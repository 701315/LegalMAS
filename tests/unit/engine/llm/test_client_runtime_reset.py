from __future__ import annotations

from types import SimpleNamespace

from engine.llm.client import LLMClient


class _ClosableModel:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _BrokenClosableModel:
    def close(self) -> None:
        raise RuntimeError("close failed")


def _make_client() -> LLMClient:
    client = LLMClient()
    client.provider = "llamacpp"
    client._llama_model = None
    client._llama_grammar_cache = {}
    return client


def test_reset_local_runtime_state_clears_model_and_grammar_cache():
    client = _make_client()
    model = _ClosableModel()
    client._llama_model = model
    client._llama_grammar_cache = {
        "a.gbnf": object(),
        "b.gbnf": object(),
    }

    client.reset_local_runtime_state()

    assert client._llama_model is None
    assert client._llama_grammar_cache == {}
    assert model.closed is True


def test_reset_local_runtime_state_is_noop_for_non_llamacpp():
    client = LLMClient()
    client.provider = "ollama"
    marker = object()
    client._llama_model = marker
    client._llama_grammar_cache = {"a.gbnf": object()}

    client.reset_local_runtime_state()

    assert client._llama_model is marker
    assert "a.gbnf" in client._llama_grammar_cache


def test_reset_local_runtime_state_handles_model_without_close():
    client = _make_client()
    client._llama_model = SimpleNamespace()
    client._llama_grammar_cache = {"a.gbnf": object()}

    client.reset_local_runtime_state()

    assert client._llama_model is None
    assert client._llama_grammar_cache == {}


def test_reset_local_runtime_state_best_effort_swallows_close_errors():
    client = _make_client()
    client._llama_model = _BrokenClosableModel()
    client._llama_grammar_cache = {"a.gbnf": object()}

    client.reset_local_runtime_state_best_effort()

    # best-effort wrapper не должен бросать исключение наружу
    # состояние модели/кэша уже обнулено до попытки close()
    assert client._llama_model is None
    assert client._llama_grammar_cache == {}


    