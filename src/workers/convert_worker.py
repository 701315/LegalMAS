# src/workers/convert_worker.py

"""
Convert Worker.

Назначение:
- Конвертация исходных файлов (DOC/DOCX/и др.) в PDF, чтобы дальше использовать
  существующий PDF‑пайплайн (workers.extract_document).
- Пока реализация конвертации отсутствует, воркер служит заглушкой и только логирует
  вызовы, не изменяя БД и не ставя downstream‑задачи.

Планируемый сценарий работы:
  1) Import Worker сохраняет исходный файл (DOC/DOCX/...) в MinIO
     и создаёт Document + DocumentVersion.
  2) Extract Router (services.extract_router) по filetype решает, что для этого типа
     нужно сначала выполнить конвертацию в PDF.
  3) Import Worker ставит задачу workers.convert_to_pdf с нужными параметрами.
  4) Этот воркер:
       - достаёт оригинал из MinIO;
       - конвертирует в PDF;
       - кладёт PDF в MinIO;
       - создаёт/обновляет DocumentVersion с ссылкой на PDF;
       - ставит задачу на PDF‑extractor (workers.extract_document).

Архитектура:
- Внешняя Celery‑таска convert_to_pdf — синхронная (def), как и в других воркерах.
- Внутри один раз выполняется переход sync → async через run_async.
- Асинхронное ядро convert_to_pdf_async работает под db_uow() и использует AsyncSession.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.repositories import DocumentRepository, DocumentVersionRepository
from db.uow import db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from storage.artifact_store import ArtifactStore, ArtifactPath  # ArtifactPath пока не используется, но пригодится позже

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.convert_to_pdf",
    track_job=False,
    queue="default",
)
def convert_to_pdf(
    self,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,  # <-- добавили
) -> dict:
    """
    Celery‑задача конвертации исходного файла в PDF.

    Паттерн:
    - синхронная точка входа для Celery;
    - внутри один переход в async‑код через run_async.
    """

    async def _wrapper() -> dict:
        async with db_uow() as uow:
            return await convert_to_pdf_async(
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                db=uow.session,
                run_id=run_id,  # <-- пробрасываем, пока не используем
            )

    return run_async(_wrapper())


async def convert_to_pdf_async(
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None = None,  # <-- тоже принимаем, на будущее
) -> dict:
    """
    Асинхронное ядро конвертации (пока заглушка).
    """
    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)
    store = ArtifactStore()

    doc_uuid = uuid.UUID(document_id)
    ver_uuid = uuid.UUID(document_version_id)

    # 1. Загружаем сущности из БД
    document = await doc_repo.get_by_id(doc_uuid)
    version = await ver_repo.get_by_id(ver_uuid)

    if not document or not version:
        logger.error(
            "convert_to_pdf: document or version not found",
            document_id=document_id,
            document_version_id=document_version_id,
        )
        return {"status": "error", "reason": "document_or_version_not_found"}

    logger.info(
        "convert_to_pdf called (stub)",
        document_id=document_id,
        document_version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        original_ref=version.original_ref,
        run_id=run_id,
    )

    return {
        "status": "not_implemented",
        "document_id": document_id,
        "document_version_id": document_version_id,
    }



# ─────────────────────────────────────────────────────────────────────────────
# КАК ДЕЙСТВОВАТЬ, КОГДА ПОЯВИТСЯ РЕАЛЬНЫЙ EXTRACTOR ИЛИ КОНВЕРТЕР ДЛЯ НОВОГО ТИПА
# ─────────────────────────────────────────────────────────────────────────────
#
# Ниже — пошаговая инструкция для будущего себя или коллеги,
# который будет подключать новый тип файла в пайплайн.
#
# Сценарий 1. Появился конвертер DOCX/DOC → PDF
# -------------------------------------------
#
# Цель: для doc/docx сначала делать конвертацию, потом пускать через PDF-экстрактор.
#
# Шаг 1. Реализовать конвертацию в convert_to_pdf_async
#   1.1. Взять исходный файл из MinIO:
#        - у версии документа (version.original_ref) уже есть путь к оригиналу.
#        - через ArtifactStore.get_file(...) получить байты файла.
#   1.2. Вызвать внешний инструмент конвертации:
#        - например, LibreOffice (через subprocess) или отдельный HTTP-сервис.
#        - на вход подать исходный файл, на выход получить PDF-байты.
#   1.3. Сохранить PDF в MinIO:
#        - придумать путь, например:
#              ArtifactPath.converted(tenant_id, deal_id, document_id) + ".pdf"
#        - через store.put_file(...) загрузить PDF в хранилище.
#   1.4. Обновить/создать DocumentVersion:
#        - либо обновить существующую версию, добавив ссылку на PDF (например, отдельное поле),
#        - либо создать новую версию (version_num + 1) с original_ref указывающим уже на PDF.
#   1.5. Поставить задачу на PDF-экстрактор:
#        - celery_app.send_task(
#              "workers.extract_document",
#              kwargs={
#                  "document_version_id": str(<id нужной версии>),
#                  "document_id": document_id,
#                  "deal_id": deal_id,
#                  "tenant_id": tenant_id,
#                  "run_id": None или нужный run_id,
#              },
#          )
#
# Шаг 2. Включить конвертацию для DOC/DOCX в роутере
#   2.1. Открыть services/extract_router.py.
#   2.2. В функции decide_extraction_strategy найти ветку:
#            if ft in ("docx", "doc"):
#                return ExtractRoutingDecision(
#                    action="unsupported",
#                    extractor_task=None,
#                    reason="DOC/DOCX documents require conversion to PDF before analysis (not implemented yet)",
#                )
#   2.3. Заменить её на:
#            if ft in ("docx", "doc"):
#                return ExtractRoutingDecision(
#                    action="convert_then_extract",
#                    extractor_task="workers.convert_to_pdf",
#                    reason="DOC/DOCX will be converted to PDF before analysis",
#                )
#
# Шаг 3. Обновить Import Worker (если нужно)
#   3.1. В _async_import Import Worker уже использует Extract Router.
#   3.2. Для action == "convert_then_extract" он сейчас "карантинит" документ.
#        - этот код нужно заменить на постановку задачи convert_to_pdf:
#              tasks_to_dispatch.append(
#                  {
#                      "task_name": decision.extractor_task,
#                      "kwargs": {
#                          "document_version_id": str(doc_version.id),
#                          "document_id": str(doc.id),
#                          "deal_id": deal_id,
#                          "tenant_id": tenant_id,
#                          "run_id": run_id,
#                      },
#                  }
#              )
#        - и НЕ отправлять документ в карантин.
#
# Сценарий 2. Появился "родной" extractor для типа файла (например, DOCX)
# ------------------------------------------------------------------------
#
# Цель: для docx больше НЕ конвертировать в PDF, а сразу вызывать свой extractor.
#
# Шаг 1. Реализовать новый extractor
#   1.1. Создать новый Celery-воркер (файл), например src/workers/extract_docx_worker.py.
#   1.2. В нём сделать задачу, например:
#            @celery_app.task(name="workers.extract_document_docx", ...)
#        которая:
#            - берёт исходный DOCX из MinIO;
#            - извлекает текст/структуру;
#            - сохраняет артефакты (в текстовые JSON, как это делает PDF extractor);
#            - обновляет DocumentVersion и статус документа.
#
# Шаг 2. Переключить роутер на новый extractor
#   2.1. В services/extract_router.py в decide_extraction_strategy
#        для ft == "docx" заменить логику:
#            с action="convert_then_extract" на action="extract"
#            и extractor_task="workers.extract_document_docx".
#        Пример:
#            if ft == "docx":
#                return ExtractRoutingDecision(
#                    action="extract",
#                    extractor_task="workers.extract_document_docx",
#                    reason=None,
#                )
#
# Шаг 3. Ничего не менять в Import Worker
#   3.1. Import Worker уже использует Extract Router и не знает деталей.
#   3.2. После изменения роутера docx-документы начнут автоматически
#        уходить в новый extractor, без каких-либо правок в import_worker.py.
#
# Таким образом:
#   - convert_worker.py хранит логику конвертации в PDF (одна точка доработки).
#   - extract_router.py отвечает за выбор конвертации/экстрактора.
#   - import_worker.py лишь вызывает роутер и ставит задачи в Celery.
