"""Tests for the actual numeric-consistency enforcement mechanism this
whole phase exists to build - the highest-scrutiny module in the
project. Every case the phase explicitly asked for is covered: a
fabricated number gets caught, a response that only echoes real numbers
passes, percentages vs. currency figures, and different formatting
(commas, currency symbols) than the source data.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompts.calculation import build_calculation_context, render_calculation_prompt
from app.ai.prompts.system import SYSTEM_PROMPT
from app.ai.services.consistency import check_numeric_consistency, extract_numbers
from app.compensation.engine import run_calculation
from app.compensation.models import CompensationComponent, CompensationInput, ComponentType
from app.reference_data.models import Country, Currency


class TestExtractNumbers:
    def test_finds_a_plain_currency_figure_with_decimals(self) -> None:
        assert extract_numbers("Gross compensation: 150000.00 USD") == {Decimal("150000.00")}

    def test_finds_a_dollar_sign_prefixed_figure(self) -> None:
        assert extract_numbers("Your take-home is $113,791.00 this year.") == {
            Decimal("113791.00")
        }

    def test_finds_a_percentage(self) -> None:
        assert extract_numbers("Your effective tax rate is 24.14%.") == {Decimal("24.14")}

    def test_finds_a_currency_symbol_other_than_dollar(self) -> None:
        assert extract_numbers("Net compensation: €849.31") == {Decimal("849.31")}
        assert extract_numbers("Standard deduction: ₹75,000.00") == {Decimal("75000.00")}

    def test_finds_a_currency_symbol_prefixed_whole_number_with_no_decimal_or_comma(self) -> None:
        """A bare integer with neither a decimal point nor comma
        grouping - the currency-symbol-adjacency check is the ONLY
        reason this gets flagged, distinct from every other test case
        here, which already has a "." or "," that would short-circuit
        before ever reaching that check.
        """
        assert extract_numbers("This role pays $150 per hour.") == {Decimal("150")}

    def test_finds_a_whole_number_immediately_followed_by_a_currency_code(self) -> None:
        """Same reasoning as above, for the trailing-currency-code check
        specifically - "150" alone has no decimal, comma, or adjacent
        symbol; only the following " USD" makes it money-shaped.
        """
        assert extract_numbers("The base salary is 150 USD per hour.") == {Decimal("150")}

    def test_ignores_incidental_bare_integers_not_shaped_like_money_or_percent(self) -> None:
        """A component count, a bracket number, an ordinal - these are
        real numbers in the prose but were never grounded data to begin
        with, and flagging them would be pure noise (Rule of the checker
        is scoped to money/percent-shaped tokens, per the phase's own
        wording, not "every number of any kind").
        """
        assert extract_numbers("There are 5 components across 3 brackets.") == set()
        assert extract_numbers("This is the 2nd bracket.") == set()

    def test_a_date_restated_in_prose_is_never_mistaken_for_a_negative_number(self) -> None:
        """A real bug, caught by Phase 8's own real Gemini E2E
        verification, not invented: the model legitimately restated the
        prompt's "As of date: 2026-08-16" in its prose (exactly what
        it's supposed to do), and the checker wrongly flagged "-16" as
        an unmatched fabricated number - failing a genuinely correct,
        fully-grounded response. Root cause was two-fold: a hyphen used
        as a date separator is indistinguishable from a minus sign
        unless the token requires NOT being preceded by another digit,
        and a bare decimal point with no digits after it (the period
        ending the sentence, "...2026-08-16.") was being absorbed into
        the token, making a plain integer look decimal-shaped.
        """
        text = "with a target currency of USD as of 2026-08-16. From your gross"
        assert extract_numbers(text) == set()

    def test_comma_grouping_and_currency_symbols_normalize_to_the_same_value_as_the_bare_form(
        self,
    ) -> None:
        """The exact "different formatting than the source data" case
        the phase calls out explicitly - a real number stored/rendered
        as "150000.00" must still be recognized when the model
        naturally writes it as "$150,000.00" in prose.
        """
        bare = extract_numbers("150000.00")
        with_commas = extract_numbers("150,000.00")
        with_symbol = extract_numbers("$150,000.00")
        with_code = extract_numbers("150,000.00 USD")

        assert bare == with_commas == with_symbol == with_code == {Decimal("150000.00")}

    def test_expands_k_and_m_abbreviations_to_their_full_value(self) -> None:
        """The system prompt explicitly forbids abbreviations, but a
        response that violates that instruction and writes "200K" for a
        real $200,000 should still be recognized as matching (whereas
        "300K" for the same real figure would correctly be flagged as a
        mismatch by check_numeric_consistency, tested below).
        """
        assert extract_numbers("about 150K") == {Decimal("150000")}
        assert extract_numbers("roughly 1.5M") == {Decimal("1500000.0")}

    def test_negative_numbers_are_parsed_correctly(self) -> None:
        assert extract_numbers("a shortfall of -500.00") == {Decimal("-500.00")}

    def test_malformed_numeric_looking_text_does_not_raise(self) -> None:
        # A currency symbol with nothing sensible after it, and a bare
        # decimal point - must not crash the extractor.
        assert extract_numbers("$ - . nothing here") == set()

    def test_the_same_value_appearing_twice_is_only_counted_once(self) -> None:
        assert extract_numbers("150000.00 and again 150000.00") == {Decimal("150000.00")}


class TestCheckNumericConsistency:
    def test_passes_when_the_response_only_echoes_real_numbers(self) -> None:
        user_prompt = "DATA:\nGross compensation: 150000.00 USD\nNet compensation: 113791.00 USD"
        generated = "This offer has a gross of $150,000.00 and a net of $113,791.00."

        result = check_numeric_consistency(user_prompt=user_prompt, generated_text=generated)

        assert result.passed is True
        assert result.unmatched_numbers == []

    def test_catches_a_fabricated_number_not_present_anywhere_in_the_prompt(self) -> None:
        user_prompt = "DATA:\nGross compensation: 150000.00 USD\nNet compensation: 113791.00 USD"
        generated = "This offer has a gross of $150,000.00, well above the $999,999.00 average."

        result = check_numeric_consistency(user_prompt=user_prompt, generated_text=generated)

        assert result.passed is False
        assert result.unmatched_numbers == ["999999.00"]

    def test_catches_a_number_that_was_rounded_differently_than_the_source(self) -> None:
        """The real risk this whole safeguard exists for: not a wildly
        invented figure, but a plausible-looking one that's subtly
        wrong - $24 instead of the real $24.14 effective tax rate.
        """
        user_prompt = "DATA:\nEffective tax rate: 24.14%"
        generated = "Your effective tax rate works out to about 24%."

        result = check_numeric_consistency(user_prompt=user_prompt, generated_text=generated)

        assert result.passed is False
        assert result.unmatched_numbers == ["24"]

    def test_percentage_and_currency_figures_are_matched_by_value_not_by_unit(self) -> None:
        """Deliberate scope boundary, documented in the module docstring:
        the checker verifies a number's VALUE traces back to grounded
        data, not that a percent-shaped output matches a percent-shaped
        input specifically. 24.14 appearing as a dollar figure in DATA
        still legitimizes the model writing "24.14%" - a real, accepted
        looseness, not an oversight.
        """
        user_prompt = "DATA:\nSome unrelated dollar figure: 24.14 USD"
        generated = "This represents about 24.14% of the total."

        result = check_numeric_consistency(user_prompt=user_prompt, generated_text=generated)

        assert result.passed is True

    def test_the_system_prompts_own_illustrative_example_never_counts_as_real_data(self) -> None:
        """The concrete, non-hypothetical risk this module's docstring
        warns about: SYSTEM_PROMPT contains the literal text "150,000"
        as an example of what NOT to abbreviate. If a future refactor
        ever passed SYSTEM_PROMPT (instead of the rendered DATA section)
        as `user_prompt`, that "150,000" would leak in as fake grounded
        data and mask a genuinely fabricated $150,000 figure. This test
        proves both halves: (1) the danger is real - SYSTEM_PROMPT does
        contain that text, and passing it as user_prompt WOULD wrongly
        legitimize $150,000; (2) the actual call site never does that -
        with the real, correctly-scoped user_prompt, the same fabricated
        figure is caught.
        """
        assert "150,000" in SYSTEM_PROMPT  # confirms the adversarial case actually exists
        generated = "This offer's gross compensation is $150,000.00."

        # (1) The vulnerability, demonstrated: if SYSTEM_PROMPT were ever
        # mistakenly passed as user_prompt, this would (wrongly) pass.
        vulnerable_result = check_numeric_consistency(
            user_prompt=SYSTEM_PROMPT, generated_text=generated
        )
        assert vulnerable_result.passed is True

        # (2) The actual, correct call site: a real DATA section that
        # does NOT contain 150,000 anywhere - the same fabricated figure
        # is correctly caught.
        real_user_prompt = "DATA:\nGross compensation: 80000.00 USD"
        real_result = check_numeric_consistency(
            user_prompt=real_user_prompt, generated_text=generated
        )
        assert real_result.passed is False
        assert real_result.unmatched_numbers == ["150000.00"]

    def test_a_completely_fabricated_market_benchmark_claim_is_caught(self) -> None:
        """The kind of violation Rule 3 (no market-rate claims) exists
        to prevent in the prompt - if the model ignores that instruction
        anyway and states a specific "market average" figure, the
        numeric checker catches it as an independent, real safeguard
        even though the two rules address the same underlying risk from
        different angles.
        """
        user_prompt = "DATA:\nGross compensation: 150000.00 USD"
        generated = "This is well below the market average of $180,000.00 for similar roles."

        result = check_numeric_consistency(user_prompt=user_prompt, generated_text=generated)

        assert result.passed is False
        assert "180000.00" in result.unmatched_numbers

    def test_details_are_fully_self_contained_for_the_audit_trail(self) -> None:
        user_prompt = "DATA:\nGross compensation: 150000.00 USD"
        generated = "Gross is $150,000.00, roughly $999.00 in fees."

        result = check_numeric_consistency(user_prompt=user_prompt, generated_text=generated)
        details = result.to_details()

        assert details["passed"] is False
        assert details["real_numbers"] == ["150000.00"]
        # Sorted by numeric value (999.00 < 150000.00), not by order of
        # appearance in the text.
        assert details["found_numbers"] == ["999.00", "150000.00"]
        assert details["unmatched_numbers"] == ["999.00"]


class TestConsistencyAgainstARealRenderedPrompt:
    """Ties the checker to step 3's actual prompt-rendering pipeline
    against a real, engine-computed Calculation - not hand-typed prompt
    strings - proving the two modules genuinely compose correctly
    together, the same "verify for real" standard as every other cross-
    module integration point in this project.
    """

    def test_a_response_that_only_paraphrases_real_figures_passes(
        self, db_session: Session
    ) -> None:
        us = db_session.scalar(select(Country).where(Country.code == "US"))
        usd = db_session.scalar(select(Currency).where(Currency.code == "USD"))
        assert us is not None and usd is not None

        comp_input = CompensationInput(
            country_id=us.id,
            target_currency_id=usd.id,
            filing_status="single",
            as_of_date=date.today(),
        )
        comp_input.components.append(
            CompensationComponent(
                component_type=ComponentType.BASE, amount=Decimal("150000.00"), currency_id=usd.id
            )
        )
        db_session.add(comp_input)
        db_session.flush()
        calculation = run_calculation(db_session, comp_input)
        db_session.flush()

        user_prompt = render_calculation_prompt(build_calculation_context(calculation))
        # A plausible, well-formatted paraphrase using only real figures
        # from the actual rendered prompt above.
        generated_text = (
            "This role pays a gross of $150,000.00 per year. After taxes of $36,209.00, "
            "you'd take home $113,791.00, which is about 75.86% of the gross - an "
            "effective tax rate of 24.14%."
        )

        result = check_numeric_consistency(user_prompt=user_prompt, generated_text=generated_text)

        assert result.passed is True
        assert result.unmatched_numbers == []

    def test_a_response_with_one_fabricated_figure_among_real_ones_is_caught(
        self, db_session: Session
    ) -> None:
        us = db_session.scalar(select(Country).where(Country.code == "US"))
        usd = db_session.scalar(select(Currency).where(Currency.code == "USD"))
        assert us is not None and usd is not None

        comp_input = CompensationInput(
            country_id=us.id,
            target_currency_id=usd.id,
            filing_status="single",
            as_of_date=date.today(),
        )
        comp_input.components.append(
            CompensationComponent(
                component_type=ComponentType.BASE, amount=Decimal("150000.00"), currency_id=usd.id
            )
        )
        db_session.add(comp_input)
        db_session.flush()
        calculation = run_calculation(db_session, comp_input)
        db_session.flush()

        user_prompt = render_calculation_prompt(build_calculation_context(calculation))
        # Real gross, real net - but an invented "market average" the
        # model was never given (exactly the Rule 3 violation the system
        # prompt forbids, caught here by the independent numeric check).
        generated_text = (
            "This offer has a gross of $150,000.00 and a net of $113,791.00, "
            "comfortably above the industry average of $130,000.00."
        )

        result = check_numeric_consistency(user_prompt=user_prompt, generated_text=generated_text)

        assert result.passed is False
        assert result.unmatched_numbers == ["130000.00"]

    def test_a_response_that_restates_the_as_of_date_is_not_wrongly_flagged(
        self, db_session: Session
    ) -> None:
        """The real bug this checker had until Phase 8's own E2E
        verification against a live Gemini call caught it: a genuinely
        correct, fully-grounded response was rejected because it
        restated the DATA section's "As of date" in prose and the old
        regex mistook the date's day component for a negative number.
        generated_text below is the actual text captured from that real
        API call (US $120,000 single filer), not a synthetic example.
        """
        us = db_session.scalar(select(Country).where(Country.code == "US"))
        usd = db_session.scalar(select(Currency).where(Currency.code == "USD"))
        assert us is not None and usd is not None

        comp_input = CompensationInput(
            country_id=us.id,
            target_currency_id=usd.id,
            filing_status="single",
            as_of_date=date(2026, 8, 16),
        )
        comp_input.components.append(
            CompensationComponent(
                component_type=ComponentType.BASE, amount=Decimal("120000.00"), currency_id=usd.id
            )
        )
        db_session.add(comp_input)
        db_session.flush()
        calculation = run_calculation(db_session, comp_input)
        db_session.flush()

        user_prompt = render_calculation_prompt(build_calculation_context(calculation))
        generated_text = (
            "This compensation offer provides a gross compensation and base salary of "
            "120000.00 USD in the United States, with a target currency of USD as of "
            "2026-08-16. From your gross amount, a total tax of 26750.00 USD is deducted, "
            "which is comprised of an income tax of 17570.00 USD, social security of "
            "7440.00 USD, medicare of 1740.00 USD, and a medicare additional surtax of "
            "0.00 USD, while accounting for a standard deduction of 16100.00 USD. In "
            "practice, this results in an effective tax rate of 22.29% and leaves you with "
            "a net compensation after tax of 93250.00 USD, meaning your take-home "
            "percentage of gross is 77.71%."
        )

        result = check_numeric_consistency(user_prompt=user_prompt, generated_text=generated_text)

        assert result.passed is True
        assert result.unmatched_numbers == []
