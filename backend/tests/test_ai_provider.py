"""Adapter tests against mocked HTTP responses only - never a live call
to the real Anthropic API in the automated suite (same rule as Phase 6's
exchange rate adapter). The mocked payloads below are shaped exactly
like a real anthropic.types.Message serializes (confirmed empirically by
constructing a real Message instance and inspecting its own
model_dump() during development - not invented field names).
"""

import json
from collections.abc import Callable

import httpx
import pytest

from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import AIProviderError


def _provider_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
) -> AnthropicProvider:
    return AnthropicProvider(
        api_key="test-key",
        model="claude-sonnet-5",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _message_response(
    *,
    text: str = "This offer is competitive for the role.",
    model: str = "claude-sonnet-5-20260101",
    stop_reason: str = "end_turn",
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "msg_01ABC",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": text, "citations": None}],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "stop_details": None,
            "container": None,
            "usage": {"input_tokens": 42, "output_tokens": 12},
        },
    )


def test_name_is_anthropic() -> None:
    provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-5")
    assert provider.name == "anthropic"


def test_generate_parses_a_successful_response_and_sends_the_expected_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        payload = json.loads(request.read())
        assert payload["model"] == "claude-sonnet-5"
        assert payload["system"] == "You are a careful compensation analyst."
        assert payload["messages"] == [{"role": "user", "content": "Explain this offer."}]
        return _message_response()

    provider = _provider_with_handler(handler)
    result = provider.generate(
        system_prompt="You are a careful compensation analyst.",
        user_prompt="Explain this offer.",
    )

    assert result.text == "This offer is competitive for the role."
    assert result.model == "claude-sonnet-5-20260101"


def test_generate_reports_the_models_own_response_model_not_the_requested_alias() -> None:
    """The response's `model` field is the source of truth for the audit
    trail, not just an echo of the alias requested - guards against a
    requested alias silently resolving to a different dated snapshot
    without that being recorded anywhere.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return _message_response(model="claude-sonnet-5-20260315")

    provider = AnthropicProvider(
        api_key="test-key",
        model="claude-sonnet-5",  # the alias requested
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.generate(system_prompt="s", user_prompt="u")

    assert result.model == "claude-sonnet-5-20260315"


def test_generate_raises_on_a_non_200_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500, json={"type": "error", "error": {"type": "api_error", "message": "boom"}}
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
    """Phase 9's external-call resilience audit: a stalled request must
    produce a clean, catchable AIProviderError, not an unhandled
    httpx.ReadTimeout propagating past this adapter. Confirmed empirically
    (not assumed from reading the SDK) that the Anthropic SDK wraps a raw
    httpx.ReadTimeout into its own anthropic.APITimeoutError - a subclass
    of anthropic.APIError, so the existing `except anthropic.APIError`
    clause already covers it correctly; this test exists to guard that
    behavior against ever regressing, not because the except clause
    needed to change.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated stalled response", request=request)

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError):
        provider.generate(system_prompt="s", user_prompt="u")


def test_generate_raises_when_the_response_was_truncated_by_max_tokens() -> None:
    """A response cut off mid-thought could cut a number off mid-digit
    ("$150,0") in a way that would look fabricated to the numeric-
    consistency checker even though the model wasn't actually inventing
    anything - treated as a hard failure here rather than a partial
    result the caller has to guess about.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return _message_response(text="This offer is comp", stop_reason="max_tokens")

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError, match="max_tokens"):
        provider.generate(system_prompt="s", user_prompt="u")


def test_generate_raises_when_the_response_was_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _message_response(text="", stop_reason="refusal")

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError, match="refusal"):
        provider.generate(system_prompt="s", user_prompt="u")


def test_generate_raises_when_the_response_has_no_text_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "msg_01ABC",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5-20260101",
                "content": [],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "stop_details": None,
                "container": None,
                "usage": {"input_tokens": 42, "output_tokens": 0},
            },
        )

    provider = _provider_with_handler(handler)
    with pytest.raises(AIProviderError):
        provider.generate(system_prompt="s", user_prompt="u")
