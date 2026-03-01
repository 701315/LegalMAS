import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.classifiers.stage8.hybrid_classifier import HybridClassifier
from src.core.config import settings

pytestmark = pytest.mark.asyncio


@pytest.fixture
def uow_mock():
    """
    UoW с мокнутым async documents repo и session (для RunnerRepository).
    """
    uow = MagicMock()
    uow.session = MagicMock()
    uow.documents = MagicMock()
    uow.documents.get_by_id = AsyncMock()
    return uow


def _make_doc(
    doc_id: str = "doc-1",
    filename: str = "file.docx",
    folder: str = "/",
    is_duplicate: bool = False,
    doc_type: str | None = None,
    classification_confidence: float | None = None,
):
    doc = MagicMock()
    doc.id = doc_id
    doc.filename = filename
    doc.folder = folder
    doc.is_duplicate = is_duplicate
    doc.doc_type = doc_type
    doc.classification_confidence = classification_confidence
    return doc


# 1. Дубликат и master → level="COPIED", тип/уверенность скопированы
async def test_hybrid_classifier_copies_from_master_for_duplicate(uow_mock):
    from src.classifiers.stage8 import hybrid_classifier as hc_module

    doc = _make_doc(
        doc_id="dup-1",
        is_duplicate=True,
    )
    master = _make_doc(
        doc_id="master-1",
        doc_type="SPA",
        classification_confidence=0.93,
    )

    uow_mock.documents.get_by_id.return_value = doc

    repo_mock = MagicMock()
    repo_mock.get_master_document.return_value = master

    with patch.object(hc_module, "RunnerRepository", return_value=repo_mock):
        clf = HybridClassifier(uow_mock)
        result = await clf.classify_document(doc.id)

    assert result["level"] == "COPIED"
    assert result["copied_from_master"] == str(master.id)
    assert result["final_type"] == master.doc_type
    assert result["final_confidence"] == pytest.approx(
        float(master.classification_confidence or 0.0)
    )


# Базовый DummyHybrid, который инициализирует поля, ожидаемые реальным классом,
# и позволяет подсовывать свои l1/l2/l3/content_service/registry.
def _make_dummy_hybrid(hc_module, uow, l1, l2, l3, content_service=None, registry=None):
    class DummyHybrid(hc_module.HybridClassifier):
        def __init__(self, uow_inner):
            self.uow = uow_inner
            self.repo = MagicMock()
            self.registry = registry or MagicMock()
            self.l1 = l1
            self.l2 = l2
            self.l3 = l3
            self.content_service = content_service
            self.level_weights = {
                "L1": 0.4,
                "L2": 0.3,
                "L3": 0.3,
            }

    return DummyHybrid(uow)


# 2. L1 уверенный → даже при наличии content_service финальный выбор равен L1-кандидату
async def test_hybrid_classifier_l1_confident_stops_early(uow_mock):
    from src.classifiers.stage8 import hybrid_classifier as hc_module

    doc = _make_doc(
        doc_id="doc-l1",
        filename="contract_spa_en.docx",
        folder="/deals/123",
    )
    uow_mock.documents.get_by_id.return_value = doc

    l1_mock = MagicMock()
    l1_mock.classify.return_value = [
        {
            "type_code": "SPA",
            "confidence": settings.CLASSIFICATION_L1_ACCEPT + 0.01,
            "level": "L1",
            "method": "filename",
        }
    ]
    l2_mock = MagicMock()
    l2_mock.classify.return_value = []
    l3_mock = MagicMock()
    l3_mock.classify.return_value = []

    content_service_mock = MagicMock()
    content_service_mock.get_header_and_snippet = AsyncMock(return_value=(None, None))

    clf = _make_dummy_hybrid(
        hc_module, uow_mock, l1_mock, l2_mock, l3_mock, content_service=content_service_mock
    )
    result = await clf.classify_document(doc.id)

    assert result["final_type"] == "SPA"
    assert result["final_confidence"] == pytest.approx(
        settings.CLASSIFICATION_L1_ACCEPT + 0.01
    )
    assert "L1" in result["details"]["levels_tried"]
    l2_mock.classify.assert_not_called()
    l3_mock.classify.assert_not_called()


# 3. L1 слабый, L2 уверенный → при наличии header и без L3 побеждает L2
async def test_hybrid_classifier_l2_confident_skips_l3(uow_mock):
    from src.classifiers.stage8 import hybrid_classifier as hc_module

    doc = _make_doc(
        doc_id="doc-l2",
        filename="unknown.docx",
        folder="/deals/123",
    )
    uow_mock.documents.get_by_id.return_value = doc

    l1_mock = MagicMock()
    l1_mock.classify.return_value = [
        {
            "type_code": "SPA",
            "confidence": settings.CLASSIFICATION_L1_ACCEPT - 0.1,
            "level": "L1",
            "method": "filename",
        }
    ]

    l2_result = MagicMock()
    l2_result.doctype = "NDA"
    l2_result.confidence = settings.CLASSIFICATION_L2_ACCEPT + 0.01
    l2_result.method = "header"
    l2_result.evidence = "Header match"

    l2_mock = MagicMock()
    l2_mock.classify = AsyncMock(return_value=l2_result)

    l3_mock = MagicMock()
    l3_mock.classify = AsyncMock(return_value=[])

    content_service_mock = MagicMock()
    content_service_mock.get_header_and_snippet = AsyncMock(
        return_value=("Some header text", None)
    )

    clf = _make_dummy_hybrid(
        hc_module, uow_mock, l1_mock, l2_mock, l3_mock, content_service=content_service_mock
    )
    result = await clf.classify_document(doc.id)

    assert result["final_type"] == "NDA"
    assert result["final_confidence"] >= settings.CLASSIFICATION_L2_ACCEPT
    assert "L2" in result["details"]["levels_tried"]


# 4. L1/L2 слабые → при наличии snippet побеждает L3-кандидат
async def test_hybrid_classifier_uses_l3_when_l1_l2_weak(uow_mock):
    from src.classifiers.stage8 import hybrid_classifier as hc_module

    doc = _make_doc(
        doc_id="doc-l3",
        filename="unknown.docx",
        folder="/deals/123",
    )
    uow_mock.documents.get_by_id.return_value = doc

    l1_mock = MagicMock()
    l1_mock.classify.return_value = [
        {
            "type_code": "SPA",
            "confidence": settings.CLASSIFICATION_L1_ACCEPT - 0.1,
            "level": "L1",
            "method": "filename",
        }
    ]

    l2_result = MagicMock()
    l2_result.doctype = "NDA"
    l2_result.confidence = settings.CLASSIFICATION_L2_ACCEPT - 0.05
    l2_result.method = "header"
    l2_result.evidence = "Weak header"

    l2_mock = MagicMock()
    l2_mock.classify = AsyncMock(return_value=l2_result)

    l3_result = MagicMock()
    l3_result.doctype = "MSA"
    l3_result.confidence = settings.CLASSIFICATION_L3_ACCEPT + 0.02
    l3_result.method = "semantic"
    l3_result.evidence = "Semantic match"
    l3_result.language = "en"
    l3_result.jurisdiction = "US"
    l3_result.applicable_triggers = []

    l3_mock = MagicMock()
    l3_mock.classify = AsyncMock(return_value=l3_result)

    content_service_mock = MagicMock()
    content_service_mock.get_header_and_snippet = AsyncMock(
        return_value=("Some header", "Some snippet text")
    )

    clf = _make_dummy_hybrid(
        hc_module, uow_mock, l1_mock, l2_mock, l3_mock, content_service=content_service_mock
    )
    result = await clf.classify_document(doc.id)

    assert result["final_type"] == "MSA"
    assert result["final_confidence"] >= settings.CLASSIFICATION_L3_ACCEPT
    assert "L3" in result["details"]["levels_tried"]


# 5. HYBRID‑голосование + language/jurisdiction при участии всех уровней
async def test_hybrid_classifier_hybrid_voting_and_metadata(uow_mock):
    from src.classifiers.stage8 import hybrid_classifier as hc_module

    doc = _make_doc(doc_id="doc-hybrid", filename="mixed.docx", folder="/deals/123")
    doc.language = None
    doc.jurisdiction = None
    uow_mock.documents.get_by_id.return_value = doc

    l1_mock = MagicMock()
    l1_mock.classify.return_value = [
        {"type_code": "SPA", "confidence": 0.65, "level": "L1", "method": "filename"},
    ]

    l2_result = MagicMock()
    l2_result.doctype = "NDA"
    l2_result.confidence = 0.7
    l2_result.method = "header"
    l2_result.evidence = "Header evidence"

    l2_mock = MagicMock()
    l2_mock.classify = AsyncMock(return_value=l2_result)

    l3_result = MagicMock()
    l3_result.doctype = "SPA"
    l3_result.confidence = 0.8
    l3_result.method = "semantic"
    l3_result.evidence = "Semantic evidence"
    l3_result.language = "en"
    l3_result.jurisdiction = "US"
    l3_result.applicable_triggers = []

    l3_mock = MagicMock()
    l3_mock.classify = AsyncMock(return_value=l3_result)

    registry_mock = MagicMock()
    registry_mock.get_language.return_value = "en"
    registry_mock.get_jurisdiction.return_value = "US"

    content_service_mock = MagicMock()
    content_service_mock.get_header_and_snippet = AsyncMock(
        return_value=("Some header", "Some snippet text")
    )

    clf = _make_dummy_hybrid(
        hc_module,
        uow_mock,
        l1_mock,
        l2_mock,
        l3_mock,
        content_service=content_service_mock,
        registry=registry_mock,
    )
    result = await clf.classify_document(doc.id)

    assert result["final_type"] == "SPA"
    assert result["final_confidence"] == pytest.approx(0.8)
    assert result["level"] == "HYBRID"

    assert "levels_tried" in result["details"]
    assert "candidates" in result["details"]
    assert "voting" in result["details"]

    assert result["language"] == "en"
    assert result["jurisdiction"] == "US"
