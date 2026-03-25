# src/workers/convert_worker.py

"""
Convert Worker.

Назначение:
- Конвертация исходных файлов (DOC/DOCX/и др.) в PDF, чтобы дальше использовать
  существующий PDF‑пайплайн (workers.extract_document).

Сценарий работы:
  1) Import Worker сохраняет исходный файл (DOC/DOCX/...) в MinIO
     и создаёт Document + DocumentVersion.
  2) Extract Router (services.extract_router) по filetype решает, что для этого типа
     нужно сначала выполнить конвертацию в PDF.
  3) Import Worker ставит задачу workers.convert_to_pdf с нужными параметрами.
  4) Этот воркер:
       - достаёт оригинал из MinIO;
       - конвертирует в PDF;
       - кладёт PDF в MinIO;
       - обновляет DocumentVersion.converted_pdf_ref ссылкой на PDF;
       - ставит задачу на PDF‑extractor (workers.extract_document).

Архитектура:
- Внешняя Celery‑таска convert_to_pdf — синхронная (def), как и в других воркерах.
- Внутри один раз выполняется переход sync → async через run_async.
- Асинхронное ядро convert_to_pdf_async работает под db_uow() и использует AsyncSession.
"""

import uuid
import tempfile
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.repositories import DocumentRepository, DocumentVersionRepository
from db.uow import db_uow, UnitOfWork
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from storage.artifact_store import ArtifactStore, ArtifactPath

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
    run_id: str | None = None,
) -> dict:
    """
    Celery‑задача конвертации исходного файла в PDF.

    Паттерн:
    - синхронная точка входа для Celery;
    - внутри один переход в async‑код через run_async.
    """

    async def _wrapper() -> dict:
        async with db_uow() as uow:
            try:
                return await convert_to_pdf_async(
                    document_id=document_id,
                    document_version_id=document_version_id,
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    db=uow.session,
                    run_id=run_id,
                )
            except PermanentError as e:
                # Фатальная ошибка конвертации: помечаем документ FAILED с stage="convert".
                logger.error(
                    "Permanent error during conversion",
                    document_id=document_id,
                    document_version_id=document_version_id,
                    error=str(e),
                )
                async with db_uow() as uow_status:
                    await _mark_convert_failed(
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


async def convert_to_pdf_async(
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None = None,
) -> dict:
    """
    Асинхронное ядро конвертации DOC/DOCX → PDF.

    Контракт:
    - Берём original_ref (DOC/DOCX) из DocumentVersion.
    - Скачиваем файл из MinIO.
    - Конвертируем в PDF (через внешний инструмент/сервис).
    - Заливаем PDF в MinIO по предсказуемому пути (ArtifactPath.converted_pdf).
    - Обновляем DocumentVersion.converted_pdf_ref.
    - Ставим стандартную задачy workers.extract_document.

    В случае фатальной ошибки кидаем PermanentError — верхний уровень пометит документ FAILED.
    """
    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)
    store = ArtifactStore(settings)

    doc_uuid = uuid.UUID(document_id)
    ver_uuid = uuid.UUID(document_version_id)

    # 1. Загружаем сущности из БД
    document = await doc_repo.get_by_id(doc_uuid)
    version = await ver_repo.get_by_id(ver_uuid)

    if not document or not version:
        # Это ошибка согласованности данных: без версии/документа нельзя продолжать.
        raise PermanentError(
            f"convert_to_pdf: document or version not found "
            f"(document_id={document_id}, document_version_id={document_version_id})"
        )

    if not version.original_ref:
        # У версии нет исходного файла — конвертировать нечего.
        raise PermanentError(
            f"convert_to_pdf: missing original_ref for version {document_version_id}"
        )

    logger.info(
        "Starting DOCX/DOC → PDF conversion",
        document_id=document_id,
        document_version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        original_ref=version.original_ref,
        run_id=run_id,
    )

    # 2. Скачиваем исходный файл из MinIO (DOCX/DOC/другой офисный формат)
    src_s3_path = version.original_ref.replace(f"s3://{store.bucket}/", "")
    src_bytes = store.get_file(src_s3_path)

    # 3. Конвертируем в PDF (через внешний конвертер)
    pdf_bytes = await _convert_office_bytes_to_pdf_bytes(src_bytes)

    # 4. Кладём PDF в MinIO
    pdf_path = ArtifactPath.converted_pdf(tenant_id, deal_id, document_id)
    pdf_ref = store.put_file(pdf_path, pdf_bytes, content_type="application/pdf")

    # 5. Обновляем DocumentVersion: ссылка на сконвертированный PDF
    await ver_repo.update_refs(
        ver_uuid,
        converted_pdf_ref=pdf_ref,
    )

    logger.info(
        "DOCX/DOC → PDF conversion complete, scheduling extraction",
        document_id=document_id,
        document_version_id=document_version_id,
        pdf_ref=pdf_ref,
    )

    # 6. Ставим стандартный extract_document (Stage 4)
    from mas_queue.celery_app import celery_app as _celery  # локальный импорт на случай циклов

    _celery.send_task(
        "workers.extract_document",
        kwargs={
            "document_version_id": document_version_id,
            "document_id": document_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "run_id": run_id,
        },
    )

    # Статус документа (IN_PROGRESS/EXTRACTED) будет обновлён уже в extract_worker.
    return {
        "status": "ok",
        "document_id": document_id,
        "document_version_id": document_version_id,
        "pdf_ref": pdf_ref,
    }


async def _convert_office_bytes_to_pdf_bytes(src_bytes: bytes) -> bytes:
    """
    Конвертация офисного файла (DOCX/DOC/...) в PDF через внешний HTTP‑сервис.

    Ожидаемый протокол сервиса:

    - URL берётся из settings.DOCX_CONVERTER_URL, например:
        http://office-converter:8080/convert

    - Запрос:
        POST /convert
        Content-Type: multipart/form-data
        form-data:
          - file: бинарное содержимое исходного файла (DOCX/DOC/...)

    - Успешный ответ:
        200 OK
        Content-Type: application/pdf
        body: байты PDF

    - Ошибка:
        4xx/5xx с текстом ошибки в body (text/json).

    Пока сервис не поднят или URL не настроен — кидаем PermanentError
    с понятным текстом, чтобы было видно, что конвертация ещё не подключена.
    """
    converter_url = getattr(settings, "DOCX_CONVERTER_URL", None)
    timeout_seconds = getattr(settings, "DOCX_CONVERTER_TIMEOUT_SECONDS", 60)

    if not converter_url:
        # Инфраструктура ещё не настроена — явный и понятный сигнал.
        raise PermanentError(
            "Office → PDF conversion service is not configured. "
            "Set DOCX_CONVERTER_URL in settings and deploy your LibreOffice-based "
            "converter service behind HTTP."
        )

    # Ниже — реальный вызов сервиса.
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            files = {"file": ("input.docx", src_bytes, "application/octet-stream")}
            resp = await client.post(converter_url, files=files)

        if resp.status_code != 200:
            # Сервис ответил ошибкой — фатально для конкретного документа,
            # но не транзиентная сетевуха.
            raise PermanentError(
                f"Conversion service error: {resp.status_code} {resp.text}"
            )

        # Успешная конвертация: возвращаем байты PDF.
        return resp.content

    except httpx.TimeoutException as e:
        # Таймаут — временная ошибка, можно повторить.
        raise TransientError(f"Conversion service timeout: {e}")
    except httpx.ConnectError as e:
        # Нет соединения — временная ошибка.
        raise TransientError(f"Conversion service connection failed: {e}")
    except httpx.RequestError as e:
        # Другие сетевые ошибки — тоже временные.
        raise TransientError(f"Conversion service request error: {e}")


async def _mark_convert_failed(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    message: str,
    run_id: Optional[uuid.UUID],
) -> None:
    """
    Отдельный простой UoW для перевода документа в статус FAILED
    на стадии convert, с заполнением processing_error_details.
    """
    repo = DocumentRepository(uow.session)
    await repo.set_failed(
        document_uuid,
        stage="convert",
        message=message,
        reason="conversion_error",
        run_id=run_id,
    )


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
