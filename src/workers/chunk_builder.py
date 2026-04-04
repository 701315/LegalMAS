# src/workers/chunk_builder.py

"""
Chunk Builder Worker.

Назначение:
- Прочитать из MinIO макет документа и clause_tree.
- Построить canonical snapshot чанков (section / clause / subclause) через
  отдельный сервис ChunkSnapshotBuilder.
- Сохранить snapshot в MinIO и обновить ссылку chunks_ref в DocumentVersion.
- При необходимости обновить статус документа (structured -> chunked),
  либо оставить STRUCTURED, если ты не хочешь вводить отдельный статус.
- В будущем: запускать downstream-задачи, которым нужны готовые чанки.

Архитектурный паттерн:
- Внешняя функция Celery‑таски остаётся синхронной (def), чтобы Celery
  корректно работал в prefork‑модели.
- Вся асинхронная логика (БД, MinIO) находится в _build_chunks_async()
  и вызывается из таски через безопасный переход sync → async (run_async + db_uow),
  как в extract_worker и structure_builder.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import db_uow, UnitOfWork
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from storage.artifact_store import ArtifactPath, ArtifactStore

# ВАЖНО:
# ChunkSnapshotBuilder мы создадим в отдельном модуле engine/content/chunk_snapshot_builder.py.
# Здесь мы только используем его интерфейс.
from engine.content.chunk_snapshot_builder import ChunkSnapshotBuilder  # noqa: F401

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_chunks",
    queue="default",
)
def build_chunks(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
    **kwargs: Any,
) -> dict:
    """
    Sync Celery entry point для построения чанков.

    Для непрофессионального программиста:
    - Celery вызывает ЭТУ функцию как обычную (синхронную).
    - Внутри мы один раз "ныряем" в async-мир через run_async(_wrapper()).
    - Все обращения к БД и MinIO происходят уже внутри _build_chunks_async().
    """

    async def _wrapper() -> dict:
        try:
            async with db_uow() as uow:
                return await _build_chunks_async(
                    document_version_id=document_version_id,
                    document_id=document_id,
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    uow=uow,
                )
        except PermanentError as e:
            # Если ошибка "постоянная" (например, нет layout или clause_tree),
            # логируем её и переводим документ в FAILED со stage="chunking".
            logger.error(
                "Permanent error during chunk building",
                document_id=document_id,
                version_id=document_version_id,
                error=str(e),
            )
            async with db_uow() as uow_status:
                await _mark_failed(
                    uow_status,
                    document_uuid=uuid.UUID(document_id),
                    message=str(e),
                    run_id=uuid.UUID(run_id) if run_id else None,
                )
            return {
                "status": DocumentStatus.FAILED.value,
                "document_id": document_id,
                "error": str(e),
            }

    return run_async(_wrapper())


async def _build_chunks_async(
    *,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None,
    uow: UnitOfWork,
) -> dict:
    """
    Основная асинхронная логика построения чанков.

    Для непрофессионального программиста:
    - Здесь мы:
      1) проверяем, что есть нужные артефакты (layout + clause_tree);
      2) строим snapshot чанков через ChunkSnapshotBuilder;
      3) сохраняем JSON в MinIO;
      4) обновляем ссылку chunks_ref в DocumentVersion;
      5) обновляем статус документа (опционально).
    """

    start = time.time()
    store = ArtifactStore(settings)

    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)

    v_id = uuid.UUID(document_version_id)
    d_id = uuid.UUID(document_id)

    # 1. Загрузка версии и документа из БД
    version = await ver_repo.get_by_id(v_id)
    if not version:
        raise PermanentError(f"DocumentVersion {v_id} not found")

    doc = await doc_repo.get_by_id(d_id)
    if not doc:
        raise PermanentError(f"Document {d_id} not found")

    # Идемпотентность:
    # Если у версии уже есть chunks_ref, можно:
    # - либо сразу вернуть, не пересчитывая,
    # - либо пересобирать принудительно (например, при смене логики chunking).
    # Для простоты сейчас: если chunks_ref есть — просто логируем и выходим.
    if getattr(version, "chunks_ref", None):
        logger.info(
            "Chunks snapshot already exists for version, skipping rebuild",
            document_id=str(doc.id),
            version_id=str(version.id),
            chunks_ref=version.chunks_ref,
        )
        return {
            "document_id": str(doc.id),
            "document_version_id": str(version.id),
            "chunks_ref": version.chunks_ref,
            "skipped": True,
        }

    # Проверяем, что структура уже построена (без clause_tree чанки не построить)
    if not getattr(version, "clause_tree_ref", None):
        raise PermanentError(
            f"Cannot build chunks: clause_tree_ref is missing for version {v_id}"
        )

    # 2. Построение snapshot чанков через отдельный сервис
    # ChunkSnapshotBuilder повторяет логику DocumentContentService.get_hierarchical_chunks,
    # но возвращает один JSON-объект для сохранения.
    snapshot_builder = ChunkSnapshotBuilder(store=store)
    snapshot = await snapshot_builder.build_snapshot(
        session=uow.session,
        doc_id=d_id,
        # target_tokens / max_tokens / overlap_ratio можно вынести в настройки
        target_tokens=300,
        max_tokens=800,
        overlap_ratio=0.15,
    )

    # 3. Сохраняем snapshot в MinIO по единому пути ArtifactPath.chunks(...)
    chunks_path = ArtifactPath.chunks(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=str(doc.id),
    )
    chunks_ref = store.put_json(chunks_path, snapshot)

    # 4. Обновляем ссылку в DocumentVersion
    await ver_repo.update_refs(
        version_id=v_id,
        chunks_ref=chunks_ref,
    )

    # 5. Обновляем статус документа при необходимости.
    #
    # Варианты:
    # - если хочешь отдельный статус CHUNKED — можно добавить его в DocumentStatus
    #   и использовать здесь;
    # - либо оставить STRUCTURED, считая чанки частью "структурирования".
    #
    # Сейчас выберем второй вариант: если документ уже STRUCTURED,
    # статус не меняем; если был STRUCTURED/CLASSIFIED/ANALYZING — тоже не трогаем.
    if doc.status == DocumentStatus.STRUCTURED.value:
        # Статус уже подходящий, просто очищаем ошибки (если были).
        await doc_repo.update_status(
            doc.id,
            DocumentStatus.STRUCTURED.value,
            processing_error_details=None,
        )

    duration = round(time.time() - start, 2)
    logger.info(
        "Chunks snapshot built and stored",
        document_id=str(doc.id),
        version_id=str(version.id),
        chunks_ref=chunks_ref,
        duration_seconds=duration,
    )

    # 6. (Опционально) можно запустить downstream-задачу,
    #    если есть что-то, что должно запускаться только при наличии чанков.
    #    На первом шаге это не делаем, чтобы не менять поведение пайплайна.

    return {
        "document_id": str(doc.id),
        "document_version_id": str(version.id),
        "chunks_ref": chunks_ref,
        "duration_seconds": duration,
    }


async def _mark_failed(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    message: str,
    run_id: uuid.UUID | None,
) -> None:
    """
    Отдельный простой UoW для перевода документа в статус FAILED
    с заполнением processing_error_details, если чанки не смогли построиться.

    Для непрофессионального программиста:
    - Этот helper очень похож на _mark_failed в extract_worker/structure_builder.
    - Мы фиксируем, что именно "chunking" сломался, чтобы фронт и логи
      могли показать понятную причину.
    """
    doc_repo = DocumentRepository(uow.session)
    await doc_repo.set_failed(
        document_uuid,
        stage="chunking",
        message=message,
        reason="chunking_error",
        run_id=run_id,
    )


    