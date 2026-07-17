# src/services/document_family_dedup.py

"""
Pure logic helpers for family-based document deduplication.

Задача:
- выбрать ровно один representative/master document на семью;
- исключить остальные family members;
- сохранить детерминированный порядок результата.

Источник истины:
- primary truth = DocumentFamily.master_doc_id
- fallback = earliest document by (created_at, id)

Этот модуль не зависит от ORM/Celery и пригоден для unit-тестов.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any


def _document_sort_key(doc: Any) -> tuple[bool, str, str]:
    """
    Детерминированный ключ сортировки документа.

    Порядок:
    1) created_at != None идут раньше документов без created_at
    2) created_at по возрастанию
    3) id по строковому виду как tie-break

    Используем isoformat() вместо прямого сравнения datetime,
    чтобы не словить проблемы с naive/aware mixed values в тестах/грязных данных.
    """
    created_at = getattr(doc, "created_at", None)
    created_key = created_at.isoformat() if created_at is not None else ""
    doc_id = getattr(doc, "id", None)
    return (created_at is None, created_key, str(doc_id) if doc_id is not None else "")


def sort_documents_stably(documents: Sequence[Any]) -> list[Any]:
    """
    Вернуть документы в стабильном детерминированном порядке.
    """
    return sorted(documents, key=_document_sort_key)


def select_family_representative(
    *,
    family_documents: Sequence[Any],
    master_doc_id: uuid.UUID | None,
) -> Any | None:
    """
    Выбрать representative document для одной семьи.

    Правила:
    1) если master_doc_id присутствует среди family_documents — вернуть его;
    2) иначе fallback: earliest document by (created_at, id).
    """
    if not family_documents:
        return None

    docs_by_id = {
        getattr(doc, "id", None): doc
        for doc in family_documents
        if getattr(doc, "id", None) is not None
    }

    if master_doc_id is not None and master_doc_id in docs_by_id:
        return docs_by_id[master_doc_id]

    ordered = sort_documents_stably(family_documents)
    return ordered[0] if ordered else None


def filter_non_duplicate_documents(
    *,
    documents: Sequence[Any],
    families: Sequence[Any],
) -> list[Any]:
    """
    Отфильтровать документы сделки так, чтобы:
    - документы вне family остались как есть;
    - из каждой family остался ровно один representative/master;
    - порядок результата остался стабильным.

    Вход:
    - documents: полный список документов сделки
    - families: список DocumentFamily-подобных объектов с .master_doc_id и .members

    Каждый member должен иметь поле .doc_id.
    """
    ordered_documents = sort_documents_stably(documents)

    docs_by_id: dict[uuid.UUID, Any] = {
        getattr(doc, "id", None): doc
        for doc in ordered_documents
        if getattr(doc, "id", None) is not None
    }

    excluded_doc_ids: set[uuid.UUID] = set()

    for family in families:
        member_ids: list[uuid.UUID] = []
        for member in getattr(family, "members", ()) or ():
            member_doc_id = getattr(member, "doc_id", None)
            if member_doc_id is not None and member_doc_id in docs_by_id:
                member_ids.append(member_doc_id)

        if not member_ids:
            continue

        family_documents = [docs_by_id[doc_id] for doc_id in member_ids]
        representative = select_family_representative(
            family_documents=family_documents,
            master_doc_id=getattr(family, "master_doc_id", None),
        )
        representative_id = getattr(representative, "id", None) if representative is not None else None

        for member_doc_id in member_ids:
            if member_doc_id != representative_id:
                excluded_doc_ids.add(member_doc_id)

    return [
        doc
        for doc in ordered_documents
        if getattr(doc, "id", None) not in excluded_doc_ids
    ]



    