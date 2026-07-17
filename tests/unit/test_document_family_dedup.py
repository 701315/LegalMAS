"""
Pure-logic tests for family-based document deduplication.

Не тянет ORM/Celery импорты.
Проверяет именно бизнес-правила:
- из семьи остаётся только master;
- документы вне семьи сохраняются;
- fallback детерминирован;
- порядок результата стабилен.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from services.document_family_dedup import (
    filter_non_duplicate_documents,
    select_family_representative,
    sort_documents_stably,
)


@dataclass
class FakeDocument:
    id: uuid.UUID
    created_at: datetime | None
    filename: str = ""
    doc_type: str | None = None


@dataclass
class FakeMember:
    doc_id: uuid.UUID


@dataclass
class FakeFamily:
    id: uuid.UUID
    master_doc_id: uuid.UUID
    members: list[FakeMember] = field(default_factory=list)


def _dt(minutes: int) -> datetime:
    return datetime(2025, 1, 1, 12, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


class TestDocumentFamilyDedup:
    def test_sort_documents_stably_orders_by_created_at_then_id(self):
        doc_b = FakeDocument(
            id=_uuid("00000000-0000-0000-0000-00000000000b"),
            created_at=_dt(1),
        )
        doc_a = FakeDocument(
            id=_uuid("00000000-0000-0000-0000-00000000000a"),
            created_at=_dt(1),
        )
        doc_c = FakeDocument(
            id=_uuid("00000000-0000-0000-0000-00000000000c"),
            created_at=_dt(2),
        )

        result = sort_documents_stably([doc_c, doc_b, doc_a])

        assert [doc.id for doc in result] == [doc_a.id, doc_b.id, doc_c.id]

    def test_select_family_representative_prefers_master_doc_id(self):
        master = FakeDocument(
            id=_uuid("10000000-0000-0000-0000-000000000001"),
            created_at=_dt(10),
        )
        member = FakeDocument(
            id=_uuid("10000000-0000-0000-0000-000000000002"),
            created_at=_dt(1),
        )

        rep = select_family_representative(
            family_documents=[member, master],
            master_doc_id=master.id,
        )

        assert rep is master

    def test_select_family_representative_falls_back_to_earliest_when_master_missing(self):
        earlier = FakeDocument(
            id=_uuid("20000000-0000-0000-0000-000000000001"),
            created_at=_dt(1),
        )
        later = FakeDocument(
            id=_uuid("20000000-0000-0000-0000-000000000002"),
            created_at=_dt(5),
        )

        missing_master_id = _uuid("29999999-0000-0000-0000-000000000999")

        rep = select_family_representative(
            family_documents=[later, earlier],
            master_doc_id=missing_master_id,
        )

        assert rep is earlier

    def test_filter_non_duplicate_documents_keeps_standalone_and_family_master(self):
        standalone = FakeDocument(
            id=_uuid("30000000-0000-0000-0000-000000000001"),
            created_at=_dt(1),
        )
        master = FakeDocument(
            id=_uuid("30000000-0000-0000-0000-000000000002"),
            created_at=_dt(2),
        )
        member = FakeDocument(
            id=_uuid("30000000-0000-0000-0000-000000000003"),
            created_at=_dt(3),
        )
        trailing = FakeDocument(
            id=_uuid("30000000-0000-0000-0000-000000000004"),
            created_at=_dt(4),
        )

        family = FakeFamily(
            id=_uuid("30000000-0000-0000-0000-000000000099"),
            master_doc_id=master.id,
            members=[FakeMember(doc_id=master.id), FakeMember(doc_id=member.id)],
        )

        result = filter_non_duplicate_documents(
            documents=[standalone, master, member, trailing],
            families=[family],
        )

        assert [doc.id for doc in result] == [
            standalone.id,
            master.id,
            trailing.id,
        ]

    def test_filter_non_duplicate_documents_handles_multiple_families(self):
        fam1_master = FakeDocument(
            id=_uuid("40000000-0000-0000-0000-000000000001"),
            created_at=_dt(1),
        )
        fam1_member = FakeDocument(
            id=_uuid("40000000-0000-0000-0000-000000000002"),
            created_at=_dt(2),
        )
        standalone = FakeDocument(
            id=_uuid("40000000-0000-0000-0000-000000000003"),
            created_at=_dt(3),
        )
        fam2_master = FakeDocument(
            id=_uuid("40000000-0000-0000-0000-000000000004"),
            created_at=_dt(4),
        )
        fam2_member = FakeDocument(
            id=_uuid("40000000-0000-0000-0000-000000000005"),
            created_at=_dt(5),
        )

        family1 = FakeFamily(
            id=_uuid("40000000-0000-0000-0000-000000000101"),
            master_doc_id=fam1_master.id,
            members=[FakeMember(doc_id=fam1_master.id), FakeMember(doc_id=fam1_member.id)],
        )
        family2 = FakeFamily(
            id=_uuid("40000000-0000-0000-0000-000000000102"),
            master_doc_id=fam2_master.id,
            members=[FakeMember(doc_id=fam2_master.id), FakeMember(doc_id=fam2_member.id)],
        )

        result = filter_non_duplicate_documents(
            documents=[fam1_master, fam1_member, standalone, fam2_master, fam2_member],
            families=[family1, family2],
        )

        assert [doc.id for doc in result] == [
            fam1_master.id,
            standalone.id,
            fam2_master.id,
        ]

    def test_filter_non_duplicate_documents_uses_deterministic_fallback_when_master_missing(self):
        earlier = FakeDocument(
            id=_uuid("50000000-0000-0000-0000-000000000001"),
            created_at=_dt(1),
        )
        later = FakeDocument(
            id=_uuid("50000000-0000-0000-0000-000000000002"),
            created_at=_dt(2),
        )

        family = FakeFamily(
            id=_uuid("50000000-0000-0000-0000-000000000099"),
            master_doc_id=_uuid("59999999-0000-0000-0000-000000000999"),
            members=[FakeMember(doc_id=later.id), FakeMember(doc_id=earlier.id)],
        )

        result = filter_non_duplicate_documents(
            documents=[later, earlier],
            families=[family],
        )

        assert [doc.id for doc in result] == [earlier.id]

    def test_filter_non_duplicate_documents_ignores_family_members_missing_from_documents(self):
        present = FakeDocument(
            id=_uuid("60000000-0000-0000-0000-000000000001"),
            created_at=_dt(1),
        )
        outsider_member_id = _uuid("60000000-0000-0000-0000-000000000999")

        family = FakeFamily(
            id=_uuid("60000000-0000-0000-0000-000000000099"),
            master_doc_id=present.id,
            members=[FakeMember(doc_id=present.id), FakeMember(doc_id=outsider_member_id)],
        )

        result = filter_non_duplicate_documents(
            documents=[present],
            families=[family],
        )

        assert [doc.id for doc in result] == [present.id]

        