"""
Extract Worker — simplified version for vertical slice.

Extracts text from PDF using pdfplumber with word-grouping into lines.
Produces textlayoutraw JSON artifact in MinIO.

NOTE: element.clause_uid is null here — set by Structure Builder.
Full production version with OCR, Tesseract, strategy detection in Stage 4.
"""

import io
import uuid

from src.core.constants import DocumentStatus
from src.core.exceptions import PermanentError, QuarantineError
from src.core.logging import get_logger
from src.db.session import get_session
from src.queue.base_task import MASBaseTask
from src.queue.celery_app import celery_app
from src.storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)

try:
    import pdfplumber

    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.extract_document",
    track_job=False,
    queue="default",
)
async def extract_document(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str = None,
) -> dict:
    return await _extract_document_async(
        document_version_id=document_version_id,
        document_id=document_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
    )


async def _extract_document_async(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
) -> dict:
    """Extract text from PDF and produce textlayoutraw artifact."""
    logger.info("Starting extraction", document_id=document_id)

    if not HAS_PDFPLUMBER:
        raise PermanentError("pdfplumber not installed")

    store = ArtifactStore()

    original_ref = await get_original_ref(document_version_id)
    if not original_ref:
        raise PermanentError(f"No originalref for version {document_version_id}")

    s3_path = original_ref.replace(f"s3://{store.bucket}/", "")
    pdf_bytes = store.get_file(s3_path)

    elements: list[dict] = []
    total_pages = 0
    element_index = 0

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        total_pages = len(pdf.pages)
        for page_num, page in enumerate(pdf.pages, start=1):
            words = (
                page.extract_words(
                    keep_blank_chars=False,
                    extra_attrs=["fontname", "size"],
                )
                or []
            )
            lines = _group_words_into_lines(words)
            for line_text, line_bbox in lines:
                stripped = line_text.strip()
                if not stripped:
                    continue
                elements.append(
                    {
                        "element_id": f"e{element_index:05d}",
                        "type": "text",
                        "text": stripped,
                        "page": page_num,
                        "bbox": line_bbox,
                        "confidence": 1.0,
                        "clause_uid": None,  # set by Structure Builder
                    }
                )
                element_index += 1

    if not elements:
        raise QuarantineError(
            "No text extracted from PDF",
            document_id=document_id,
            reason="no_text_extracted",
        )

    text_layout_raw = {
        "document_version_id": document_version_id,
        "document_id": document_id,
        "elements": elements,
        "tables": [],
        "metadata": {
            "pages": total_pages,
            "strategy": "pdfplumber",
            "element_count": len(elements),
        },
    }

    raw_path = ArtifactPath.layout_raw(tenant_id, deal_id, document_id)
    raw_ref = store.put_json(raw_path, text_layout_raw)

    await update_extraction_result(
        document_version_id=document_version_id,
        document_id=document_id,
        raw_ref=raw_ref,
        page_count=total_pages,
    )

    logger.info(
        "Extraction complete",
        document_id=document_id,
        elements=len(elements),
        pages=total_pages,
    )

    from src.workers.pii_sanitizer import sanitize_document

    sanitize_document.delay(
        document_version_id=document_version_id,
        document_id=document_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    return {"document_id": document_id, "elements": len(elements), "pages": total_pages}


def _group_words_into_lines(words: list) -> list:
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
    lines = []
    current = [sorted_words[0]]
    current_top = round(sorted_words[0]["top"], 1)
    for word in sorted_words[1:]:
        wt = round(word["top"], 1)
        if abs(wt - current_top) <= 3:
            current.append(word)
        else:
            lines.append(_build_line(current))
            current = [word]
            current_top = wt
    if current:
        lines.append(_build_line(current))
    return lines


def _build_line(words: list) -> tuple:
    ws = sorted(words, key=lambda w: w["x0"])
    text = " ".join(w["text"] for w in ws)
    bbox = [
        min(w["x0"] for w in ws),
        min(w["top"] for w in ws),
        max(w["x1"] for w in ws),
        max(w["bottom"] for w in ws),
    ]
    return text, [round(v, 2) for v in bbox]


async def get_original_ref(document_version_id: str) -> str | None:
    from src.db.repositories import DocumentVersionRepository

    async with get_session() as session:
        repo = DocumentVersionRepository(session)
        version = await repo.get_by_id(uuid.UUID(document_version_id))
        return version.original_ref if version else None


async def update_extraction_result(
    document_version_id: str, document_id: str, raw_ref: str, page_count: int
) -> None:
    from src.db.repositories import DocumentRepository, DocumentVersionRepository

    async with get_session() as session:
        ver_repo = DocumentVersionRepository(session)
        doc_repo = DocumentRepository(session)
        await ver_repo.update_refs(
            uuid.UUID(document_version_id),
            raw_ref=raw_ref,
            extraction_strategy="pdfplumber",
        )
        await doc_repo.update_status(
            uuid.UUID(document_id),
            DocumentStatus.EXTRACTED.value,
            page_count=page_count,
        )
