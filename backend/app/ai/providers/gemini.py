"""Adapter for the Google Gemini API via the google-genai SDK.

http_client is the injection point for tests, mirroring AnthropicProvider
and FrankfurterProvider exactly: HttpOptions.httpx_client is a real,
empirically-confirmed injection point (verified during development by
constructing a real genai.Client with an httpx.MockTransport-backed
client and confirming the mock handler - not a live endpoint - actually
receives the request) - never a live call to the real API in the
automated suite.

Model choice, decided during research rather than assumed: gemini-2.5-
flash (the obvious "same family as before" choice) is no longer
available to new users (a real 404 hit during research, not a
hypothetical). The current default, plain gemini-3.5-flash, is a
thinking model - a real test call with a 20-token budget spent the
entire budget on invisible internal reasoning and returned
content.parts=None, hitting MAX_TOKENS with zero visible text. For a
short, bounded, safety-constrained task like this, that's real
unpredictable failure risk for no benefit - gemini-3.5-flash-lite does
not do this by default and returned a clean STOP/real-text response on
the same test, and is confirmed free-tier.
"""

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.ai.providers.base import AIProvider, AIProviderError, GeneratedText

# Same reasoning as AnthropicProvider's DEFAULT_MAX_TOKENS - a bounded
# ceiling for a short explanation, not an essay, and every extra token is
# real (if free-tier-bounded) usage against Gemini's own rate limits.
DEFAULT_MAX_TOKENS = 1024


class GeminiProvider(AIProvider):
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
        http_options = (
            types.HttpOptions(httpx_client=http_client) if http_client is not None else None
        )
        self._client = genai.Client(api_key=api_key, http_options=http_options)

    @property
    def name(self) -> str:
        return "gemini"

    def generate(self, *, system_prompt: str, user_prompt: str) -> GeneratedText:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=self._max_tokens,
                ),
            )
        except (genai_errors.APIError, httpx.HTTPError) as exc:
            # Two distinct exception families, both real: genai_errors.
            # APIError covers structured API failures (4xx/5xx the SDK
            # parses into its own error type), but a raw transport
            # failure (DNS, connection refused) propagates as a bare
            # httpx.HTTPError straight through the SDK's own tenacity-
            # based retry wrapper, unlike AnthropicProvider's SDK, which
            # catches transport failures into its own APIError hierarchy
            # - confirmed by a real test that failed until this second
            # except clause was added, not assumed from reading the code.
            raise AIProviderError(f"Gemini API request failed: {exc}") from exc

        if not response.candidates:
            raise AIProviderError("Gemini response contained no candidates")
        candidate = response.candidates[0]

        # Anything other than a normal, complete turn means there's no
        # text worth trusting - same reasoning as AnthropicProvider's
        # stop_reason check, and concretely confirmed during this
        # provider's own research: a thinking-capable model can hit
        # MAX_TOKENS having spent its entire budget on invisible internal
        # reasoning, leaving no visible content at all - not hypothetical.
        if candidate.finish_reason != types.FinishReason.STOP:
            raise AIProviderError(
                "Gemini response did not complete normally "
                f"(finish_reason={candidate.finish_reason!r})"
            )

        parts = candidate.content.parts if candidate.content is not None else None
        text_parts = [part.text for part in parts if part.text] if parts else []
        if not text_parts:
            raise AIProviderError("Gemini response contained no text content")

        # Falls back to the requested model alias only if the response
        # genuinely omits its own model_version - the response's own
        # value is still preferred whenever present, same "read from the
        # response, not the request" principle as AnthropicProvider.
        model_version = response.model_version or self._model
        return GeneratedText(text="".join(text_parts), model=model_version)
