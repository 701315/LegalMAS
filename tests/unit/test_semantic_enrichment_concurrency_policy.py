from services.structure.semantic_enrichment._enricher import (
    _provider_requires_serial_execution,
    _resolve_semantic_enrichment_max_inflight_llm_calls,
)


def test_llamacpp_requires_serial_execution():
    assert _provider_requires_serial_execution("llamacpp") is True


def test_openai_does_not_require_serial_execution():
    assert _provider_requires_serial_execution("openai") is False


def test_none_provider_does_not_require_serial_execution():
    assert _provider_requires_serial_execution(None) is False


def test_llamacpp_always_clamps_to_one_even_if_configured_higher():
    assert (
        _resolve_semantic_enrichment_max_inflight_llm_calls(
            "llamacpp",
            configured_value=8,
        )
        == 1
    )


def test_non_embedded_provider_uses_configured_parallelism():
    assert (
        _resolve_semantic_enrichment_max_inflight_llm_calls(
            "openai",
            configured_value=3,
        )
        == 3
    )


def test_non_embedded_provider_falls_back_to_default_for_invalid_value():
    assert (
        _resolve_semantic_enrichment_max_inflight_llm_calls(
            "openai",
            configured_value="bad",
        )
        == 4
    )


def test_non_embedded_provider_falls_back_to_default_for_non_positive_value():
    assert (
        _resolve_semantic_enrichment_max_inflight_llm_calls(
            "openai",
            configured_value=0,
        )
        == 4
    )

    