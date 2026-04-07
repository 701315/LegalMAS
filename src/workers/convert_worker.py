# src/workers/convert_worker.py

"""
Convert Worker.

Назначение:
- Конвертация исходных офисных документов (DOC/DOCX/RTF/ODT и т.п.) в PDF,
  чтобы дальше документ шёл по единому PDF-пайплайну.

Позиция в пайплайне:
- import -> convert_to_pdf -> build_primary_language_source -> extract -> pii -> structure -> ...

Контракт стадии:
- На входе DocumentVersion.original_ref должен указывать на исходный офисный файл в S3/MinIO.
- На выходе DocumentVersion.converted_pdf_ref должен указывать на успешно сохранённый PDF.
- Этот воркер НЕ диспатчит следующую Celery-задачу напрямую.
- После успешного flush/verify/commit воркер может только ретриггернуть оркестратор,
  чтобы тот централизованно решил, можно ли запускать следующую стадию.

Ключевые архитектурные правила:
- Один sync->async переход через run_async.
- Все изменения БД делаются внутри одного UnitOfWork.
- retrigger_run_pipeline вызывается только после подтверждённого commit.
- Ошибки делятся на:
  * TransientError  -> retry через MASBaseTask;
  * PermanentError  -> документ переводится в FAILED на стадии convert.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.repositories import DocumentRepository, DocumentVersionRepository
from db.uow import UnitOfWork, db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.run_orchestrator_trigger import retrigger_run_pipeline
from storage.artifact_store import ArtifactPath, ArtifactStore

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
    Sync Celery entrypoint.

    Поведение:
    - выполняет конвертацию офисного файла в PDF;
    - сохраняет converted_pdf_ref;
    - при успехе будит оркестратор только после commit;
    - при PermanentError помечает документ FAILED на стадии convert;
    - при TransientError отдаёт управление retry-механизму MASBaseTask.
    """

    async def _wrapper() -> dict:
        async with db_uow() as uow:
            return await convert_to_pdf_async(
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                db=uow.session,
                run_id=run_id,
            )

    try:
        result = run_async(_wrapper())

    except TransientError as e:
        logger.warning(
            "Transient error during conversion; task should be retried",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            error=str(e),
        )
        raise

    except PermanentError as e:
        logger.error(
            "Permanent error during conversion",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            error=str(e),
        )
        run_async(
            _mark_convert_failed_wrapper(
                document_id=document_id,
                message=str(e),
                run_id=run_id,
            )
        )
        return {
            "status": DocumentStatus.FAILED.value,
            "document_id": document_id,
            "document_version_id": document_version_id,
            "error": str(e),
            "committed": False,
        }

    if run_id and result.get("committed") is True:
        logger.info(
            "Conversion committed, retriggering run pipeline",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            converted_pdf_ref=result.get("pdf_ref"),
        )
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
        )

    return result


async def convert_to_pdf_async(
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None = None,
) -> dict:
    """
    Асинхронное ядро стадии convert.

    Шаги:
    1. Проверить наличие документа и версии.
    2. Проверить наличие original_ref.
    3. Скачать исходный офисный файл из MinIO.
    4. Отправить его во внешний converter service.
    5. Провалидировать, что ответ действительно PDF.
    6. Сохранить PDF в MinIO.
    7. Обновить converted_pdf_ref в DocumentVersion.
    8. Сделать flush -> reload -> verify -> commit.
    9. Вернуть committed=True только после успешного commit.
    """
    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)
    store = ArtifactStore(settings)

    doc_uuid = uuid.UUID(document_id)
    ver_uuid = uuid.UUID(document_version_id)

    document = await doc_repo.get_by_id(doc_uuid)
    version = await ver_repo.get_by_id(ver_uuid)

    if not document or not version:
        raise PermanentError(
            "convert_to_pdf: document or version not found "
            f"(document_id={document_id}, document_version_id={document_version_id})"
        )

    original_ref = getattr(version, "original_ref", None)
    if not original_ref:
        raise PermanentError(
            f"convert_to_pdf: missing original_ref for version {document_version_id}"
        )

    origin_filetype = (getattr(version, "origin_filetype", None) or "").lower()
    existing_converted_pdf_ref = getattr(version, "converted_pdf_ref", None)

    logger.info(
        "Starting office-to-PDF conversion",
        document_id=document_id,
        document_version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
        original_ref=original_ref,
        origin_filetype=origin_filetype,
        existing_converted_pdf_ref=existing_converted_pdf_ref,
    )

    try:
        src_s3_path = _s3_ref_to_store_path(original_ref, store.bucket)
        src_bytes = store.get_file(src_s3_path)
    except TransientError:
        raise
    except Exception as e:
        logger.exception(
            "Failed to read original source file for conversion",
            document_id=document_id,
            document_version_id=document_version_id,
            original_ref=original_ref,
            error=str(e),
        )
        raise PermanentError(
            f"convert_to_pdf: failed to read original source file: {e}"
        )

    if not src_bytes:
        raise PermanentError(
            f"convert_to_pdf: original source file is empty for version {document_version_id}"
        )

    filename = _build_converter_filename(version)
    pdf_bytes = await _convert_office_bytes_to_pdf_bytes(
        src_bytes=src_bytes,
        filename=filename,
    )

    if not pdf_bytes:
        raise PermanentError(
            f"convert_to_pdf: converter returned empty PDF body for version {document_version_id}"
        )

    pdf_path = ArtifactPath.converted_pdf(tenant_id, deal_id, document_id)
    pdf_ref = store.put_file(
        pdf_path,
        pdf_bytes,
        content_type="application/pdf",
    )

    updated_version = await ver_repo.update_refs(
        ver_uuid,
        converted_pdf_ref=pdf_ref,
    )
    if not updated_version:
        raise PermanentError(
            "convert_to_pdf: failed to update converted_pdf_ref "
            f"for version {document_version_id}"
        )

    await db.flush()

    refreshed_version = await ver_repo.get_by_id(ver_uuid)
    refreshed_converted_ref = (
        getattr(refreshed_version, "converted_pdf_ref", None)
        if refreshed_version
        else None
    )

    if not refreshed_version:
        raise TransientError(
            f"convert_to_pdf: version disappeared after flush for {document_version_id}"
        )

    if not refreshed_converted_ref:
        raise TransientError(
            "convert_to_pdf: converted_pdf_ref is not visible after flush "
            f"for version {document_version_id}"
        )

    if refreshed_converted_ref != pdf_ref:
        raise TransientError(
            "convert_to_pdf: converted_pdf_ref mismatch after flush "
            f"for version {document_version_id}: "
            f"expected={pdf_ref}, actual={refreshed_converted_ref}"
        )

    await db.commit()

    logger.info(
        "Office-to-PDF conversion committed successfully",
        document_id=document_id,
        document_version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
        pdf_ref=pdf_ref,
    )

    return {
        "status": "converted",
        "document_id": document_id,
        "document_version_id": document_version_id,
        "pdf_ref": pdf_ref,
        "committed": True,
    }


def _s3_ref_to_store_path(ref: str, bucket: str) -> str:
    """
    Преобразовать S3 URI вида s3://bucket/path/to/file.ext в path/to/file.ext
    с жёсткой валидацией bucket-prefix.
    """
    prefix = f"s3://{bucket}/"
    if not ref or not ref.startswith(prefix):
        raise PermanentError(
            f"Invalid S3 ref for bucket '{bucket}': {ref}"
        )
    return ref[len(prefix):]


def _build_converter_filename(version) -> str:
    """
    Построить имя файла для multipart upload в converter service.

    Почему это важно:
    - некоторые конвертеры/LibreOffice-обёртки ориентируются на extension;
    - передавать всегда 'input.docx' неправильно для .doc/.rtf/.odt и т.д.
    """
    origin_filetype = (getattr(version, "origin_filetype", None) or "").strip().lower()
    original_name = (
        getattr(version, "original_filename", None)
        or getattr(version, "filename", None)
        or getattr(version, "source_filename", None)
        or ""
    )

    if original_name:
        base = os.path.basename(original_name)
        if "." in base:
            return base

    ext = origin_filetype if origin_filetype else "bin"
    return f"input.{ext}"


async def _convert_office_bytes_to_pdf_bytes(
    *,
    src_bytes: bytes,
    filename: str,
) -> bytes:
    """
    Конвертация офисного файла в PDF через внешний HTTP-сервис.

    Требования к ответу сервиса:
    - HTTP 200
    - Content-Type совместим с application/pdf
    - body непустой
    """
    converter_url = getattr(settings, "DOCX_CONVERTER_URL", None)
    timeout_seconds = getattr(settings, "DOCX_CONVERTER_TIMEOUT_SECONDS", 60)

    if not converter_url:
        raise PermanentError(
            "Office-to-PDF conversion service is not configured. "
            "Set DOCX_CONVERTER_URL in settings and deploy the converter service."
        )

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            files = {
                "file": (
                    filename,
                    src_bytes,
                    "application/octet-stream",
                )
            }
            resp = await client.post(converter_url, files=files)

    except httpx.TimeoutException as e:
        raise TransientError(f"Conversion service timeout: {e}") from e
    except httpx.ConnectError as e:
        raise TransientError(f"Conversion service connection failed: {e}") from e
    except httpx.RequestError as e:
        raise TransientError(f"Conversion service request error: {e}") from e

    if resp.status_code != 200:
        body_preview = (resp.text or "")[:1000]
        raise PermanentError(
            f"Conversion service error: {resp.status_code} {body_preview}"
        )

    content_type = (resp.headers.get("content-type") or "").lower()
    if "application/pdf" not in content_type:
        body_preview = (resp.text or "")[:500]
        raise PermanentError(
            "Conversion service returned unexpected content-type: "
            f"{content_type or '<empty>'}; body_preview={body_preview}"
        )

    if not resp.content:
        raise PermanentError("Conversion service returned empty PDF body")

    return resp.content


async def _mark_convert_failed_wrapper(
    document_id: str,
    message: str,
    run_id: str | None,
) -> None:
    async with db_uow() as uow:
        await _mark_convert_failed(
            uow,
            document_uuid=uuid.UUID(document_id),
            message=message,
            run_id=uuid.UUID(run_id) if run_id else None,
        )


async def _mark_convert_failed(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    message: str,
    run_id: Optional[uuid.UUID],
) -> None:
    """
    Перевести документ в FAILED на стадии convert.
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


