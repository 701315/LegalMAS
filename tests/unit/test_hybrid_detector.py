import pytest
from types import SimpleNamespace

from src.engine.detectors.hybrid_detector import HybridDetector, RULES_CONFIDENCE_THRESHOLD


class DummyCheck:
    """Простейший объект, имитирующий CheckDefinition."""
    def __init__(
        self,
        id: str = "chk_1",
        name: str = "Test check",
        description: str = "Test description",
        doc_types: list[str] | None = None,
        severity: str = "medium",
        severity_if_fail: str | None = None,
        severity_if_pass: str | None = None,
        severity_if_unclear: str | None = None,
        llm: object | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.description = description
        self.doc_types = doc_types or []
        self.severity = severity
        self.severity_if_fail = severity_if_fail
        self.severity_if_pass = severity_if_pass
        self.severity_if_unclear = severity_if_unclear
        self.llm = llm
        # rules здесь не важен, его результат мы мокнем через RulesDetector
        self.rules = SimpleNamespace()


@pytest.fixture
def dummy_chunks():
    # Можно передать пустой список, т.к. мы не проверяем логику LLM внутри
    return []


class FakeRulesDetector:
    """Мокнутый RulesDetector, возвращающий заранее заданный результат."""
    def __init__(self, result):
        self.result = result
        self.called = False

    def detect(self, text, rules):
        self.called = True
        return self.result


class FakeLLMDetector:
    """Мокнутый LLMDetector, возвращающий заранее заданный результат или None."""
    def __init__(self, result):
        self.result = result
        self.called = False
        self.last_extra_variables = None

    def detect_with_variables(self, config, chunks, extra_variables):
        self.called = True
        self.last_extra_variables = extra_variables
        return self.result

class DummyLLMClient:
    def is_available(self) -> bool:
        return True

    def call(self, prompt: str, temperature: float, max_tokens: int):
        # В этих тестах мы всё равно мокаем LLMDetector и не должны сюда приходить,
        # так что можно просто вернуть None или бросить, если захотим отследить.
        return None

def make_hybrid_detector(rules_result, llm_result):
    """Удобный конструктор HybridDetector с подменой детекторов."""
    dummy_client = DummyLLMClient()
    hd = HybridDetector(llm_client=dummy_client)
    hd.rules = FakeRulesDetector(rules_result)
    hd.llm = FakeLLMDetector(llm_result)
    return hd



def test_rules_confident_llm_not_called(dummy_chunks):
    """Сценарий: rules нашёл и уверенность выше порога → LLM не вызывается, method='rules'."""
    rules_result = {
        "found": True,
        "confidence": RULES_CONFIDENCE_THRESHOLD + 0.1,
        "evidence": "by rules",
    }
    llm_result = None  # не важно, он не должен вызываться

    detector = make_hybrid_detector(rules_result, llm_result)

    check = DummyCheck(
        llm=SimpleNamespace(
            prompt_template="Test {condition_name} with {context}",
            context_k=3,
            temperature=0.0,
            max_tokens=100,
        )
    )

    result = detector.run("some text", dummy_chunks, check)

    assert detector.rules.called is True
    assert detector.llm.called is False
    assert result["method"] == "rules"
    assert result["raw"]["source"] == "rules_confident"


def test_rules_not_found_llm_called_and_wins(dummy_chunks):
    """Сценарий: rules не нашёл → вызывается LLM, found=True, method='llm'."""
    rules_result = {
        "found": False,
        "confidence": 0.0,
        "evidence": "",
    }
    # имитируем DetectionResult от LLMDetector после _flatten_llm_result
    llm_detection = SimpleNamespace(
        found=True,
        confidence=0.9,
        evidence_chunks=[],
        details={},
    )

    detector = make_hybrid_detector(rules_result, llm_detection)

    check = DummyCheck(
        llm=SimpleNamespace(
            prompt_template="Test {condition_name} with {context}",
            context_k=3,
            temperature=0.0,
            max_tokens=100,
        )
    )

    result = detector.run("some text", dummy_chunks, check)

    assert detector.rules.called is True
    assert detector.llm.called is True
    assert result["found"] is True
    assert result["method"] == "llm"
    assert result["raw"]["source"] == "llm_found_rules_not_found"
    # проверяем, что extra_variables заполнены
    ev = detector.llm.last_extra_variables
    assert ev["condition_name"] == check.name
    assert ev["check_id"] == check.id
    assert "doc_types" in ev


def test_conflict_rules_found_llm_not_found(dummy_chunks):
    """
    Конфликтный сценарий:
    rules: found=True (низкая уверенность),
    LLM: found=False (не нашёл).
    Ожидаемое поведение: остаёмся на rules, method='rules'.
    """
    rules_result = {
        "found": True,
        "confidence": 0.4,
        "evidence": "rule hit",
    }
    llm_detection = SimpleNamespace(
        found=False,
        confidence=0.9,
        evidence_chunks=[],
        details={},
    )

    detector = make_hybrid_detector(rules_result, llm_detection)

    check = DummyCheck(
        llm=SimpleNamespace(
            prompt_template="Test {condition_name} with {context}",
            context_k=3,
            temperature=0.0,
            max_tokens=100,
        )
    )

    result = detector.run("some text", dummy_chunks, check)

    assert detector.rules.called is True
    assert detector.llm.called is True
    assert result["method"] == "rules"
    assert result["raw"]["source"] == "rules_found_llm_not_found"
    assert "llm_confidence" in result["raw"]


def test_both_found_llm_stronger(dummy_chunks):
    """
    Сценарий: оба нашли, но LLM более уверен → method='llm'.
    """
    rules_result = {
        "found": True,
        "confidence": 0.6,
        "evidence": "rule hit",
    }
    llm_detection = SimpleNamespace(
        found=True,
        confidence=0.9,
        evidence_chunks=[],
        details={},
    )

    detector = make_hybrid_detector(rules_result, llm_detection)

    check = DummyCheck(
        llm=SimpleNamespace(
            prompt_template="Test {condition_name} with {context}",
            context_k=3,
            temperature=0.0,
            max_tokens=100,
        )
    )

    result = detector.run("some text", dummy_chunks, check)

    assert detector.rules.called is True
    assert detector.llm.called is True
    assert result["method"] == "llm"
    assert result["raw"]["source"] == "llm_stronger"
    assert result["raw"]["rules_confidence"] == rules_result["confidence"]
