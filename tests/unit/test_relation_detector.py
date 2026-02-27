import pytest

from src.core.config import settings
from src.services.relations.detector import RelationDetector
from src.services.relations.models import RelationDetectionMethod


@pytest.fixture
def detector():
    return RelationDetector()


def test_appendix_filename_pattern(detector, monkeypatch):
    docs = [
        {
            "id": "doc-master",
            "filename": "SharePurchaseAgreement.pdf",
            "folder_path": "01. Transaction",
            "doc_type": "SPA",
            "text_first_2000": "",
            "classification_level": "L3",
        },
        {
            "id": "doc-app",
            "filename": "Appendix 1 to SharePurchaseAgreement.pdf",
            "folder_path": "01. Transaction",
            "doc_type": "Generic",
            "text_first_2000": "",
            "classification_level": "L1",
        },
    ]

    monkeypatch.setattr(settings, "RELATIONS_FILENAME_ENABLED", True)
    monkeypatch.setattr(settings, "RELATIONS_TEXT_ENABLED", False)

    relations = detector.detect_all_relations(docs)

    assert len(relations) == 1
    rel = relations[0]
    assert rel.source_doc_id == "doc-app"
    assert rel.target_doc_id == "doc-master"
    assert rel.relation_type == "appendix"
    assert rel.method == RelationDetectionMethod.FILENAME_PATTERN


def test_amendment_filename_pattern(detector, monkeypatch):
    docs = [
        {
            "id": "doc-master",
            "filename": "Договор купли-продажи.pdf",
            "folder_path": "01. Transaction",
            "doc_type": "SPA",
            "text_first_2000": "",
            "classification_level": "L2",
        },
        {
            "id": "doc-amend",
            "filename": "Дополнительное соглашение №1 к Договору купли-продажи.pdf",
            "folder_path": "01. Transaction",
            "doc_type": "Generic",
            "text_first_2000": "",
            "classification_level": "L1",
        },
    ]

    monkeypatch.setattr(settings, "RELATIONS_FILENAME_ENABLED", True)
    monkeypatch.setattr(settings, "RELATIONS_TEXT_ENABLED", False)

    relations = detector.detect_all_relations(docs)

    assert len(relations) == 1
    rel = relations[0]
    assert rel.relation_type == "amendment"
    assert rel.source_doc_id == "doc-amend"
    assert rel.target_doc_id == "doc-master"


def test_version_groups(detector, monkeypatch):
    docs = [
        {
            "id": "doc-v1",
            "filename": "SPAv1.pdf",
            "folder_path": "",
            "doc_type": "SPA",
            "text_first_2000": "",
            "classification_level": "L2",
        },
        {
            "id": "doc-v2",
            "filename": "SPAv2.pdf",
            "folder_path": "",
            "doc_type": "SPA",
            "text_first_2000": "",
            "classification_level": "L2",
        },
        {
            "id": "doc-v3",
            "filename": "SPAv3.pdf",
            "folder_path": "",
            "doc_type": "SPA",
            "text_first_2000": "",
            "classification_level": "L2",
        },
    ]

    monkeypatch.setattr(settings, "RELATIONS_FILENAME_ENABLED", True)
    monkeypatch.setattr(settings, "RELATIONS_TEXT_ENABLED", False)

    relations = detector.detect_all_relations(docs)
    version_rels = [r for r in relations if r.relation_type == "version"]

    assert len(version_rels) == 2
    ids = {(r.source_doc_id, r.target_doc_id) for r in version_rels}
    assert ("doc-v2", "doc-v1") in ids
    assert ("doc-v3", "doc-v2") in ids


def test_text_based_appendix(detector, monkeypatch):
    docs = [
        {
            "id": "doc-master",
            "filename": "SPA.pdf",
            "folder_path": "",
            "doc_type": "SPA",
            "text_first_2000": "",
            "classification_level": "L3",
        },
        {
            "id": "doc-app",
            "filename": "Generic.pdf",
            "folder_path": "",
            "doc_type": "Generic",
            "text_first_2000": "Настоящее Приложение является неотъемлемой частью Договора...",
            "classification_level": "L1",
        },
    ]

    monkeypatch.setattr(settings, "RELATIONS_FILENAME_ENABLED", False)
    monkeypatch.setattr(settings, "RELATIONS_TEXT_ENABLED", True)

    relations = detector.detect_all_relations(docs)
    assert len(relations) == 1
    rel = relations[0]
    assert rel.relation_type == "appendix"
    assert rel.method == RelationDetectionMethod.TEXT_REFERENCE
