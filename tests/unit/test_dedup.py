import datetime

import pytest

from src.services.relations.dedup import ExactDedupService
from src.services.relations.models import RelationDetectionMethod


@pytest.fixture
def deduper():
    return ExactDedupService()


def test_no_duplicates(deduper):
    docs = [
        {
            "id": "doc-1",
            "sha256_file": "hash1",
            "filename": "a.pdf",
            "created_at": datetime.datetime(2024, 1, 1, 10, 0, 0),
        },
        {
            "id": "doc-2",
            "sha256_file": "hash2",
            "filename": "b.pdf",
            "created_at": datetime.datetime(2024, 1, 1, 11, 0, 0),
        },
        {
            "id": "doc-3",
            "sha256_file": "hash3",
            "filename": "c.pdf",
            "created_at": datetime.datetime(2024, 1, 1, 12, 0, 0),
        },
    ]

    result, relations = deduper.find_duplicates(docs)

    assert result.total_documents == 3
    assert result.exact_duplicates == 0
    assert result.duplicate_groups == []
    assert result.marked_doc_ids == []
    assert relations == []


def test_single_duplicate_group(deduper):
    docs = [
        {
            "id": "doc-1",
            "sha256_file": "hash1",
            "filename": "orig.pdf",
            "created_at": datetime.datetime(2024, 1, 1, 10, 0, 0),
        },
        {
            "id": "doc-2",
            "sha256_file": "hash1",
            "filename": "copy.pdf",
            "created_at": datetime.datetime(2024, 1, 1, 11, 0, 0),
        },
    ]

    result, relations = deduper.find_duplicates(docs)

    assert result.total_documents == 2
    assert result.exact_duplicates == 1
    assert len(result.duplicate_groups) == 1
    assert set(result.duplicate_groups[0]) == {"doc-1", "doc-2"}
    assert len(result.kept_doc_ids) == 1
    assert len(result.marked_doc_ids) == 1
    assert len(relations) == 1

    rel = relations[0]
    assert rel.relation_type == "version"
    assert rel.method == RelationDetectionMethod.EXACT_HASH
    assert rel.confidence == 1.0
    assert {rel.source_doc_id, rel.target_doc_id} == {"doc-1", "doc-2"}


def test_multiple_duplicate_groups(deduper):
    docs = [
        {
            "id": "doc-1",
            "sha256_file": "h1",
            "filename": "a1.pdf",
            "created_at": datetime.datetime(2024, 1, 1, 9, 0, 0),
        },
        {
            "id": "doc-2",
            "sha256_file": "h1",
            "filename": "a2.pdf",
            "created_at": datetime.datetime(2024, 1, 1, 10, 0, 0),
        },
        {
            "id": "doc-3",
            "sha256_file": "h2",
            "filename": "b1.pdf",
            "created_at": datetime.datetime(2024, 1, 1, 9, 30, 0),
        },
        {
            "id": "doc-4",
            "sha256_file": "h2",
            "filename": "b2.pdf",
            "created_at": datetime.datetime(2024, 1, 1, 10, 30, 0),
        },
    ]

    result, relations = deduper.find_duplicates(docs)

    assert result.total_documents == 4
    assert result.exact_duplicates == 2
    assert len(result.duplicate_groups) == 2
    assert len(result.kept_doc_ids) == 2
    assert len(result.marked_doc_ids) == 2
    assert len(relations) == 2
