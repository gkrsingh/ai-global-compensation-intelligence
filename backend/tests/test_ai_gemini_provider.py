"""Adapter tests against mocked HTTP responses only - never a live call
to the real Gemini API in the automated suite (same rule as every other
external adapter in this project). Both the request body shape and the
response payload shape below are captured from real calls made during
development (httpx.MockTransport intercepting a real genai.Client
request, and a real API call against gemini-3.5-flash-lite/gemini-3.5-
flash respectively) - not invented field names or guessed structure.
"""

import json
from collections.abc import Callable

import httpx
import pytest

from app.ai.providers.base import AIProviderError
from app.ai.providers.gemini import GeminiProvider


def _provider_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
) -> GeminiProvider:
    return GeminiProvider(
        api_key="test-key",
        model="gemini-3.5-flash-lite",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _generate_content_response(
    *,
    text: str = "This offer is competitive for the role.",
    model_version: str = "gemini-3.5-flash-lite",
    finish_reason: str = "STOP",
    parts: list[dict[str, str]] | None = None,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": parts if parts is not None else [{"text": text}],
                        "role": "model",
                    },
                    "finishReason": finish_reason,
                    "index": 0,
                }
            ],
            "modelVersion": model_version,
            "usageMetadata": {
                "promptTokenCount": 42,
                "candidatesTokenCount": 12,
                "totalTokenCount": 54,
            },
        },
    )


def test_name_is_gemini() -> None:
    provider = GeminiProvider(api_key="test-key", model="gemini-3.5-flash-lite")
    assert provider.name == "gemini"


def test_generate_sends_the_expected_request_and_parses_a_successful_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1beta/models/gemini-3.5-flash-lite:generateContent"
        payload = json.loads(request.read())
        assert payload["contents"] == [{"parts": [{"text": "Explain this offer."}], "role": "user"}]
        assert payload["systemInstruction"]["parts"] == [
            {"text": "You are a careful compensation analyst."}
        ]
        assert payload["generationConfig"]["maxOutputTokens"] == 1024
        return _generate_content_response()

    provider = _provider_with_handler(handler)
    result = provider.generate(
        system_prompt="You are a careful compensation analyst.",
        user_prompt="Explain this offer.",
    )

    assert result.text == "This offer is competitive for the role."
    assert result.model == "gemini-3.5-flash-lite"


def test_generate_reports_the_responses_own_model_version_not_the_requested_alias() -> None:
    """Same "read from the response, not the request" principle as
    AnthropicProvider - guards against a requested alias silently
    resolving to a different dated snapshot without that being recorded.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return _generate_content_response(model_version="gemini-3.5-flash-lite-001")

    provider = GeminiProvider(
        api_key="test-key",
        model="gemini-3.5-flash-lite",  # the alias requested
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.generate(system_prompt="s", user_prompt="u")

    assert result.model == "gemini-3.5-flash-lite-001"


def test_generate_raises_on_a_non_200_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"error": {"code": 500, "message": "internal error", "status": "INTERNAL"}},
        )

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError):
        provider.generate(system_prompt="s", user_prompt="u")


def test_generate_raises_on_a_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError):
        provider.generate(system_prompt="s", user_prompt="u")


def test_generate_raises_cleanly_on_a_timeout_not_a_hang_or_bare_httpx_error() -> None:
    """Phase 9's external-call resilience audit. Unlike AnthropicProvider,
    confirmed empirically that the genai SDK does NOT wrap a raw
    httpx.ReadTimeout into its own error hierarchy - it propagates as a
    bare httpx.ReadTimeout (an httpx.HTTPError subclass), the same
    surprise already found for connection errors during Phase 8's own
    research. The existing `except (genai_errors.APIError,
    httpx.HTTPError)` clause already covers it correctly for that reason;
    this test guards that behavior against ever regressing.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated stalled response", request=request)

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError):
        provider.generate(system_prompt="s", user_prompt="u")


def test_generate_raises_when_a_thinking_model_exhausts_its_budget_with_no_visible_text() -> None:
    """The real failure mode discovered during this provider's own
    research: a thinking-capable model can hit MAX_TOKENS having spent
    its entire budget on invisible internal reasoning, leaving
    content.parts=None - a real captured shape from an actual API call
    against plain gemini-3.5-flash, not a hypothetical edge case.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "MAX_TOKENS",
                        "index": 0,
                        # No "content" key at all - matches the real
                        # response captured during research exactly.
                    }
                ],
                "modelVersion": "gemini-3.5-flash",
                "usageMetadata": {
                    "promptTokenCount": 15,
                    "thoughtsTokenCount": 16,
                    "totalTokenCount": 31,
                },
            },
        )

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError, match="MAX_TOKENS"):
        provider.generate(system_prompt="s", user_prompt="u")


def test_generate_raises_when_the_response_was_blocked_for_safety() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _generate_content_response(finish_reason="SAFETY", parts=[])

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError, match="SAFETY"):
        provider.generate(system_prompt="s", user_prompt="u")


def test_generate_raises_when_the_response_has_no_candidates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [],
                "modelVersion": "gemini-3.5-flash-lite",
                "usageMetadata": {"promptTokenCount": 5, "totalTokenCount": 5},
            },
        )

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError):
        provider.generate(system_prompt="s", user_prompt="u")


def test_generate_raises_when_the_response_has_no_text_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _generate_content_response(parts=[])

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError):
        provider.generate(system_prompt="s", user_prompt="u")
