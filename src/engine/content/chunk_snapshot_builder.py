# src/engine/content/chunk_snapshot_builder.py

"""
ChunkSnapshotBuilder — единый сервис для построения snapshot'а чанков.

Простыми словами для непрофессионального программиста:

- В MinIO у нас уже есть:
  * layout (layout_primary / layout_primary_sanitized) — список маленьких кусочков текста;
  * clause_tree — дерево пунктов договора (1., 1.1., 1.2. и т.п.).

- DocumentContentService сейчас на лету строит чанки:
  * листовые клаузы (clause),
  * нормализованные под‑чанки (subclause),
  * крупные разделы (section).

- Этот класс делает то же самое, но:
  * собирает ВСЮ эту структуру в один JSON‑объект (snapshot),
  * возвращает его как dict, чтобы воркер chunk_builder сохранил его в MinIO.

Зачем это нужно:
- В будущем RetrievalEngine / CheckRunner / LLM будут читать готовый snapshot
  из MinIO (по ссылке chunks_ref в DocumentVersion), а не пересчитывать
  чанки при каждом запросе.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.clause_tree_builder import ClauseTreeBuilder
from engine.content.chunking import (
    build_chunk_summary,
    build_section_chunks_from_clauses,
    split_text_to_sized_chunks,
)
from engine.retrieval.tokenization import count_tokens
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)


class ChunkSnapshotBuilder:
    """
    Сервис построения canonical snapshot'а чанков для документа.

    Для непрофессионального программиста:
    - На вход даём:
      * session (подключение к БД),
      * doc_id (UUID документа),
      * параметры chunking (размер, максимум, overlap).
    - Внутри:
      1) читаем из БД последнюю версию документа;
      2) по ссылкам version.layout_primary*_ref и version.clause_tree_ref
         читаем layout и clause_tree из MinIO;
      3) строим:
         - leaf clause chunks (как get_chunks в DocumentContentService),
         - sized subclause chunks (как get_sized_chunks),
         - section‑чанки (как get_hierarchical_chunks → build_section_chunks_from_clauses);
      4) собираем всё это в один dict (snapshot) и возвращаем его.
    """

    def __init__(self, store: ArtifactStore | None = None) -> None:
        # ArtifactStore умеет читать/писать JSON в MinIO.
        self.store = store or ArtifactStore()

    async def build_snapshot(
        self,
        *,
        session: AsyncSession,
        doc_id: uuid.UUID,
        target_tokens: int = 300,
        max_tokens: int = 800,
        overlap_ratio: float = 0.15,
    ) -> dict[str, Any]:
        # 1. Загружаем документ и его последнюю версию из БД.
        doc_repo = DocumentRepository(session)
        ver_repo = DocumentVersionRepository(session)

        doc = await doc_repo.get_by_id(doc_id)
        if not doc:
            raise PermanentError(f"Document {doc_id} not found")

        version = await ver_repo.get_latest(doc_id)
        if not version:
            raise PermanentError(f"DocumentVersion for doc {doc_id} not found")

        # 2. Определяем, какой layout использовать.
        #
        # Приоритет:
        #   1) layout_primary_sanitized_ref — основной layout после PII;
        #   2) layout_primary_ref — fallback, если PII ещё не прошёл.
        layout_ref = (
            getattr(version, "layout_primary_sanitized_ref", None)
            or getattr(version, "layout_primary_ref", None)
        )
        if not layout_ref:
            raise PermanentError(
                f"No primary layout for doc {doc_id} "
                f"(layout_primary_sanitized_ref/layout_primary_ref missing)"
            )

        clause_tree_ref = getattr(version, "clause_tree_ref", None)
        if not clause_tree_ref:
            raise PermanentError(
                f"No clause_tree_ref for doc {doc_id}, structure must be built first"
            )

        # 3. Читаем layout и clause_tree из MinIO.
        layout = self.store.get_json(layout_ref)
        clause_tree = self.store.get_json(clause_tree_ref)

        # 4. Строим leaf‑чанки по клаузам (как get_chunks в DocumentContentService).
        leaf_chunks = ClauseTreeBuilder.build_leaf_chunks(
            doc_id=doc_id,
            tree=clause_tree,
            layout=layout,
        )

        if not leaf_chunks:
            logger.warning(
                "ChunkSnapshotBuilder: clause tree produced no leaf chunks",
                extra={
                    "doc_id": str(doc_id),
                    "clause_tree_ref": clause_tree_ref,
                    "layout_ref": layout_ref,
                },
            )

            # ВАЖНО: дальше строить snapshot бессмысленно — нет ни одной клаузы.
            # Возвращаем пустой skeleton, чтобы воркер на следующем шаге
            # мог принять решение (в т.ч. отправить документ в карантин).
            empty_snapshot: dict[str, Any] = {
                "schema_version": 1,
                "doc_id": str(doc.id),
                "document_version_id": str(version.id),
                "built_at": datetime.now(tz=timezone.utc).isoformat(),
                "source": {
                    "layout_ref": layout_ref,
                    "layout_kind": (
                        "layout_primary_sanitized_ref"
                        if getattr(version, "layout_primary_sanitized_ref", None)
                        else "layout_primary_ref"
                    ),
                    "clause_tree_ref": clause_tree_ref,
                },
                "params": {
                    "target_tokens": target_tokens,
                    "max_tokens": max_tokens,
                    "overlap_ratio": overlap_ratio,
                },
                "chunks": {
                    "section": [],
                    "clause": [],
                    "subclause": [],
                },
            }
            return empty_snapshot

        # 4.1. Извлекаем общее число страниц из layout.metadata.
        layout_meta = layout.get("metadata") or {}
        total_pages = _extract_total_pages(layout_meta)

        # 4.2. Пробрасываем информацию о language_filter / degraded из layout в метаданные чанков.
        _propagate_language_filter(leaf_chunks, layout_meta)

        # 4.3. Добавляем position_ratio (позиция чанка в документе).
        if total_pages:
            _add_position_ratio(leaf_chunks, total_pages)

        # 5. Строим sized subclause‑чанки (по логике get_sized_chunks).
        sized_chunks = _build_sized_chunks_from_leaf(
            doc_id=doc_id,
            leaf_chunks=leaf_chunks,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
            total_pages=total_pages,
        )

        if not sized_chunks:
            logger.warning(
                "ChunkSnapshotBuilder: no sized chunks built from leaf chunks",
                extra={
                    "doc_id": str(doc_id),
                    "clause_tree_ref": clause_tree_ref,
                    "layout_ref": layout_ref,
                    "leaf_chunk_count": len(leaf_chunks),
                },
            )
            empty_snapshot: dict[str, Any] = {
                "schema_version": 1,
                "doc_id": str(doc.id),
                "document_version_id": str(version.id),
                "built_at": datetime.now(tz=timezone.utc).isoformat(),
                "source": {
                    "layout_ref": layout_ref,
                    "layout_kind": (
                        "layout_primary_sanitized_ref"
                        if getattr(version, "layout_primary_sanitized_ref", None)
                        else "layout_primary_ref"
                    ),
                    "clause_tree_ref": clause_tree_ref,
                },
                "params": {
                    "target_tokens": target_tokens,
                    "max_tokens": max_tokens,
                    "overlap_ratio": overlap_ratio,
                },
                "chunks": {
                    "section": [],
                    "clause": [],
                    "subclause": [],
                },
            }
            return empty_snapshot

        # 6. Приводим leaf‑чанки к "нормальному" виду и добавляем им summary.
        clause_chunks = _ensure_clause_metadata(doc_id, leaf_chunks)
        clause_chunks_with_summary = _add_summary(clause_chunks)

        # 7. Строим section‑чанки на основе clause‑чанков.
        #
        # build_section_chunks_from_clauses ожидает список dict с полями id/text/metadata.
        section_chunks = build_section_chunks_from_clauses(
            doc_id=str(doc_id),
            clause_chunks=clause_chunks_with_summary,
            max_tokens=1200,
        )

        # 8. Добавляем summary к subclause‑чанкам.
        subclause_chunks_with_summary = _add_summary(sized_chunks)

        # 9. Собираем финальный snapshot.
        snapshot: dict[str, Any] = {
            "schema_version": 1,
            "doc_id": str(doc.id),
            "document_version_id": str(version.id),
            "built_at": datetime.now(tz=timezone.utc).isoformat(),
            "source": {
                "layout_ref": layout_ref,
                "layout_kind": (
                    "layout_primary_sanitized_ref"
                    if getattr(version, "layout_primary_sanitized_ref", None)
                    else "layout_primary_ref"
                ),
                "clause_tree_ref": clause_tree_ref,
            },
            "params": {
                "target_tokens": target_tokens,
                "max_tokens": max_tokens,
                "overlap_ratio": overlap_ratio,
            },
            "chunks": {
                "section": section_chunks,
                "clause": clause_chunks_with_summary,
                "subclause": subclause_chunks_with_summary,
            },
        }
        return snapshot


# ---------------------------------------------------------------------------
# Вспомогательные функции: полностью совместимы с текущим DocumentContentService
# ---------------------------------------------------------------------------


def _extract_total_pages(layout_meta: dict) -> int | None:
    """
    Попытаться достать общее число страниц из metadata layout.

    Для непрофессионального программиста:
    - layout.metadata может содержать разные ключи: page_count, pages, num_pages...
    - мы пробуем несколько вариантов и возвращаем первое подходящее число > 0.
    """
    if not isinstance(layout_meta, dict):
        return None
    for key in ("page_count", "pages", "num_pages", "total_pages"):
        value = layout_meta.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _propagate_language_filter(leaf_chunks: list[dict], layout_meta: dict) -> None:
    """
    Перенести информацию о language_filter из layout в каждый чанк.

    Для непрофессионального программиста:
    - layout.metadata.language_filter содержит:
      target_language, degraded, degraded_reason и др.
    - Здесь мы аккуратно добавляем эти поля в metadata каждого чанка,
      не перетирая уже существующие значения.
    """
    lf_meta = (layout_meta.get("language_filter") or {}) if isinstance(layout_meta, dict) else {}
    lf_degraded = lf_meta.get("degraded")
    lf_reason = lf_meta.get("degraded_reason")
    lf_target_lang = lf_meta.get("target_language")

    if lf_degraded is None and lf_target_lang is None:
        return

    for ch in leaf_chunks:
        meta = ch.get("metadata") or {}
        lf = dict(meta.get("language_filter") or {})
        if lf_target_lang is not None and "target_language" not in lf:
            lf["target_language"] = lf_target_lang
        if lf_degraded is not None and "degraded" not in lf:
            lf["degraded"] = bool(lf_degraded)
        if lf_reason is not None and "degraded_reason" not in lf:
            lf["degraded_reason"] = lf_reason
        if lf:
            meta["language_filter"] = lf
            ch["metadata"] = meta


def _calc_position_ratio(
    start_page: int | None,
    end_page: int | None,
    total_pages: int | None,
) -> float | None:
    """
    Посчитать нормализованную позицию чанка в документе.

    Для непрофессионального программиста:
    - Если знаем страницу(ы) чанка и общее число страниц,
      считаем "середину" чанка и делим на длину документа.
    - Получаем число от 0.0 до 1.0:
        ~0.0  — начало документа,
        ~0.5  — середина,
        ~1.0  — конец.
    """
    if not total_pages or total_pages <= 0:
        return None

    if start_page is None and end_page is None:
        return None

    s = start_page if isinstance(start_page, int) else end_page
    e = end_page if isinstance(end_page, int) else start_page
    if s is None or e is None:
        return None

    mid = (s + e) / 2.0
    ratio = mid / float(total_pages)
    if ratio < 0.0:
        return 0.0
    if ratio > 1.0:
        return 1.0
    return ratio


def _add_position_ratio(leaf_chunks: list[dict], total_pages: int) -> None:
    """Добавить поле position_ratio во все листовые чанки, если можем его посчитать."""
    for ch in leaf_chunks:
        meta = ch.get("metadata") or {}
        start_page = meta.get("start_page")
        end_page = meta.get("end_page")
        pos = _calc_position_ratio(start_page, end_page, total_pages)
        if pos is not None:
            meta["position_ratio"] = pos
            ch["metadata"] = meta


def _build_sized_chunks_from_leaf(
    *,
    doc_id: uuid.UUID,
    leaf_chunks: list[dict],
    target_tokens: int,
    max_tokens: int,
    overlap_ratio: float,
    total_pages: int | None,
) -> list[dict]:
    """
    Построить нормализованные subclause‑чанки поверх листовых клауз.

    Логика 1:1 с DocumentContentService.get_sized_chunks, только вынесена
    в чистую функцию и сразу проставляет kind="clause"/"subclause",
    а также section_title для retrieval metadata.
    """
    SHORT_CLAUSE_MAX_TOKENS = int(target_tokens * 0.9)   # ~270 при target=300
    LONG_CLAUSE_MIN_TOKENS = int(max_tokens * 1.2)       # ~960 при max=800

    sized: list[dict] = []

    for base in leaf_chunks:
        text = base.get("text") or ""
        metadata = base.get("metadata") or {}

        if not text.strip():
            continue

        clause_uid = metadata.get("clause_uid")
        level = metadata.get("level")
        path_titles = metadata.get("path_titles") or []
        start_page = metadata.get("start_page")
        end_page = metadata.get("end_page")
        element_ids = metadata.get("element_ids") or []

        clause_token_count = count_tokens(text)

        # section_title:
        # - для clause/subclause используем верхний заголовок раздела,
        #   если path_titles заполнен;
        # - если path_titles пуст, section_title не ставим.
        section_title = path_titles[0] if path_titles else None

        if "position_ratio" in metadata:
            position_ratio = metadata.get("position_ratio")
        elif total_pages:
            position_ratio = _calc_position_ratio(start_page, end_page, total_pages)
        else:
            position_ratio = None

        def _append_whole() -> None:
            chunk_id = f"{doc_id}:{clause_uid or 'full'}:0"

            chunk_meta = {
                "doc_id": str(doc_id),
                "kind": "clause",
                "clause_uid": clause_uid,
                "title": metadata.get("title"),
                "level": level,
                "path_titles": path_titles,
                "start_page": start_page,
                "end_page": end_page,
                "element_ids": element_ids,
                "token_count": clause_token_count,
                "position_ratio": position_ratio,
            }

            if section_title is not None:
                chunk_meta["section_title"] = section_title

            sized.append(
                {
                    "id": chunk_id,
                    "text": text,
                    "metadata": chunk_meta,
                }
            )

        # 1) Короткие клаузы: вообще не режем.
        if clause_token_count <= SHORT_CLAUSE_MAX_TOKENS:
            _append_whole()
            continue

        # 2) Средние клаузы: тоже не режем, чтобы сохранить одну "юридическую мысль".
        if SHORT_CLAUSE_MAX_TOKENS < clause_token_count < LONG_CLAUSE_MIN_TOKENS:
            _append_whole()
            continue

        # 3) Только очень длинные клаузы режем на под‑чанки.
        sub_texts = split_text_to_sized_chunks(
            text=text,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
        )

        if not sub_texts:
            _append_whole()
            continue

        for sub_idx, sub_text in enumerate(sub_texts):
            if not sub_text.strip():
                continue

            sub_token_count = count_tokens(sub_text)
            chunk_id = f"{doc_id}:{clause_uid or 'full'}:{sub_idx}"

            sub_meta = {
                "doc_id": str(doc_id),
                "kind": "subclause",
                "clause_uid": clause_uid,
                "title": metadata.get("title"),
                "level": level,
                "path_titles": path_titles,
                "start_page": start_page,
                "end_page": end_page,
                "element_ids": element_ids,
                "token_count": sub_token_count,
                "position_ratio": position_ratio,
            }

            if section_title is not None:
                sub_meta["section_title"] = section_title

            sized.append(
                {
                    "id": chunk_id,
                    "text": sub_text,
                    "metadata": sub_meta,
                }
            )

    if not sized:
        logger.warning(
            "ChunkSnapshotBuilder: no sized chunks built, subclause list will be empty",
        )
    return sized


def _ensure_clause_metadata(doc_id: uuid.UUID, leaf_chunks: list[dict]) -> list[dict]:
    """
    Привести leaf‑чанки к ожидаемому виду:
    - гарантировать doc_id, kind, token_count, section_title.
    """
    out: list[dict] = []

    for ch in leaf_chunks:
        text = (ch.get("text") or "").strip()
        meta = ch.get("metadata") or {}

        if not text:
            continue

        path_titles = meta.get("path_titles") or []

        # Для clause‑чанка section_title = верхний заголовок раздела,
        # если он известен.
        section_title = path_titles[0] if path_titles else None

        meta.setdefault("doc_id", str(doc_id))
        meta.setdefault("kind", "clause")
        meta.setdefault("token_count", count_tokens(text))

        if section_title is not None and "section_title" not in meta:
            meta["section_title"] = section_title

        out.append(
            {
                "id": ch.get("id") or f"{doc_id}:{meta.get('clause_uid') or 'full'}",
                "text": text,
                "metadata": meta,
            }
        )

    return out


def _add_summary(chunks: list[dict]) -> list[dict]:
    """
    Добавить summary в metadata каждого чанка, если его ещё нет.

    Для непрофессионального программиста:
    - summary — это короткое текстовое описание чанка:
      "Payment / Payment Terms: The Lessee shall ..."
    - Оно строится на основе заголовков path_titles и самого текста чанка.
    """
    out: list[dict] = []
    for ch in chunks:
        text = ch.get("text") or ""
        meta = ch.get("metadata") or {}
        if not meta.get("summary"):
            path_titles = meta.get("path_titles") or []
            meta["summary"] = build_chunk_summary(path_titles, text)
            ch["metadata"] = meta
        out.append(ch)
    return out


