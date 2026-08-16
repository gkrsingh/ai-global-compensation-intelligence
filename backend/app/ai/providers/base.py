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

import httpx

# Shared across every concrete provider (Phase 9, original architecture
# §14): each SDK's own unconfigured default is either far too permissive
# (Anthropic's, empirically confirmed: Timeout(connect=5.0, read=600,
# write=600, pool=600) - a stalled call could hang a worker for ten
# minutes) or simply unspecified and dependent on httpx's own default
# (Gemini's, when no client is injected). Neither is an explicit, sane
# choice this project made on purpose, which is exactly what this phase's
# external-call audit calls for. 30s read is generous headroom for a
# single bounded ~1024-token completion while still failing fast enough
# that a stalled provider produces a clean, prompt AIProviderError instead
# of a hung request - confirmed with a real induced-timeout test for both
# providers, not assumed from reading either SDK.
DEFAULT_PROVIDER_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


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
    @property
    @abstractmethod
    def name(self) -> str:
        """A short, stable identifier for this provider (e.g.
        "anthropic"), persisted as AIAnalysisResult.provider - part of
        the audit trail, distinct from `model` (which model, on this
        provider, actually generated the text)."""

    @abstractmethod
    def generate(self, *, system_prompt: str, user_prompt: str) -> GeneratedText:
        """One single-turn request: a system prompt (the persona/
        constraints) and a user prompt (the grounded context + the
        actual ask), returning the model's response text plus which
        exact model produced it.
        """
