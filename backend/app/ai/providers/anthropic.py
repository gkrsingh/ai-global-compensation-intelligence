"""Adapter for the Anthropic Messages API.

http_client (not the SDK's own higher-level `client` concept) is the
injection point for tests, mirroring FrankfurterProvider's pattern from
Phase 6 exactly: the Anthropic SDK is itself built on httpx and accepts
an httpx.Client via its own `http_client` constructor param, so tests can
use the identical httpx.MockTransport technique - never a live call to
the real API in the automated suite.
"""

import anthropic
import httpx

from app.ai.providers.base import (
    DEFAULT_PROVIDER_TIMEOUT,
    AIProvider,
    AIProviderError,
    GeneratedText,
)

# A bounded ceiling, not a tuning knob: this is meant to produce a short
# explanation/negotiation framing, not an essay, and every extra token
# is real, per-call cost (see the phase's own emphasis on cost being a
# genuine consideration here, unlike the free Frankfurter API in Phase 6).
DEFAULT_MAX_TOKENS = 1024


class AnthropicProvider(AIProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        http_client: httpx.Client | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        # http_client stays the test-injection point (a MockTransport-
        # backed client) when provided; production (no http_client
        # passed) gets an explicit, bounded-timeout client instead of
        # silently falling through to the SDK's own 600s-read default.
        self._client = anthropic.Anthropic(
            api_key=api_key,
            http_client=http_client or httpx.Client(timeout=DEFAULT_PROVIDER_TIMEOUT),
        )

    @property
    def name(self) -> str:
        return "anthropic"

    def generate(self, *, system_prompt: str, user_prompt: str) -> GeneratedText:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as exc:
            raise AIProviderError(f"Anthropic API request failed: {exc}") from exc

        # Anything other than a normal, complete turn means there's no
        # text worth trusting - hitting max_tokens mid-sentence is the
        # concrete risk that matters most here: a truncated response
        # could cut a number off mid-digit ("$150,0") in a way that
        # would look fabricated to the numeric-consistency checker even
        # though the model wasn't actually inventing anything, so this
        # is treated as a hard failure rather than a partial result the
        # caller has to guess about.
        if response.stop_reason != "end_turn":
            raise AIProviderError(
                "Anthropic response did not complete normally "
                f"(stop_reason={response.stop_reason!r})"
            )

        text_blocks = [block.text for block in response.content if block.type == "text"]
        if not text_blocks:
            raise AIProviderError("Anthropic response contained no text content")

        return GeneratedText(text="".join(text_blocks), model=response.model)
