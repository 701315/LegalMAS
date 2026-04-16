# src/engine/content/chunk_snapshot_reader.py

from __future__ import annotations

import uuid
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from storage.artifact_store import ArtifactStore
from core.logging import get_logger

logger = get_logger(__name__)


class ChunkCorpusReaderV2:
    """
    ЧТЕНИЕ CHUNKS V2 (segment-aware, schema_version = 2).

    Простыми словами для непрофессионального программиста:

    - Вся информация о чанках теперь разделена:
      * один "манифест" на весь файл (file manifest),
      * отдельные snapshots для каждого сегмента.

    - Этот класс:
      1) Находит последнюю версию документа (DocumentVersion).
      2) Берёт ссылку на file manifest (chunks_manifest_v2_ref).
      3) Грузит manifest JSON из object storage.
      4) Для каждого сегмента берёт ссылку на его snapshot (segment_chunks_ref).
      5) Грузит сегментные snapshots и собирает единый список чанков.

    - Возвращает такой же нормализованный список, как и legacy-reader:
      [
          {
              "id": ...,
              "text": ...,
              "metadata": {...},  # но тут уже есть segment-aware поля
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
            # Нет манифеста — значит CHUNKS v2 ещё не построен.
            return []

        # 3. Грузим manifest JSON из object storage.
        manifest = self._load_manifest(manifest_ref, doc_id, version.id)
        if manifest is None:
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

        # 5. Считываем сегментные записи из БД (проверка целостности, если нужно).
        #    Сейчас мы используем в основном данные манифеста, потому что в нём уже есть segment_chunks_ref.
        #    Репозиторий можно использовать для дополнительных проверок или для случаев, когда ref ещё не проставлен.
        db_segments = await self.segments.list_by_version(version.id)
        db_segments_by_id = {s.segment_id: s for s in db_segments}

        # 6. Идём по сегментам из манифеста, грузим их snapshots и собираем единый corpus.
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

            # Дополнительная проверка: сегмент из манифеста должен быть в БД.
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

            segment_items = self._load_segment_snapshot(
                doc_id=doc_id,
                version_id=version.id,
                segment_id=segment_id,
                segment_chunks_ref=segment_chunks_ref,
                level_set=level_set,
            )
            out.extend(segment_items)

        return out

    @staticmethod
    def _normalize_levels(levels: Iterable[str]) -> set[str]:
        """
        Простой helper: нормализует список уровней чанков.
        """
        return {
            lvl.strip().lower()
            for lvl in levels
            if isinstance(lvl, str) and lvl.strip()
        }

    def _load_manifest(
        self,
        manifest_ref: str,
        doc_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        """
        Загрузить file-level manifest (chunks_manifest_v2.json) из object storage.

        Возвращает dict или None, если что-то пошло не так.
        """
        try:
            manifest = self.artifact_store.get_json(manifest_ref)
        except Exception as e:
            logger.warning(
                "ChunkCorpusReaderV2: failed to load file manifest",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version_id),
                    "manifest_ref": manifest_ref,
                    "error": str(e),
                },
            )
            return None

        if not isinstance(manifest, dict):
            logger.warning(
                "ChunkCorpusReaderV2: manifest is not a dict",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version_id),
                    "manifest_ref": manifest_ref,
                    "manifest_type": type(manifest).__name__,
                },
            )
            return None

        return manifest

    def _load_segment_snapshot(
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

        - doc_id, version_id — для логов и проверок.
        - segment_id — идентификатор сегмента (строка).
        - segment_chunks_ref — ссылка на JSON с чанками сегмента.
        - level_set — какие уровни чанков нужны.
        """
        try:
            snapshot = self.artifact_store.get_json(segment_chunks_ref)
        except Exception as e:
            logger.warning(
                "ChunkCorpusReaderV2: failed to load segment snapshot",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version_id),
                    "segment_id": segment_id,
                    "segment_chunks_ref": segment_chunks_ref,
                    "error": str(e),
                },
            )
            return []

        if not isinstance(snapshot, dict):
            logger.warning(
                "ChunkCorpusReaderV2: segment snapshot is not a dict",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version_id),
                    "segment_id": segment_id,
                    "segment_chunks_ref": segment_chunks_ref,
                    "snapshot_type": type(snapshot).__name__,
                },
            )
            return []

        # Проверяем базовые поля snapshot (по желанию можно сделать строгую проверку schema_version/scope).
        scope = snapshot.get("scope")
        schema_version = snapshot.get("schema_version")
        if scope != "segment" or schema_version != 2:
            logger.warning(
                "ChunkCorpusReaderV2: unexpected segment snapshot schema",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version_id),
                    "segment_id": segment_id,
                    "segment_chunks_ref": segment_chunks_ref,
                    "scope": scope,
                    "schema_version": schema_version,
                },
            )

        chunks_by_level = (snapshot.get("chunks") or {})
        if not isinstance(chunks_by_level, dict):
            return []

        out: list[dict[str, Any]] = []

        for lvl, items in chunks_by_level.items():
            if not isinstance(lvl, str):
                continue
            if lvl.strip().lower() not in level_set:
                continue
            if not isinstance(items, list):
                continue

            for ch in items:
                if not isinstance(ch, dict):
                    continue

                text = (ch.get("text") or "").strip()
                if not text:
                    continue

                metadata = ch.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}

                out.append(
                    {
                        "id": ch.get("id"),
                        "text": text,
                        "metadata": metadata,
                    }
                )

        return out
    

    