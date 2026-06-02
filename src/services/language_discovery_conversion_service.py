# src/services/language_discovery_conversion_service.py

"""
Language discovery conversion service.

Назначение:
- Предоставить conversion core исключительно для pre-run language discovery workflow;
- Конвертировать office-форматы (DOCX, XLSX, PPTX и т.д.) в PDF через external converter service;
- Сохранять результат в DocumentVersion.converted_pdf_ref;
- Не зависеть от основного analysis pipeline и workers.convert_worker;
- Обеспечить идемпотентность и корректную обработку transient/permanent errors.

Контракт:
- Принимает документы с origin_filetype из OFFICE_FILETYPES;
- Читает исходный файл из original_ref;
- Отправляет в converter endpoint (настройка DOCX_CONVERTER_URL);
- Получает PDF response и валидирует content-type;
- Сохраняет PDF в ArtifactStore через ArtifactPath.converted_pdf;
- Обновляет DocumentVersion.converted_pdf_ref через DocumentVersionRepository.update_refs;
- После flush проверяет, что converted_pdf_ref действительно записан;
- Возвращает LanguageDiscoveryConversionResult с pdf_ref и committed=True.

Ошибки:
- PermanentError: отсутствие original_ref, пустой source file, неподдерживаемый filetype,
  converter HTTP error, неожиданный content-type, пустой PDF response,
  failure при update_refs;
- TransientError: converter timeout, connection error, version disappeared после flush,
  converted_pdf_ref не видно после flush, ref mismatch после flush.

Использование:
- Вызывается из workers.convert_document_for_language_discovery;
- НЕ вызывается из основного workers.convert_worker или других run-stage workers;
- Переиспользуемый core для всех pre-run conversion потребностей.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from services._tenant_resolver import resolve_artifact_tenant_id
from core.config import settings
from core.exceptions import PermanentError, TransientError
from db.repositories.document_version_repo import DocumentVersionRepository
from storage.artifact_store import ArtifactPath, ArtifactStore

OFFICE_FILETYPES = {
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "odt",
    "ods",
    "odp",
    "rtf",
    "csv",
    "html",
    "htm",
}


@dataclass(slots=True)
class LanguageDiscoveryConversionResult:
    """
    Result of pre-run language discovery conversion.

    Attributes:
        document_id: UUID документа.
        document_version_id: UUID версии документа.
        deal_id: UUID сделки.
        tenant_id: UUID тенанта.
        pdf_ref: S3 reference на готовый PDF.
        origin_filetype: Исходный формат файла.
        committed: True если converted_pdf_ref записан и flush успешен.
    """

    document_id: str
    document_version_id: str
    deal_id: str
    tenant_id: str
    pdf_ref: str
    origin_filetype: str | None
    committed: bool


def _normalize_filetype(value: str | None) -> str | None:
    """
    Normalize filetype to lowercase stripped string.

    :param value: Raw filetype value.
    :return: Normalized filetype or None.
    """
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _s3_ref_to_store_path(ref: str, bucket: str) -> str:
    """
    Convert S3 ref to ArtifactStore path.

    :param ref: S3 reference string (e.g., s3://bucket/path/to/file).
    :param bucket: Expected bucket name.
    :return: Path относительно bucket root.
    :raises PermanentError: Если ref не начинается с ожидаемого s3:// prefix.
    """
    prefix = f"s3://{bucket}/"
    if not ref or not ref.startswith(prefix):
        raise PermanentError(f"Invalid S3 ref for bucket '{bucket}': {ref}")
    return ref[len(prefix) :]


def _build_converter_filename(version) -> str:
    """
    Build converter-compatible filename from DocumentVersion attributes.

    :param version: DocumentVersion entity.
    :return: Filename с расширением для отправки в converter endpoint.
    """
    origin_filetype = _normalize_filetype(getattr(version, "origin_filetype", None))
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
    Convert office document bytes to PDF via external converter service.

    :param src_bytes: Исходные байты office-документа.
    :param filename: Имя файла с расширением для multipart upload.
    :return: PDF bytes.
    :raises PermanentError: Converter not configured, HTTP error, unexpected content-type, empty PDF.
    :raises TransientError: Timeout, connection error, request error.
    """
    converter_url = getattr(settings, "DOCX_CONVERTER_URL", None)
    timeout_seconds = getattr(settings, "DOCX_CONVERTER_TIMEOUT_SECONDS", 60)

    if not converter_url:
        raise PermanentError(
            "Language discovery conversion service is not configured. "
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
        raise PermanentError(f"Conversion service error: {resp.status_code} {body_preview}")

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


async def convert_document_for_language_discovery(
    *,
    db: AsyncSession,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
) -> LanguageDiscoveryConversionResult:
    """
    Convert office document to PDF for pre-run language discovery workflow.

    Контракт:
    - Если origin_filetype не в OFFICE_FILETYPES → PermanentError;
    - Если converted_pdf_ref уже существует → немедленный возврат с committed=True;
    - Если original_ref отсутствует → PermanentError;
    - Читает исходный файл из storage;
    - Конвертирует через external converter service;
    - Сохраняет PDF в storage;
    - Обновляет DocumentVersion.converted_pdf_ref;
    - После flush проверяет, что converted_pdf_ref действительно записан;
    - Возвращает LanguageDiscoveryConversionResult.

    :param db: AsyncSession для database операций.
    :param document_id: UUID документа.
    :param document_version_id: UUID версии документа.
    :param deal_id: UUID сделки.
    :param tenant_id: UUID тенанта.
    :return: LanguageDiscoveryConversionResult с pdf_ref и committed=True.
    :raises PermanentError: Version not found, unsupported filetype, missing original_ref,
                            storage read error, conversion error, update_refs failure.
    :raises TransientError: Converter timeout/connection error, version disappeared after flush,
                            converted_pdf_ref не видно после flush, ref mismatch after flush.
    """
    ver_repo = DocumentVersionRepository(db)
    store = ArtifactStore(settings)

    ver_uuid = uuid.UUID(document_version_id)
    version = await ver_repo.get_by_id(ver_uuid)
    if not version:
        raise PermanentError(
            "language_discovery_conversion: document version not found "
            f"(document_version_id={document_version_id})"
        )

    origin_filetype = _normalize_filetype(getattr(version, "origin_filetype", None))
    original_ref = getattr(version, "original_ref", None)
    converted_pdf_ref = getattr(version, "converted_pdf_ref", None)

    resolved_tenant_id = await resolve_artifact_tenant_id(
        session=db,
        deal_id=deal_id,
        document_id=document_id,
        payload_tenant_id=tenant_id,
    )

    if origin_filetype not in OFFICE_FILETYPES:
        raise PermanentError(
            "language_discovery_conversion: unsupported origin_filetype for pre-run conversion "
            f"(document_version_id={document_version_id}, origin_filetype={origin_filetype})"
        )

    if converted_pdf_ref:
        return LanguageDiscoveryConversionResult(
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=resolved_tenant_id,
            pdf_ref=converted_pdf_ref,
            origin_filetype=origin_filetype,
            committed=True,
        )

    if not original_ref:
        raise PermanentError(
            "language_discovery_conversion: missing original_ref "
            f"(document_version_id={document_version_id})"
        )

    try:
        src_s3_path = _s3_ref_to_store_path(original_ref, store.bucket)
        src_bytes = store.get_file(src_s3_path)
    except TransientError:
        raise
    except Exception as e:
        raise PermanentError(
            f"language_discovery_conversion: failed to read original source file: {e}"
        ) from e

    if not src_bytes:
        raise PermanentError(
            "language_discovery_conversion: original source file is empty "
            f"(document_version_id={document_version_id})"
        )

    filename = _build_converter_filename(version)
    pdf_bytes = await _convert_office_bytes_to_pdf_bytes(
        src_bytes=src_bytes,
        filename=filename,
    )

    pdf_path = ArtifactPath.converted_pdf(resolved_tenant_id, deal_id, document_id)
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
            "language_discovery_conversion: failed to update converted_pdf_ref "
            f"(document_version_id={document_version_id})"
        )

    await db.flush()

    refreshed_version = await ver_repo.get_by_id(ver_uuid)
    refreshed_converted_ref = (
        getattr(refreshed_version, "converted_pdf_ref", None) if refreshed_version else None
    )

    if not refreshed_version:
        raise TransientError(
            "language_discovery_conversion: version disappeared after flush "
            f"(document_version_id={document_version_id})"
        )

    if not refreshed_converted_ref:
        raise TransientError(
            "language_discovery_conversion: converted_pdf_ref not visible after flush "
            f"(document_version_id={document_version_id})"
        )

    if refreshed_converted_ref != pdf_ref:
        raise TransientError(
            "language_discovery_conversion: converted_pdf_ref mismatch after flush "
            f"(document_version_id={document_version_id}, expected={pdf_ref}, actual={refreshed_converted_ref})"
        )

    return LanguageDiscoveryConversionResult(
        document_id=document_id,
        document_version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=resolved_tenant_id,
        pdf_ref=pdf_ref,
        origin_filetype=origin_filetype,
        committed=True,
    )

    
