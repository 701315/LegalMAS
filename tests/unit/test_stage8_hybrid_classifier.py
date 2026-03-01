from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

import pytest

from src.classifiers.stage8.hybrid_classifier import HybridClassifier
from src.core.config import settings


class DummyDoc:
    """Минимальная заглушка документа для HybridClassifier."""

    def __init__(
        self,
        id: Any,
        filename: str = "",
        folder_path: str = "",
        text: str = "",
        is_duplicate: bool = False,
        doc_type: str | None = None,
        classification_confidence: float | None = None,
        language: str | None = None,
        jurisdiction: str | None = None,
        applicable_triggers: List[str] | None = None,
    ) -> None:
        self.id = id
        self.filename = filename
        self.folder_path = folder_path
        self.text = text
        self.is_duplicate = is_duplicate
        self.doc_type = doc_type
        self.classification_confidence = classification_confidence
        self.language = language
        self.jurisdiction = jurisdiction
        self.applicable_triggers = applicable_triggers or []


class DummyDocumentsRepo:
    """Простая заглушка uow.documents с in-memory хранилищем."""

    def __init__(self, docs: Dict[Any, DummyDoc]) -> None:
        self._docs = docs

    def get_by_id(self, doc_id: str) -> DummyDoc | None:
        return self._docs.get(doc_id)


class DummyRunnerRepo:
    """Заглушка RunnerRepository для тестов HybridClassifier."""

    def __init__(self, docs: Dict[Any, DummyDoc]) -> None:
        self._docs = docs

    def get_master_document(self, doc_id: str) -> DummyDoc | None:
        # Для теста COPIED просто возвращаем заранее подготовленный master
        return self._docs.get("master")


class DummyUoW:
    """Минимальный UoW для HybridClassifier: session + documents."""

    def __init__(self, docs: Dict[Any, DummyDoc]) -> None:
        self.session = None
        self.documents = DummyDocumentsRepo(docs)


@pytest.fixture(autouse=True)
def _setup_thresholds(monkeypatch):
    """Гарантируем предсказуемые пороги для ранних остановок."""
    monkeypatch.setattr(settings, "CLASSIFICATION_L1_ACCEPT", 0.9, raising=False)
    monkeypatch.setattr(settings, "CLASSIFICATION_L2_ACCEPT", 0.8, raising=False)
    monkeypatch.setattr(settings, "CLASSIFICATION_L3_ACCEPT", 0.7, raising=False)
    monkeypatch.setattr(settings, "RUNNER_EMBEDDINGS_ENABLED", False, raising=False)
    yield


@pytest.mark.asyncio
async def test_hybrid_classifier_copied_from_master(monkeypatch):
    """Если документ дубликат и у master есть классификация — возвращается COPIED."""
    master = DummyDoc(
        id="master",
        doc_type="contract_master",
        classification_confidence=0.95,
        language="ru",
        jurisdiction="RU",
        applicable_triggers=["t1"],
    )
    dup = DummyDoc(
        id="dup",
        is_duplicate=True,
    )
    docs = {"dup": dup, "master": master}
    uow = DummyUoW(docs)

    # Подменяем RunnerRepository внутри HybridClassifier
    def _dummy_runner_repo(session):
        return DummyRunnerRepo(docs)

    monkeypatch.setattr(
        "src.classifiers.stage8.hybrid_classifier.RunnerRepository",
        _dummy_runner_repo,
    )

    clf = HybridClassifier(uow)

    # вызываем асинхронный метод как async
    result = await clf.classify_document("dup")

    assert result["level"] == "COPIED"
    assert result["final_type"] == "contract_master"
    assert result["final_confidence"] == 0.95
    assert result["language"] == "ru"
    assert result["jurisdiction"] == "RU"
    assert result["copied_from_master"] == "master"
    assert set(result["applicable_triggers"]) == {"t1"}



@pytest.mark.asyncio
async def test_hybrid_classifier_l1_early_stop(monkeypatch):
    """L1 даёт высокую уверенность → ранняя остановка на уровне L1."""
    doc_id = "doc-l1"
    doc = DummyDoc(id=doc_id, filename="VERY_OBVIOUS_CONTRACT.pdf", text="")
    docs = {doc_id: doc}
    uow = DummyUoW(docs)

    # L1 возвращает один кандидат с нужной уверенность
    class DummyL1:
        def classify(self, filename: str, folder: str) -> list[dict]:
            return [
                {
                    "type_code": "contract_l1",
                    "confidence": settings.CLASSIFICATION_L1_ACCEPT,
                    "level": "L1",
                    "method": "filename",
                }
            ]

    monkeypatch.setattr(
        "src.classifiers.stage8.hybrid_classifier.L1FilenameClassifier",
        lambda: DummyL1(),
    )
    monkeypatch.setattr(
        "src.classifiers.stage8.hybrid_classifier.L2HeaderClassifier",
        lambda: None,
    )
    monkeypatch.setattr(
        "src.classifiers.stage8.hybrid_classifier.L3SemanticClassifier",
        lambda: None,
    )
    monkeypatch.setattr(
        "src.classifiers.stage8.hybrid_classifier.RunnerRepository",
        lambda session: DummyRunnerRepo(docs),
    )

    clf = HybridClassifier(uow)
    result = await clf.classify_document(doc_id)

    assert result["level"] == "L1"
    assert result["final_type"] == "contract_l1"
    assert result["final_confidence"] == settings.CLASSIFICATION_L1_ACCEPT
    assert "L1" in result["levels_tried"]


@pytest.mark.asyncio
async def test_hybrid_classifier_hybrid_voting(monkeypatch):
    """При отсутствии ранних остановок используется HYBRID голосование и возвращается voting."""
    doc_id = "doc-hybrid"
    doc = DummyDoc(
        id=doc_id,
        filename="file.pdf",
        text="some header\nand body\ntext",
    )
    docs = {doc_id: doc}
    uow = DummyUoW(docs)

    class DummyL1:
        def classify(self, filename: str, folder: str) -> list[dict]:
            return [
                {
                    "type_code": "contract_l1",
                    "confidence": 0.5,
                    "level": "L1",
                    "method": "filename",
                }
            ]

    class DummyL2Result:
        def __init__(self):
            self.doctype = "contract_l2"
            self.confidence = 0.6
            self.level = "L2"
            self.method = "header_pattern"
            self.evidence = "matched header"

    class DummyL2:
        async def classify(
            self,
            text: str,
            filename: str,
            folder_path: str,
            text_sanitized=None,
            metadata=None,
        ):
            return DummyL2Result()

    class DummyL3Result:
        def __init__(self):
            self.doctype = "contract_l3"
            self.confidence = 0.65
            self.level = "L3"
            self.method = "embedding_similarity"
            self.evidence = "cosine_sim=0.8"
            self.language = "en"
            self.jurisdiction = "US"
            self.alternative_types = []

    class DummyL3:
        async def classify(
            self,
            text: str,
            filename: str,
            folder_path: str,
            text_sanitized=None,
            metadata=None,
        ):
            return DummyL3Result()

    monkeypatch.setattr(
        "src.classifiers.stage8.hybrid_classifier.L1FilenameClassifier",
        lambda: DummyL1(),
    )
    monkeypatch.setattr(
        "src.classifiers.stage8.hybrid_classifier.L2HeaderClassifier",
        lambda: DummyL2(),
    )
    monkeypatch.setattr(
        "src.classifiers.stage8.hybrid_classifier.L3SemanticClassifier",
        lambda: DummyL3(),
    )
    monkeypatch.setattr(
        "src.classifiers.stage8.hybrid_classifier.RunnerRepository",
        lambda session: DummyRunnerRepo(docs),
    )
    # Отключаем раннюю остановку L2/L3, чтобы дойти до HYBRID
    monkeypatch.setattr(settings, "CLASSIFICATION_L2_ACCEPT", 0.9, raising=False)
    monkeypatch.setattr(settings, "CLASSIFICATION_L3_ACCEPT", 0.9, raising=False)
    monkeypatch.setattr(settings, "RUNNER_EMBEDDINGS_ENABLED", True, raising=False)

    clf = HybridClassifier(uow)
    result = await clf.classify_document(doc_id)

    assert result["level"] == "HYBRID"
    assert result["final_type"] in {"contract_l1", "contract_l2", "contract_l3"}
    assert "voting" in result["details"]
    assert "language" in result
    assert "jurisdiction" in result
