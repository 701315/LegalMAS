from types import SimpleNamespace

import pytest

from src.engine.checks.executor import CheckExecutor
from src.engine.playbook.models import CheckDefinition, LLMConfig, RetrievalConfig, RulesConfig


class DummyHybridDetector:
    """Мок HybridDetector, который возвращает заранее заданный detection."""

    def __init__(self, detection_result):
        self.detection_result = detection_result
        self.called_with = None

    def run(self, text, chunks, check):
        self.called_with = {
            "text": text,
            "chunks": chunks,
            "check": check,
        }
        return self.detection_result


@pytest.fixture
def sample_doc():
    return SimpleNamespace(
        id="doc_1",
        text="Some contract text about change of control.",
        doctype="SPA",
    )


@pytest.fixture
def sample_check():
    return CheckDefinition(
        id="chk_1",
        name="Change of Control",
        description="Detect change of control clause",
        doc_types=["SPA"],
        severity="critical",
        rules=RulesConfig(
            keywords=["change of control"],
        ),
        llm=LLMConfig(),
        retrieval=RetrievalConfig(context_k=3),
    )


class FakeRetrievalEngine:
    def __init__(self, chunks):
        self._chunks = chunks

    def search(self, query, top_k=None):
        return self._chunks


def test_check_executor_basic_flow(monkeypatch, sample_doc, sample_check):
    detection = {
        "found": True,
        "evidence": "change of control",
        "confidence": 0.9,
        "method": "rules",
        "raw": {"source": "rules_confident"},
    }
    fake_detector = DummyHybridDetector(detection_result=detection)

    def fake_hd_init(self, llm_client):
        self.rules = None
        self.llm = None
        self.run = fake_detector.run

    monkeypatch.setattr("src.engine.checks.executor.HybridDetector.__init__", fake_hd_init)
    monkeypatch.setattr("src.engine.checks.executor.RetrievalEngine", FakeRetrievalEngine)

    fake_chunks = [
        {
            "id": "chunk_1",
            "text": sample_doc.text,
            "metadata": {},
        }
    ]

    executor = CheckExecutor(llm_client=None)

    result = executor.execute(sample_doc, sample_check, chunks=fake_chunks)

    assert result["doc_id"] == sample_doc.id
    assert result["check_id"] == sample_check.id
    assert result["found"] is True
    assert result["confidence"] == detection["confidence"]
    assert result["evidence"] == detection["evidence"]
    assert result["method"] == detection["method"]
    assert result["raw"] == detection["raw"]


def test_check_executor_propagates_not_found(monkeypatch, sample_doc, sample_check):
    detection = {
        "found": False,
        "evidence": "",
        "confidence": 0.0,
        "method": "rules",
        "raw": {"source": "both_not_found_llm_preferred"},
    }
    fake_detector = DummyHybridDetector(detection_result=detection)

    def fake_hd_init(self, llm_client):
        self.rules = None
        self.llm = None
        self.run = fake_detector.run

    monkeypatch.setattr("src.engine.checks.executor.HybridDetector.__init__", fake_hd_init)
    monkeypatch.setattr("src.engine.checks.executor.RetrievalEngine", FakeRetrievalEngine)

    fake_chunks = [
        {
            "id": "chunk_1",
            "text": sample_doc.text,
            "metadata": {},
        }
    ]

    executor = CheckExecutor(llm_client=None)

    result = executor.execute(sample_doc, sample_check, chunks=fake_chunks)

    assert result["found"] is False
    assert result["confidence"] == 0.0
    assert result["evidence"] == ""
    assert result["method"] == "rules"
    assert result["raw"]["source"] == "both_not_found_llm_preferred"
