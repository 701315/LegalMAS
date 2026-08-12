from services.embeddings._cache import build_embedding_cache_key


def test_same_text_model_role_and_limit_produce_same_key():
    k1 = build_embedding_cache_key("hello", "model-a", role="passage", max_input_tokens=500)
    k2 = build_embedding_cache_key("hello", "model-a", role="passage", max_input_tokens=500)
    assert k1 == k2


def test_different_role_produces_different_key():
    k1 = build_embedding_cache_key("hello", "model-a", role="passage", max_input_tokens=500)
    k2 = build_embedding_cache_key("hello", "model-a", role="query", max_input_tokens=500)
    assert k1 != k2


def test_different_token_limit_produces_different_key():
    k1 = build_embedding_cache_key("hello", "model-a", role="passage", max_input_tokens=500)
    k2 = build_embedding_cache_key("hello", "model-a", role="passage", max_input_tokens=300)
    assert k1 != k2


    