"""The actual enforcement mechanism behind this phase's non-negotiable
constraint (original architecture §9): a prompt instruction telling the
model "don't invent numbers" is necessary but NOT sufficient on its own -
LLMs can still misstate a number even when explicitly told not to. This
module is the real safeguard: after generation, every number-shaped
token in the model's output gets extracted and checked against the exact
set of numbers genuinely present in the rendered user prompt (the DATA
section).

Critically, the "real" set is built ONLY from the user prompt, NEVER the
system prompt - app/ai/prompts/system.py's SYSTEM_PROMPT contains its
own illustrative example ("never write \"150K\" for \"150,000\""), and
that "150,000" is instructional text, not grounded data. If it leaked
into the real-numbers set, a fabricated $150,000 figure would silently
pass the check regardless of what the actual calculation says - this is
tested explicitly, not just avoided by convention.

Deliberately scoped to VALUE matching, not semantic-category matching: a
number is accepted if its numeric value appears anywhere in the grounded
data, regardless of whether it was originally a currency amount or a
percentage in context (so "24.14" in the response matches whether the
context labeled it a dollar figure or a percentage). Verifying that a
percentage-shaped output number specifically matches a percentage-shaped
input number - and not a coincidentally-equal dollar figure - is a
harder, fuzzier problem this phase doesn't attempt: the goal here is
catching genuinely INVENTED digit sequences, not full semantic
correctness.

Known, deliberate limitation: numbers spelled out in words ("one hundred
fifty thousand dollars") are not recognized at all - parsing spelled-out
English number words is a much larger undertaking than this phase's
scope justifies, and the system prompt's own instruction to state
figures verbatim in digit form makes this an unlikely failure mode in
practice, not an ignored one.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

_CURRENCY_SYMBOLS = "$€₹£"

# A digit run with optional comma-grouping and an optional decimal part.
# Deliberately lenient about grouping correctness - "1,50,000" (Indian-
# style grouping) isn't validated as "properly" grouped, just stripped
# of commas and parsed as whatever digits remain; malformed grouping is
# not this checker's concern.
_NUMBER_TOKEN = re.compile(r"-?\d[\d,]*\.?\d*")

# "150K", "1.5M", "2B" - a number immediately followed by a scale letter.
# Matched and expanded separately from _NUMBER_TOKEN so a value like
# "200K" is checked against its real 200000 magnitude, not silently
# ignored as a bare, non-money-shaped "200".
_ABBREVIATED_NUMBER = re.compile(r"-?(\d[\d,]*\.?\d*)\s?([KkMmBb])\b")
_ABBREVIATION_MULTIPLIERS: dict[str, Decimal] = {
    "k": Decimal(1_000),
    "m": Decimal(1_000_000),
    "b": Decimal(1_000_000_000),
}


def _looks_like_money_or_percent(text: str, start: int, end: int) -> bool:
    """Whether the plain digit-run at text[start:end] is shaped like a
    monetary figure or percentage - not just any bare integer (a
    component count, a bracket number, an ordinal) that happens to
    appear in prose and was never meant to be checked against grounded
    data in the first place.
    """
    token = text[start:end]
    if "." in token or "," in token:
        return True
    if start > 0 and text[start - 1] in _CURRENCY_SYMBOLS:
        return True
    if text[end : end + 1] == "%":
        return True
    # A 3-letter uppercase currency-code-shaped token right after (one
    # optional space) - not hardcoded to USD/EUR/INR specifically, so
    # this doesn't need updating if a new currency is added later.
    if re.match(r"\s?[A-Z]{3}\b", text[end : end + 4]):
        return True
    return False


def extract_numbers(text: str) -> set[Decimal]:
    """Every money/percent-shaped numeric token in `text`, normalized to
    Decimal so "150,000.00", "150000.00", and "$150,000" all collapse to
    the same value regardless of how each was formatted.

    No try/except around the Decimal parsing below: both _NUMBER_TOKEN
    and _ABBREVIATED_NUMBER require a leading digit and allow at most one
    decimal point, so a comma-stripped match is always a valid decimal
    literal by construction - there is no input that reaches Decimal()
    here and fails. A silently-swallowed InvalidOperation would only end
    up masking a real bug in the regex itself, not protecting against
    anything a crafted test could ever demonstrate.
    """
    found: set[Decimal] = set()
    claimed_spans: list[tuple[int, int]] = []

    for match in _ABBREVIATED_NUMBER.finditer(text):
        digits = match.group(1).replace(",", "")
        suffix = match.group(2).lower()
        found.add(Decimal(digits) * _ABBREVIATION_MULTIPLIERS[suffix])
        claimed_spans.append(match.span())

    for match in _NUMBER_TOKEN.finditer(text):
        start, end = match.span()
        if any(start >= s and end <= e for s, e in claimed_spans):
            continue  # already accounted for as part of an abbreviated token
        if not _looks_like_money_or_percent(text, start, end):
            continue
        found.add(Decimal(match.group().replace(",", "")))

    return found


@dataclass(frozen=True)
class ConsistencyCheckResult:
    passed: bool
    real_numbers: list[str]
    found_numbers: list[str]
    unmatched_numbers: list[str]

    def to_details(self) -> dict[str, object]:
        """The exact shape persisted as AIAnalysisResult.consistency_
        check_details - self-contained (repeats `passed` even though
        it's also its own column) so the audit record is fully readable
        on its own, without needing to cross-reference a sibling column.
        """
        return {
            "passed": self.passed,
            "real_numbers": self.real_numbers,
            "found_numbers": self.found_numbers,
            "unmatched_numbers": self.unmatched_numbers,
        }


def check_numeric_consistency(*, user_prompt: str, generated_text: str) -> ConsistencyCheckResult:
    """The real numbers set comes ONLY from user_prompt (the rendered
    DATA section) - never the system prompt, which contains its own
    illustrative examples that are not grounded data and must never be
    mistaken for it.
    """
    real_numbers = extract_numbers(user_prompt)
    found_numbers = extract_numbers(generated_text)
    unmatched = found_numbers - real_numbers

    return ConsistencyCheckResult(
        passed=len(unmatched) == 0,
        real_numbers=[str(n) for n in sorted(real_numbers)],
        found_numbers=[str(n) for n in sorted(found_numbers)],
        unmatched_numbers=[str(n) for n in sorted(unmatched)],
    )
