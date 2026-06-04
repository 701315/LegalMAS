from core.config import settings
from services.structure.semantic_enrichment import _enricher as enricher


def test_resolve_llm_info_uses_actual_llamacpp_model_label_not_legacy_structure_model(
    monkeypatch,
):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "llamacpp", raising=False)
    monkeypatch.setattr(
        settings,
        "LLM_LOCAL_MODEL_PATH",
        "/home/vladi/models/qwen2.5-7b-instruct-q4_k_m.gguf",
        raising=False,
    )
    monkeypatch.setattr(settings, "STRUCTURE_LLM_PROVIDER", "local", raising=False)
    monkeypatch.setattr(
        settings,
        "STRUCTURE_LLM_MODEL",
        "qwen2.5-3b-instruct-q4_k_m",
        raising=False,
    )

    provider, model = enricher._resolve_llm_info()

    assert provider == "llamacpp"
    assert model == "qwen2.5-7b-instruct-q4_k_m.gguf"


def test_resolve_llm_info_normalizes_windows_style_model_path(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "llamacpp", raising=False)
    monkeypatch.setattr(
        settings,
        "LLM_LOCAL_MODEL_PATH",
        r"C:\LegalMAS\LLMmodel\qwen2.5-7b-instruct-q4_k_m.gguf",
        raising=False,
    )

    provider, model = enricher._resolve_llm_info()

    assert provider == "llamacpp"
    assert model == "qwen2.5-7b-instruct-q4_k_m.gguf"


def test_resolve_semantic_enrichment_cache_identity_keeps_full_llamacpp_path(monkeypatch):
    model_path = "/home/vladi/models/qwen2.5-7b-instruct-q4_k_m.gguf"
    monkeypatch.setattr(settings, "LLM_PROVIDER", "llamacpp", raising=False)
    monkeypatch.setattr(settings, "LLM_LOCAL_MODEL_PATH", model_path, raising=False)

    provider, model = enricher._resolve_semantic_enrichment_cache_identity()

    assert provider == "llamacpp"
    assert model == model_path


    