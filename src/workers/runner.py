"""
Runner — simplified version for vertical slice.

Executes one hardcoded DD check: Change of Control (coc001).
Rules-only detection via keyword search.
Writes check result with new fields:
  - structured_data          = None  (populated in Stage 8)
  - conditional_check_triggered = False (populated in Stage 8)
  - trigger_name             = None  (populated in Stage 8)

applicable_triggers routing:
  In this stage: Runner checks all documents regardless of applicable_triggers.
  In Stage 8: Runner reads Document.applicable_triggers and routes to
  applicable checks from check_catalogue.yaml.
  The structured_data=None / conditional_check_triggered=False values
  validate the contract with the production Runner (Stage 8).

Full Runner with check_catalogue.yaml routing in Stage 8.

В продакшене Runner не ограничивается одним CoC‑чеком.
Для каждого юридического кейса (смена контроля, золотой парашют, штрафы за неподачу отчётности и т.п.)
будет отдельный YAML‑файл/блок с описанием:
check_id, check_name, severity;
целевых типов документов (doc_types);
триггеров запуска (профиль DD, юрисдикция, роль контрагента);
набора ключевых слов / паттернов / LLM‑промптов (аналог COC_KEYWORDS).

UI конструктора плейбука показывает эти кейсы как чек‑боксы/список сценариев анализа.
Пользователь при формировании плейбука выбирает нужные кейсы, а Runner по выбранному
набору YAML‑описаний формирует набор проверок, который будет запускаться для документов.

"""

import json
import uuid

from src.core.constants import CheckResultStatus, DocumentStatus, Severity
from src.core.logging import get_logger
from src.queue.async_helpers import get_worker_session, run_async
from src.queue.base_task import MASBaseTask
from src.queue.celery_app import celery_app
from src.storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)

COC_KEYWORDS = [
    "смена контроля",
    "смены контроля",
    "смене контроля",
    "change of control",
    "change-of-control",
    "переход контроля",
    "переход права контроля",
    "смена собственника",
    "контрольный пакет",
]


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.run_checks",
    track_job=False,
    queue="default",
)
def run_checks(
    self,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str = None,
    doctype: str = "Other",
) -> dict:
    """
    Run DD checks on a document.

    Stage 2.5: one hardcoded check (coc001 — Change of Control).
    Stage 8:   full routing via check_catalogue.yaml + applicable_triggers.

    structured_data=None and conditional_check_triggered=False are
    intentional — they validate the DB field contract with Stage 8.
    """
    logger.info("Starting checks", document_id=document_id, doctype=doctype)
    store = ArtifactStore()

    raw_path = ArtifactPath.layout_raw(tenant_id, deal_id, document_id)
    text_layout_raw = store.get_json(raw_path)
    elements = text_layout_raw["elements"]

    tree_path = ArtifactPath.clause_tree(tenant_id, deal_id, document_id)
    clause_tree = store.get_json(tree_path)

    check_results = []
    evidence_records = []

    coc_result = _check_change_of_control(elements, clause_tree, document_id)
    check_results.append(coc_result["check_result"])
    if coc_result.get("evidence"):
        evidence_records.append(coc_result["evidence"])

    run_async(
        _finalize(
            run_id=run_id,
            document_id=document_id,
            check_results=check_results,
        )
    )

    if run_id:
        results_path = ArtifactPath.check_results(tenant_id, deal_id, run_id)
        results_ndjson = "\n".join(json.dumps(r, ensure_ascii=False) for r in check_results)
        store.put_file(
            results_path,
            results_ndjson.encode("utf-8"),
            content_type="application/x-ndjson",
        )

        if evidence_records:
            evidence_path = ArtifactPath.evidence(tenant_id, deal_id, run_id)
            evidence_ndjson = "\n".join(json.dumps(e, ensure_ascii=False) for e in evidence_records)
            store.put_file(
                evidence_path,
                evidence_ndjson.encode("utf-8"),
                content_type="application/x-ndjson",
            )

    logger.info(
        "Checks complete",
        document_id=document_id,
        results=len(check_results),
        evidence=len(evidence_records),
    )

    from src.workers.exporter import export_results

    if run_id:
        export_results.delay(run_id=run_id, deal_id=deal_id, tenant_id=tenant_id)

    return {
        "document_id": document_id,
        "checks_run": len(check_results),
        "findings": sum(1 for r in check_results if r["result"] == "fail"),
    }


def _check_change_of_control(elements, clause_tree, document_id) -> dict:
    """
    Check for Change of Control clause.

    Returns dict with check_result and optional evidence.
    structured_data=None, conditional_check_triggered=False are intentional
    stubs — they validate the contract with production Runner (Stage 8).
    """
    for element in elements:
        text_lower = element.get("text", "").lower()
        for keyword in COC_KEYWORDS:
            if keyword in text_lower:
                clause_uid = _find_clause_for_element(clause_tree, element.get("element_id"))
                evidence = {
                    "check_id": "coc001",
                    "element_id": element.get("element_id"),
                    "snippet": element.get("text", "")[:500],
                    "page": element.get("page"),
                    "clause_uid": clause_uid,
                    "bbox": element.get("bbox"),
                    "keyword_matched": keyword,
                }
                return {
                    "check_result": {
                        "check_id": "coc001",
                        "check_name": "Change of Control Clause",
                        "result": CheckResultStatus.FAIL.value,
                        "severity": Severity.CRITICAL.value,
                        "value_text": f"Change of control clause found: '{keyword}'",
                        "evidence_snippet": element.get("text", "")[:300],
                        "evidence_page": element.get("page"),
                        "confidence": 0.85,
                        "detector_used": "rules",
                        "quality_flags": [],
                        # Contract fields for Stage 8 validation
                        "structured_data": None,
                        "conditional_check_triggered": False,
                        "trigger_name": None,
                    },
                    "evidence": evidence,
                }

    return {
        "check_result": {
            "check_id": "coc001",
            "check_name": "Change of Control Clause",
            "result": CheckResultStatus.PASS.value,
            "severity": Severity.PASS.value,
            "value_text": "No change of control clause detected",
            "confidence": 0.8,
            "detector_used": "rules",
            "quality_flags": [],
            "structured_data": None,
            "conditional_check_triggered": False,
            "trigger_name": None,
        },
    }


def _find_clause_for_element(clause_tree, element_id) -> str | None:
    def search(nodes):
        for node in nodes:
            if element_id in node.get("element_ids", []):
                return node["clause_uid"]
            found = search(node.get("children", []))
            if found:
                return found
        return None

    root_children = clause_tree.get("root", {}).get("children", [])
    return search(root_children)


async def _save_results(run_id, document_id, check_results) -> None:
    """Save check results to DB including new fields."""
    if not run_id:
        return
    from src.db.repositories import ResultRepository

    async with get_worker_session() as session:
        repo = ResultRepository(session)
        for cr in check_results:
            await repo.create(
                run_id=uuid.UUID(run_id),
                document_id=uuid.UUID(document_id),
                check_id=cr["check_id"],
                check_name=cr["check_name"],
                result=cr["result"],
                severity=cr["severity"],
                value_text=cr.get("value_text"),
                confidence=cr.get("confidence"),
                detector_used=cr.get("detector_used"),
                quality_flags=cr.get("quality_flags"),
                # New fields — contract with Stage 8
                structured_data=cr.get("structured_data"),
                conditional_check_triggered=cr.get("conditional_check_triggered", False),
                trigger_name=cr.get("trigger_name"),
            )


async def _finalize(run_id, document_id, check_results) -> None:
    # TODO Stage 8: рефакторинг — весь run_checks в единый run_async(_run_checks_async())
    # Текущий _finalize — временный фикс проблемы event loop при двух run_async() подряд.
    await _save_results(run_id, document_id, check_results)
    await _update_document_status(document_id)


async def _update_document_status(document_id: str) -> None:
    from src.db.repositories import DocumentRepository

    async with get_worker_session() as session:
        repo = DocumentRepository(session)
        await repo.update_status(uuid.UUID(document_id), DocumentStatus.COMPLETED.value)
