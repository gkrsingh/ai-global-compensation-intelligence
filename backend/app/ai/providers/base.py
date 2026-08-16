"""AI provider abstraction (original architecture §9): one interface, one
concrete adapter for now (Anthropic), swappable in principle.

This module knows NOTHING about compensation, calculations, or
comparisons - it only knows how to send a system+user prompt to a
language model and get text back. Domain-specific prompt construction
lives in app/ai/prompts/; the non-negotiable "the AI never computes
numbers" safeguard lives in app/ai/services/ (the numeric-consistency
checker) - neither belongs here. Deliberately no conversation history,
no tools, no streaming, no agent framework: this project is a single
grounded, single-turn call per insight, not an orchestration problem
(see the original architecture's explicit reasoning against
LangChain/CrewAI-style frameworks for this).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedText:
    text: str
    # The exact model that actually produced this response, read from
    # the provider's own response rather than just echoed back from what
    # was requested - guards against silently mislabeling the audit
    # trail if a requested alias resolves to a different dated snapshot.
    model: str


class AIProviderError(Exception):
    """Raised when a provider can't return usable text - a bad HTTP
    status, a malformed response, or a response that finished for a
    reason other than a normal, complete turn (hit max_tokens mid-
    thought, or was refused) - in either case there's no text worth
    trusting, so this is treated as a hard failure, not a partial
    result the caller has to figure out how to handle.
    """


class AIProvider(ABC):
    @abstractmethod
    def generate(self, *, system_prompt: str, user_prompt: str) -> GeneratedText:
        """One single-turn request: a system prompt (the persona/
        constraints) and a user prompt (the grounded context + the
        actual ask), returning the model's response text plus which
        exact model produced it.
        """
