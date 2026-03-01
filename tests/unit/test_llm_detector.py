import json
from types import SimpleNamespace

import pytest

from src.engine.detectors.llm_detector import LLMDetector, DEFAULT_PROMPT_FILE
from src.engine.detectors.models import RetrievedChunk, DetectionResult


class DummyLLMClient:
    """Простой мок LLMClient для тестов."""

    def __init__(self, available: bool = True, response: str | None = None):
        self._available = available
        self._response = response
        self.last_call = None

    def is_available(self) -> bool:
        return self._available

    def call(self, prompt: str, temperature: float, max_tokens: int):
        self.last_call = {
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self._response is None:
            return None
        # эмулируем LLMResponse минимумом полей
        data = json.loads(self._response)
        return SimpleNamespace(
            found=data.get("found"),
            evidence=data.get("evidence"),
            clause=data.get("clause"),
            confidence=data.get("confidence", 0.0),
            provider="dummy",
            model="dummy-model",
            tokens_used=0,
            parse_success=True,
            reasoning=data.get("reasoning"),
            raw_response=self._response,
        )


class DummyPromptLoader:
    """Мок PromptLoader, чтобы не читать реальные файлы."""
    def __init__(self, template: str):
        self.template = template

    def load_raw(self, name: str) -> str:
        return self.template

    def exists(self, name: str) -> bool:
        return True

    def list_prompts(self, category: str | None = None):
        return [DEFAULT_PROMPT_FILE]


@pytest.fixture
def sample_chunks():
    return [
        RetrievedChunk(
            element_id="e1",
            text="First chunk text",
            page=1,
            clause_uid="c1",
            bbox=[],
            combined_score=0.9,
        ),
        RetrievedChunk(
            element_id="e2",
            text="Second chunk text",
            page=2,
            clause_uid="c2",
            bbox=[],
            combined_score=0.8,
        ),
    ]


def test_detect_returns_none_when_llm_unavailable(monkeypatch, sample_chunks):
    """Если клиент недоступен, detect должен вернуть None."""
    client = DummyLLMClient(available=False)

    detector = LLMDetector(client=client)
    # подменяем promptloader, чтобы _resolve_prompt не полез в файловую систему
    monkeypatch.setattr(detector, "promptloader", DummyPromptLoader("Prompt: {context}"))

    from src.engine.playbook.models import LLMConfig
    cfg = LLMConfig(prompt_template="Prompt: {context}")

    result = detector.detect(cfg, sample_chunks)

    assert result is None


def test_detect_with_variables_no_chunks_returns_empty_detection(monkeypatch):
    """Если чанков нет, detect_with_variables должен вернуть DetectionResult с found=False."""
    client = DummyLLMClient(available=True, response=None)

    detector = LLMDetector(client=client)
    monkeypatch.setattr(detector, "promptloader", DummyPromptLoader("Prompt: {context}"))

    from src.engine.playbook.models import LLMConfig
    cfg = LLMConfig(prompt_template="Prompt: {context}")

    result = detector.detect_with_variables(cfg, chunks=[], extra_variables={})

    assert isinstance(result, DetectionResult)
    assert result.found is False
    assert result.confidence == 0.0
    assert result.detector_type == "llm"
    assert result.details.get("reason") == "no_chunks_for_context"


def test_detect_with_variables_success(monkeypatch, sample_chunks):
    """Успешный сценарий: корректный промпт и валидный JSON-ответ от LLM."""
    llm_payload = {
        "found": True,
        "evidence": "First chunk text",
        "clause": "c1",
        "confidence": 0.85,
        "reasoning": "Test reasoning",
    }
    client = DummyLLMClient(
        available=True,
        response=json.dumps(llm_payload),
    )

    detector = LLMDetector(client=client)
    monkeypatch.setattr(
        detector,
        "promptloader",
        DummyPromptLoader("Check {condition_name}:\n\n{context}"),
    )

    from src.engine.playbook.models import LLMConfig
    cfg = LLMConfig(prompt_template="Check {condition_name}:\n\n{context}")

    extra_vars = {"condition_name": "Test check"}
    result = detector.detect_with_variables(cfg, sample_chunks, extra_vars)

    assert isinstance(result, DetectionResult)
    assert result.found is True
    assert result.confidence == pytest.approx(0.85)
    assert result.detector_type == "llm"
    # evidence должен быть обрезанным текстом evidence
    assert result.evidence_chunks
    assert "First chunk text" in result.evidence_chunks[0].text
    # убедимся, что переменные действительно подставлялись в промпт
    assert "Test check" in client.last_call["prompt"]
    assert "First chunk text" in client.last_call["prompt"]


def test_detect_with_variables_missing_variable(monkeypatch, sample_chunks):
    """Если в шаблоне есть переменная, которой нет в extra_variables, должен вернуться None."""
    client = DummyLLMClient(available=True, response=None)

    detector = LLMDetector(client=client)
    # шаблон требует {condition_name}, а мы её не передадим
    monkeypatch.setattr(
        detector,
        "promptloader",
        DummyPromptLoader("Check {condition_name}:\n\n{context}"),
    )

    from src.engine.playbook.models import LLMConfig
    cfg = LLMConfig(prompt_template="Check {condition_name}:\n\n{context}")

    # не передаем condition_name
    result = detector.detect_with_variables(cfg, sample_chunks, extra_variables={})

    assert result is None
