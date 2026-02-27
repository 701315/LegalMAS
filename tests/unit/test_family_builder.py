import pytest

from src.core.config import settings
from src.services.relations.family_builder import FamilyBuilder
from src.services.relations.models import DetectedRelation, RelationDetectionMethod


@pytest.fixture
def builder(monkeypatch):
    # Явно зафиксируем master_doc_types, чтобы не зависеть от YAMLRegistry в юнит‑тесте
    family_builder = FamilyBuilder()
    family_builder.master_doc_types = ["SPA", "SHA"]
    return family_builder


def _rel(src, tgt, rtype="appendix"):
    return DetectedRelation(
        source_doc_id=src,
        target_doc_id=tgt,
        relation_type=rtype,
        confidence=0.9,
        evidence_text="test",
        method=RelationDetectionMethod.FILENAME_PATTERN,
    )


def test_simple_family(builder):
    docs = [
        {
            "id": "doc-spa",
            "doc_type": "SPA",
            "filename": "SPA.pdf",
            "classification_level": "L3",
            "yaml_instruction_available": True,
            "applicable_triggers": ["change_of_control"],
        },
        {
            "id": "doc-app1",
            "doc_type": "Generic",
            "filename": "Appendix 1.pdf",
            "classification_level": "L1",
            "yaml_instruction_available": False,
            "applicable_triggers": [],
        },
        {
            "id": "doc-amend1",
            "doc_type": "Generic",
            "filename": "Amendment 1.pdf",
            "classification_level": "L2",
            "yaml_instruction_available": False,
            "applicable_triggers": [],
        },
    ]

    relations = [
        _rel("doc-app1", "doc-spa", "appendix"),
        _rel("doc-amend1", "doc-spa", "amendment"),
    ]

    families = builder.build_families(docs, relations)

    assert len(families) == 1
    family = families[0]
    assert family.master_doc_id == "doc-spa"
    assert set(family.member_doc_ids) == {"doc-spa", "doc-app1", "doc-amend1"}
    assert family.master_classification_level == "L3"
    assert family.master_yaml_available is True
    assert "change_of_control" in family.master_applicable_triggers


def test_l3_master_preferred_over_l2(builder, monkeypatch):
    # SPA L2 и SHA L3 в одной папке, appendix должен прикрепиться к SHA
    docs = [
        {
            "id": "doc-spa",
            "doc_type": "SPA",
            "filename": "SPAdraft.pdf",
            "folder_path": "01. Transaction",
            "classification_level": "L2",
            "yaml_instruction_available": True,
            "applicable_triggers": [],
        },
        {
            "id": "doc-sha",
            "doc_type": "SHA",
            "filename": "SHAagreement.pdf",
            "folder_path": "01. Transaction",
            "classification_level": "L3",
            "yaml_instruction_available": True,
            "applicable_triggers": ["change_of_control"],
        },
        {
            "id": "doc-app",
            "doc_type": "Generic",
            "filename": "Appendix 1 to SHAagreement.pdf",
            "folder_path": "01. Transaction",
            "classification_level": "L1",
            "yaml_instruction_available": False,
            "applicable_triggers": [],
        },
    ]

    # relations: appendix → SHA
    relations = [
        _rel("doc-app", "doc-sha", "appendix"),
    ]

    # Настраиваем приоритет уровней
    monkeypatch.setattr(
        settings,
        "FAMILY_CLASSIFICATION_LEVEL_PRIORITY",
        ["L0", "L1", "L2", "L3"],
    )

    families = builder.build_families(docs, relations)
    assert len(families) == 1
    family = families[0]

    assert family.master_doc_id == "doc-sha"
    assert family.master_classification_level == "L3"
    assert family.master_yaml_available is True
    assert "change_of_control" in family.master_applicable_triggers
