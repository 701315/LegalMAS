"""
PII Sanitizer — simplified version for vertical slice.

Tokenizes personal data (names, phones, emails).
Preserves legal identifiers: INN, OGRN, amounts, dates.
No KMS encryption — added in Stage 5.
"""

import re
import uuid

from src.core.constants import DocumentStatus
from src.core.logging import get_logger
from src.db.session import get_session
from src.queue.async_helpers import run_async
from src.queue.base_task import MASBaseTask
from src.queue.celery_app import celery_app
from src.storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)

PERSON_FULL = re.compile(r"[А-ЯЁ][а-яё]{1,20}\s[А-ЯЁ][а-яё]{1,20}\s[А-ЯЁ][а-яё]{1,20}")
PERSON_SHORT = re.compile(r"[А-ЯЁ][а-яё]{1,20}\s[А-ЯЁ]\.[А-ЯЁ]\.")
PHONE = re.compile(r"\+?7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")
EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}")


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.sanitize_document",
    track_job=False,
    queue="default",
)
def sanitize_document(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str = None,
) -> dict:
    logger.info("Starting PII sanitization", document_id=document_id)
    store = ArtifactStore()
    raw_path = ArtifactPath.layout_raw(tenant_id, deal_id, document_id)
    text_layout_raw = store.get_json(raw_path)

    pii_mapping = {}
    counters = {"PERSON": 0, "PHONE": 0, "EMAIL": 0}
    sanitized_elements = []

    for element in text_layout_raw["elements"]:
        sanitized_text = element["text"]

        for match in PERSON_FULL.finditer(sanitized_text):
            counters["PERSON"] += 1
            token = f"[PERSON{counters['PERSON']}]"
            pii_mapping[token] = match.group()
            sanitized_text = sanitized_text.replace(match.group(), token, 1)

        for match in PERSON_SHORT.finditer(sanitized_text):
            if "PERSON" in sanitized_text[max(0, match.start() - 15) : match.start()]:
                continue
            counters["PERSON"] += 1
            token = f"[PERSON{counters['PERSON']}]"
            pii_mapping[token] = match.group()
            sanitized_text = sanitized_text.replace(match.group(), token, 1)

        for match in PHONE.finditer(sanitized_text):
            counters["PHONE"] += 1
            token = f"[PHONE{counters['PHONE']}]"
            pii_mapping[token] = match.group()
            sanitized_text = sanitized_text.replace(match.group(), token, 1)

        for match in EMAIL.finditer(sanitized_text):
            counters["EMAIL"] += 1
            token = f"[EMAIL{counters['EMAIL']}]"
            pii_mapping[token] = match.group()
            sanitized_text = sanitized_text.replace(match.group(), token, 1)

        sanitized_elements.append({**element, "text": sanitized_text})

    text_layout_sanitized = {
        **text_layout_raw,
        "elements": sanitized_elements,
        "pii_stats": {
            "entities_detected": sum(counters.values()),
            "persons": counters["PERSON"],
            "phones": counters["PHONE"],
            "emails": counters["EMAIL"],
        },
    }

    sanitized_path = ArtifactPath.layout_sanitized(tenant_id, deal_id, document_id)
    sanitized_ref = store.put_json(sanitized_path, text_layout_sanitized)

    mapping_path = ArtifactPath.pii_mapping(tenant_id, deal_id, document_id)
    store.put_json(mapping_path, pii_mapping)

    run_async(_update_sanitization_result(document_version_id, document_id, sanitized_ref))

    logger.info(
        "PII sanitization complete",
        document_id=document_id,
        entities_found=sum(counters.values()),
    )

    from src.workers.structure_builder import build_structure

    build_structure.delay(
        document_version_id=document_version_id,
        document_id=document_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    return {"document_id": document_id, "pii_entities": sum(counters.values())}


async def _update_sanitization_result(
    document_version_id: str, document_id: str, sanitized_ref: str
) -> None:
    from src.db.repositories import DocumentRepository, DocumentVersionRepository

    async with get_session() as session:
        ver_repo = DocumentVersionRepository(session)
        doc_repo = DocumentRepository(session)
        await ver_repo.update_refs(uuid.UUID(document_version_id), sanitized_ref=sanitized_ref)
        await doc_repo.update_status(uuid.UUID(document_id), DocumentStatus.SANITIZED.value)
