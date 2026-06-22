# src/engine/content/chunk_snapshot_reader.py

"""
Chunk snapshot reader v2: чтение materialized chunk corpus из segment snapshot'ов.

Простыми словами для непрофессионального программиста:

- CHUNKS v2 хранит corpus не одним большим файлом, а в двух слоях:
  1) file manifest — список сегментов документа и ссылок на их snapshot'ы;
  2) segment snapshot — реальные чанки конкретного логического сегмента.

- Этот модуль:
  - находит нужную версию документа;
  - читает file manifest из object storage;
  - находит segment_chunks_ref для каждого сегмента;
  - читает segment snapshot'ы;
  - возвращает плоский список чанков в wire-формате:
      {"id": ..., "text": ..., "metadata": {...}}

Архитектурно важно:
- Это transport / storage reader, а НЕ retrieval-policy слой.
- Reader не решает, какие уровни "правильные" для checks;
  он просто читает те уровни, которые запросил caller и которые
  materialized в snapshot["chunks"].
- Поэтому reader одинаково поддерживает:
    * section
    * clause
    * subclause
    * legal_unit
  и любые будущие уровни, если они записаны в CHUNKS v2 snapshot.

P8.8d — Retrieval Truth Migration:
- После migration retrieval truth переключён на legal_unit-based corpus.
- Но это решение принимается НЕ здесь, а выше:
    * в DocumentContentService,
    * в check planning / retrieval orchestration.
- Сам reader остаётся универсальным и metadata-transparent:
  он не фильтрует и не переписывает semantic/legal-unit поля,
  а только безопасно доставляет их из storage в runtime.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

# anyio.to_thread.run_sync позволяет запустить синхронную (блокирующую) функцию
# в отдельном потоке, не замораживая async event loop.
# Это важно потому что ArtifactStore.get_json делает HTTP-запрос в MinIO —
# он может занять 50-500мс, и всё это время event loop был бы заморожен.
from anyio.to_thread import run_sync
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from storage.artifact_store import ArtifactStore

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
      1) Находит версию документа (latest или конкретную по version_id).
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

    Важно:
    - Reader не привязан жёстко только к section/clause/subclause:
      он читает любые уровни, которые materialized в snapshot["chunks"].
      После P8.8d это включает также новый retrieval level `legal_unit`.
    - Все новые поля metadata проходят через reader без изменений —
      reader не фильтрует metadata.
    - Для чтения конкретной версии используй version_id параметр в
      load() и load_segment().
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
        *,
        version_id: uuid.UUID | None = None,
        enrichment_sidecars_by_segment: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Загрузить все чанки для документа в формате v2.

        doc_id     — идентификатор документа.
        levels     — какие уровни чанков нужны
                     (например section / clause / subclause / legal_unit).
        version_id — если задан, читаем конкретную версию;
                     если None — читаем последнюю (latest).

        Для непрофессионального программиста:
        - Обычно вызывают без version_id — тогда читаем последнюю версию.
        - Если нужна конкретная версия (например для аудита) — передаём version_id.

        Пример:
        - levels = ["legal_unit", "section"]
        """
        level_set = self._normalize_levels(levels)
        if not level_set:
            return []

        # 1. Находим версию документа.
        if version_id is not None:
            version = await self.versions.get_by_id(version_id)
            if not version or version.document_id != doc_id:
                logger.warning(
                    "ChunkCorpusReaderV2.load: version not found or doc_id mismatch",
                    extra={
                        "doc_id": str(doc_id),
                        "version_id": str(version_id),
                    },
                )
                return []
        else:
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
            # Если передан enrichment_sidecars_by_segment, применяем
            # runtime enrichment projection для каждого сегмента отдельно.
            segment_enrichment_sidecar: dict[str, Any] | None = None
            if enrichment_sidecars_by_segment:
                segment_enrichment_sidecar = enrichment_sidecars_by_segment.get(segment_id)

            segment_enrichment_index = self._build_enrichment_index(
                segment_enrichment_sidecar
            )

            segment_items = await self._load_segment_snapshot(
                doc_id=doc_id,
                version_id=version.id,
                segment_id=segment_id,
                segment_chunks_ref=segment_chunks_ref,
                level_set=level_set,
                enrichment_index=segment_enrichment_index,
            )
            out.extend(segment_items)

        return out

    async def load_segment(
        self,
        *,
        doc_id: uuid.UUID,
        segment_id: str,
        levels: list[str],
        version_id: uuid.UUID | None = None,
        enrichment_sidecar: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Загрузить чанки только для одного сегмента документа.

        Простыми словами:
        - находит версию документа (latest или конкретную по version_id);
        - читает manifest (chunks_manifest_v2_ref);
        - ищет там нужный segment_id и его segment_chunks_ref;
        - грузит snapshot этого сегмента и возвращает нормализованные чанки.

        Параметры:
        - doc_id:      UUID документа
        - segment_id:  ID логического сегмента (строка)
        - levels:      нужные уровни чанков
                       (например legal_unit / section / clause / subclause)
        - version_id:  если задан — читаем конкретную версию;
                       если None — читаем последнюю.

        ВАЖНО:
        - не ходит по всем сегментам, в отличие от load(...);
        - работает только для V2 (scope='segment', schema_version=2).

        Для непрофессионального программиста:
        - Раньше этот метод всегда брал get_latest() — это создавало риск
          прочитать не ту версию если caller уже нашёл нужную version по version_id.
        - Теперь можно явно передать version_id чтобы читать именно ту версию.
        """
        level_set = self._normalize_levels(levels)
        if not level_set:
            return []

        # 1. Находим версию документа
        if version_id is not None:
            version = await self.versions.get_by_id(version_id)
            if not version or version.document_id != doc_id:
                logger.warning(
                    "ChunkCorpusReaderV2.load_segment: version not found or doc_id mismatch",
                    extra={
                        "doc_id": str(doc_id),
                        "version_id": str(version_id),
                        "segment_id": segment_id,
                    },
                )
                return []
        else:
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

        # Build enrichment index if sidecar provided.
        # This allows runtime projection of enriched metadata onto chunk metadata
        # without mutating the baseline chunk snapshot artifact.
        enrichment_index = self._build_enrichment_index(enrichment_sidecar)

        # 4. Загружаем snapshot конкретного сегмента
        items = await self._load_segment_snapshot(
            doc_id=doc_id,
            version_id=version.id,
            segment_id=segment_id,
            segment_chunks_ref=target_chunks_ref,
            level_set=level_set,
            enrichment_index=enrichment_index,
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
        enrichment_index: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Загрузить snapshot одного сегмента и вернуть нормализованные чанки.

        - doc_id, version_id — только для логов.
        - segment_id — идентификатор сегмента (строка).
        - segment_chunks_ref — путь к JSON с чанками сегмента в MinIO.
        - level_set — множество нужных уровней
          (например section / clause / subclause / legal_unit).

        Важно:
        - Все поля metadata из chunk snapshot передаются downstream без изменений.
        - Это включает semantic/citability поля, legal-unit поля и другие
          retrieval-specific metadata.
        - Reader только добавляет segment_id и chunk_kind если их нет в metadata.
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
            logger.warning(
                "ChunkCorpusReaderV2: segment snapshot has invalid chunks payload",
                extra={
                    **context,
                    "segment_chunks_ref": segment_chunks_ref,
                    "chunks_type": type(chunks_by_level).__name__,
                },
            )
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

                # Обогащаем metadata только если поля отсутствуют.
                # НЕ перезаписываем существующие поля — они могут содержать
                # данные, записанные при chunking.
                if "segment_id" not in metadata:
                    metadata["segment_id"] = segment_id
                if "chunk_kind" not in metadata:
                    metadata["chunk_kind"] = lvl_normalized

                # ── Runtime enrichment projection ──────────────────────────
                # For legal_unit chunks: apply enriched semantic metadata from
                # enrichment sidecar onto chunk metadata at read time.
                # This avoids mutating baseline chunk snapshot artifacts while
                # making clause_function / unit_type / topic_tags available to
                # retrieval engine scoring and playbook excluded_unit_types filter.
                #
                # Invariants:
                # - Only legal_unit chunks carry effective_uid identity for projection.
                # - Never overwrite with None / "unknown" / empty.
                # - Graceful: enrichment_index absent → no projection, no error.
                if lvl_normalized == "legal_unit" and enrichment_index:
                    effective_uid = metadata.get("effective_uid")
                    if effective_uid and effective_uid in enrichment_index:
                        enriched = enrichment_index[effective_uid]

                        enriched_cf = enriched.get("clause_function")
                        if enriched_cf and str(enriched_cf).strip().lower() not in (
                            "", "unknown"
                        ):
                            metadata["clause_function"] = enriched_cf

                        enriched_ut = enriched.get("unit_type")
                        if enriched_ut and str(enriched_ut).strip().lower() not in (
                            "", "unknown"
                        ):
                            metadata["unit_type"] = enriched_ut

                        enriched_tags = enriched.get("topic_tags")
                        if isinstance(enriched_tags, list) and enriched_tags:
                            metadata["topic_tags"] = enriched_tags

                        metadata["enrichment_status"] = enriched.get("enrichment_status")
                        metadata["enrichment_projected"] = True

                out.append(
                    {
                        "id": ch.get("id") or f"{segment_id}:{lvl_normalized}:{len(out)}",
                        "text": text,
                        "metadata": metadata,
                    }
                )

        return out

    @staticmethod
    def _build_enrichment_index(
        enrichment_sidecar: dict[str, Any] | None,
    ) -> dict[str, dict[str, Any]]:
        """
        Build unit_id → enriched_fields index from enrichment sidecar.

        Used for runtime projection of enriched metadata onto chunk metadata.
        Baseline chunk snapshot artifacts are never mutated.

        Rules:
        - status=applied: use effective layer (post-LLM enrichment).
        - status=no_change: use effective layer (confirmed by LLM).
        - status=failed/skipped: use base layer (deterministic baseline).

        Returns empty dict if sidecar is None, malformed, or has no enrichments.
        """
        if not isinstance(enrichment_sidecar, dict):
            return {}

        enrichments = enrichment_sidecar.get("enrichments")
        if not isinstance(enrichments, list) or not enrichments:
            return {}

        index: dict[str, dict[str, Any]] = {}

        for item in enrichments:
            if not isinstance(item, dict):
                continue
            unit_id = item.get("unit_id")
            if not unit_id:
                continue

            status = str(item.get("status") or "").strip()
            effective = item.get("effective") or {}
            base = item.get("base") or {}

            # For applied/no_change: use effective (post-enrichment).
            # For failed/skipped/unknown: use base (deterministic baseline).
            source = effective if status in ("applied", "no_change") else base

            clause_function = source.get("clause_function")
            unit_type = source.get("unit_type")
            topic_tags = source.get("topic_tags")

            index[unit_id] = {
                "clause_function": clause_function,
                "unit_type": unit_type,
                "topic_tags": topic_tags if isinstance(topic_tags, list) else [],
                "enrichment_status": status,
            }

        return index


    @staticmethod
    def _normalize_levels(levels: Iterable[str]) -> set[str]:
        """
        Нормализовать список уровней: привести к нижнему регистру,
        убрать пробелы, отфильтровать пустые строки.

        Важно:
        - Reader не навязывает whitelist уровней.
        - Если уровень materialized в snapshot["chunks"], reader сможет
          его прочитать.
        """
        return {lvl.strip().lower() for lvl in levels if isinstance(lvl, str) and lvl.strip()}
    
    
