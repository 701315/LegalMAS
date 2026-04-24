# src/engine/content/chunk_snapshot_reader.py

from __future__ import annotations

import uuid
from typing import Any, Iterable

# anyio.to_thread.run_sync позволяет запустить синхронную (блокирующую) функцию
# в отдельном потоке, не замораживая async event loop.
# Это важно потому что ArtifactStore.get_json делает HTTP-запрос в MinIO —
# он может занять 50-500мс, и всё это время event loop был бы заморожен.
from anyio.to_thread import run_sync

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from storage.artifact_store import ArtifactStore
from core.logging import get_logger

logger = get_logger(__name__)

# Константы ожидаемой схемы snapshot'а.
# Вынесены как константы чтобы: (1) не дублировать магические строки,
# (2) при смене версии менять в одном месте.
_EXPECTED_SCOPE = "segment"
_EXPECTED_SCHEMA_VERSION = 2


class ChunkCorpusReaderV2:
    """
    ЧТЕНИЕ CHUNKS V2 (segment-aware, schema_version = 2).

    Простыми словами для непрофессионального программиста:

    - Вся информация о чанках разделена:
      * один "манифест" на весь файл (file manifest),
      * отдельные snapshots для каждого сегмента.

    - Этот класс:
      1) Находит последнюю версию документа (DocumentVersion).
      2) Берёт ссылку на file manifest (chunks_manifest_v2_ref).
      3) Грузит manifest JSON из object storage (MinIO) — асинхронно.
      4) Для каждого сегмента берёт ссылку на его snapshot (segment_chunks_ref).
      5) Грузит сегментные snapshots асинхронно и собирает единый список чанков.

    - Возвращает нормализованный список:
      [
          {
              "id": ...,
              "text": ...,
              "metadata": {...},
          }
      ]
    """

    def __init__(
        self,
        session: AsyncSession,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.session = session
        self.versions = DocumentVersionRepository(session)
        self.segments = DocumentSegmentRepository(session)
        self.artifact_store = artifact_store or ArtifactStore()

    async def load(
        self,
        doc_id: uuid.UUID,
        levels: list[str],
    ) -> list[dict[str, Any]]:
        """
        Загрузить все чанки для документа в формате v2.

        doc_id  — идентификатор документа.
        levels  — какие уровни чанков нужны (section / clause / subclause).

        Пример:
        - levels = ["clause", "subclause"]
        """
        level_set = self._normalize_levels(levels)
        if not level_set:
            return []

        # 1. Находим последнюю версию документа.
        version = await self.versions.get_latest(doc_id)
        if not version:
            return []

        # 2. Берём ссылку на file-level manifest.
        manifest_ref = getattr(version, "chunks_manifest_v2_ref", None)
        if not manifest_ref:
            # Нет манифеста — значит CHUNKS v2 ещё не построен для этого документа.
            return []

        # 3. Грузим manifest JSON из MinIO — АСИНХРОННО через _load_json_async.
        manifest = await self._load_json_async(
            ref=manifest_ref,
            context={
                "doc_id": str(doc_id),
                "version_id": str(version.id),
                "label": "file manifest",
            },
        )
        if manifest is None:
            return []

        if not isinstance(manifest, dict):
            logger.warning(
                "ChunkCorpusReaderV2: manifest is not a dict",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "manifest_type": type(manifest).__name__,
                },
            )
            return []

        # 4. Проверяем базовую структуру manifest.
        segments_meta = manifest.get("segments") or []
        if not isinstance(segments_meta, list) or not segments_meta:
            logger.warning(
                "ChunkCorpusReaderV2: manifest has no segments",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                },
            )
            return []

        # 5. Считываем сегментные записи из БД для проверки целостности.
        #    Если сегмент есть в манифесте но отсутствует в БД — это аномалия,
        #    логируем предупреждение (но продолжаем читать).
        db_segments = await self.segments.list_by_version(version.id)
        db_segments_by_id = {s.segment_id: s for s in db_segments}

        # 6. Идём по сегментам из манифеста, грузим их snapshots, собираем corpus.
        out: list[dict[str, Any]] = []

        for seg in segments_meta:
            if not isinstance(seg, dict):
                continue

            segment_id = seg.get("segment_id")
            segment_chunks_ref = seg.get("segment_chunks_ref")

            if not segment_id or not isinstance(segment_id, str):
                continue

            if not segment_chunks_ref:
                logger.warning(
                    "ChunkCorpusReaderV2: segment has no segment_chunks_ref, skipping",
                    extra={
                        "doc_id": str(doc_id),
                        "version_id": str(version.id),
                        "manifest_ref": manifest_ref,
                        "segment_id": segment_id,
                    },
                )
                continue

            # Дополнительная проверка целостности: сегмент из манифеста должен быть в БД.
            if segment_id not in db_segments_by_id:
                logger.warning(
                    "ChunkCorpusReaderV2: manifest segment not found in DB segments",
                    extra={
                        "doc_id": str(doc_id),
                        "version_id": str(version.id),
                        "segment_id": segment_id,
                        "segment_chunks_ref": segment_chunks_ref,
                    },
                )

            # Загружаем snapshot сегмента и извлекаем нужные уровни чанков.
            segment_items = await self._load_segment_snapshot(
                doc_id=doc_id,
                version_id=version.id,
                segment_id=segment_id,
                segment_chunks_ref=segment_chunks_ref,
                level_set=level_set,
            )
            out.extend(segment_items)

        return out

    async def load_segment(
        self,
        *,
        doc_id: uuid.UUID,
        segment_id: str,
        levels: list[str],
    ) -> list[dict[str, Any]]:
        """
        Загрузить чанки только для одного сегмента документа.

        Простыми словами:
        - находит последнюю версию документа;
        - читает manifest (chunks_manifest_v2_ref);
        - ищет там нужный segment_id и его segment_chunks_ref;
        - грузит snapshot этого сегмента и возвращает нормализованные чанки.

        ВАЖНО:
        - не ходит по всем сегментам, в отличие от load(...);
        - работает только для V2 (scope='segment', schema_version=2).
        """
        level_set = self._normalize_levels(levels)
        if not level_set:
            return []

        # 1. Последняя версия документа
        version = await self.versions.get_latest(doc_id)
        if not version:
            return []

        manifest_ref = getattr(version, "chunks_manifest_v2_ref", None)
        if not manifest_ref:
            # CHUNKS v2 ещё не построен
            return []

        # 2. Читаем manifest
        manifest = await self._load_json_async(
            ref=manifest_ref,
            context={
                "doc_id": str(doc_id),
                "version_id": str(version.id),
                "label": "file manifest",
            },
        )
        if manifest is None:
            return []

        if not isinstance(manifest, dict):
            logger.warning(
                "ChunkCorpusReaderV2.load_segment: manifest is not a dict",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "manifest_type": type(manifest).__name__,
                    "segment_id": segment_id,
                },
            )
            return []

        segments_meta = manifest.get("segments") or []
        if not isinstance(segments_meta, list) or not segments_meta:
            logger.warning(
                "ChunkCorpusReaderV2.load_segment: manifest has no segments",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "segment_id": segment_id,
                },
            )
            return []

        # 3. Ищем нужный сегмент
        target_chunks_ref: str | None = None
        for seg in segments_meta:
            if not isinstance(seg, dict):
                continue
            if seg.get("segment_id") == segment_id:
                target_chunks_ref = seg.get("segment_chunks_ref")
                break

        if not target_chunks_ref:
            # либо сегмент не попал в manifest, либо snapshot не записан
            logger.info(
                "ChunkCorpusReaderV2.load_segment: segment not found in manifest",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "segment_id": segment_id,
                    "manifest_ref": manifest_ref,
                },
            )
            return []

        # 4. Загружаем snapshot конкретного сегмента
        items = await self._load_segment_snapshot(
            doc_id=doc_id,
            version_id=version.id,
            segment_id=segment_id,
            segment_chunks_ref=target_chunks_ref,
            level_set=level_set,
        )
        return items or []

    # ------------------------------------------------------------------
    # Внутренние helpers
    # ------------------------------------------------------------------

    async def _load_json_async(
        self,
        ref: str,
        context: dict[str, Any],
    ) -> Any:
        """
        Загрузить JSON из MinIO в отдельном потоке (не блокируя event loop).

        Простыми словами:
        - ArtifactStore.get_json делает HTTP-запрос — это медленная операция.
        - Если вызвать её напрямую в async-коде, весь сервер "встанет" на это время.
        - run_sync запускает её в отдельном потоке, event loop остаётся свободным.

        Возвращает распарсенный объект (dict/list) или None при ошибке.
        """

        def _get() -> Any:
            return self.artifact_store.get_json(ref)

        try:
            return await run_sync(_get)
        except Exception as e:
            logger.warning(
                "ChunkCorpusReaderV2: failed to load JSON from storage",
                extra={**context, "ref": ref, "error": str(e)},
            )
            return None

    async def _load_segment_snapshot(
        self,
        *,
        doc_id: uuid.UUID,
        version_id: uuid.UUID,
        segment_id: str,
        segment_chunks_ref: str,
        level_set: set[str],
    ) -> list[dict[str, Any]]:
        """
        Загрузить snapshot одного сегмента и вернуть нормализованные чанки.

        - doc_id, version_id — только для логов.
        - segment_id — идентификатор сегмента (строка).
        - segment_chunks_ref — путь к JSON с чанками сегмента в MinIO.
        - level_set — множество нужных уровней (section / clause / subclause).
        """
        context = {
            "doc_id": str(doc_id),
            "version_id": str(version_id),
            "segment_id": segment_id,
            "label": "segment snapshot",
        }

        snapshot = await self._load_json_async(
            ref=segment_chunks_ref,
            context=context,
        )

        if snapshot is None:
            # Ошибка уже залогирована внутри _load_json_async.
            return []

        if not isinstance(snapshot, dict):
            logger.warning(
                "ChunkCorpusReaderV2: segment snapshot is not a dict",
                extra={
                    **context,
                    "segment_chunks_ref": segment_chunks_ref,
                    "snapshot_type": type(snapshot).__name__,
                },
            )
            return []

        scope = snapshot.get("scope")
        schema_version = snapshot.get("schema_version")

        # ЖЁСТКАЯ ПРОВЕРКА СХЕМЫ.
        # Если scope или schema_version не совпадают с ожидаемыми —
        # мы НЕ читаем данные дальше. Это защита от ситуации когда
        # в MinIO по ошибке окажется snapshot старого формата (V1):
        # его структура отличается от V2, и молчаливое чтение даст
        # некорректные данные без какой-либо ошибки.
        if scope != _EXPECTED_SCOPE or schema_version != _EXPECTED_SCHEMA_VERSION:
            logger.error(
                "ChunkCorpusReaderV2: unexpected segment snapshot schema — skipping segment. "
                "Expected scope='segment', schema_version=2. "
                "This segment will be excluded from checks corpus.",
                extra={
                    **context,
                    "segment_chunks_ref": segment_chunks_ref,
                    "actual_scope": scope,
                    "actual_schema_version": schema_version,
                    "expected_scope": _EXPECTED_SCOPE,
                    "expected_schema_version": _EXPECTED_SCHEMA_VERSION,
                },
            )
            return []

        chunks_by_level = snapshot.get("chunks") or {}
        if not isinstance(chunks_by_level, dict):
            return []

        out: list[dict[str, Any]] = []

        for lvl, items in chunks_by_level.items():
            if not isinstance(lvl, str):
                continue
            # Пропускаем уровни, которые не запрашивались.
            lvl_normalized = lvl.strip().lower()
            if lvl_normalized not in level_set:
                continue
            if not isinstance(items, list):
                continue

            for ch in items:
                if not isinstance(ch, dict):
                    continue

                text = (ch.get("text") or "").strip()
                # Пустые чанки пропускаем — они не несут информации для LLM.
                if not text:
                    continue

                metadata = ch.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}

                # Обогащаем metadata, чтобы downstream код не зависел от writer'а.
                if "segment_id" not in metadata:
                    metadata["segment_id"] = segment_id
                if "level" not in metadata:
                    metadata["level"] = lvl_normalized

                out.append(
                    {
                        "id": ch.get("id") or f"{segment_id}:{lvl_normalized}:{len(out)}",
                        "text": text,
                        "metadata": metadata,
                    }
                )

        return out

    @staticmethod
    def _normalize_levels(levels: Iterable[str]) -> set[str]:
        """
        Нормализовать список уровней: привести к нижнему регистру,
        убрать пробелы, отфильтровать пустые строки.
        """
        return {
            lvl.strip().lower()
            for lvl in levels
            if isinstance(lvl, str) and lvl.strip()
        }
    
    

    

    