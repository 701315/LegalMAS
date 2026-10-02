# src/services/export/fact_bundle.py

"""
fact_bundle.py — сборка структурированного fact_bundle для LLM и report_builder.

Назначение:
- собрать факты из check_results, documents, checks_by_id в один dataclass;
- разделить global checks и doc-type checks (по cr["origin"]);
- агрегировать по check_id и document_id;
- предоставить payload для LLM-нарративов и для report_builder.

ВАЖНО (проверено по коду):
- вход check_results — это 39 полей из runner_repo.load_check_results_for_run
  + overlay через apply_presentations_for_read (см. core.py:185–195);
- в check_results есть поле "origin" = "GLOBAL_PLAYBOOK" | "DOCUMENT_TYPE";
- в check_results НЕТ поля "doc_type" — берётся из documents[doc_id]["doc_type"];
- в check_results НЕТ поля "evidence_ref" — используется display_text / review_message;
- в documents — 8 полей (см. core.py:56–74): name, folder_path, doc_type, status,
  classification_level, classification_confidence, applicable_triggers,
  classification_requires_review.

ДОПУЩЕНИЕ (единственное):
- overlay apply_presentations_for_read не перезаписывает check_id, document_id, origin.
  Это стандартная безопасность overlay: он добавляет/заменяет презентационные поля
  (display_text, review_message), не идентификаторы.

Переиспользует:
- services.export.report_builder._build_dd_requests_for_report
- classifiers.yaml_registry.YAMLRegistry.get_config — для doc_type label
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hardcoded defaults для профиля M&A Russia DD
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDED_AREAS: dict[str, list[str]] = {
    "M&A Russia DD": [
        "Tax",
        "Environmental",
        "Insurance",
        "Anti-bribery and anti-corruption (beyond written policies)",
    ],
}

DEFAULT_LIMITATIONS: list[str] = [
    "We express no opinion as to matters of fact.",
    "We have relied on the accuracy and completeness of the documents provided.",
    "Findings based on low-confidence extraction should be manually verified.",
]

DEFAULT_ASSUMPTIONS: list[str] = [
    "All documents provided are true, complete, and up-to-date copies of the originals.",
    "All agreements reviewed were duly authorised and validly executed.",
    "No material facts have been withheld from us.",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FactBundleMeta:
    """Метаданные run'а."""
    deal_name: str
    run_id: str
    playbook_version: str
    playbook_profile: str
    checks_mode: str
    pipeline_strategy: str
    environment_hash: str
    locale: str
    generated_at: str = ""

    # Опциональные — заполняются из payload, если доступны
    buyer_name: str = ""
    target_name: str = ""
    seller_name: str = ""

    # Источники для Terms of Reference
    excluded_areas: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


@dataclass
class CheckSummaryRow:
    """Агрегат по одному check_id."""
    check_id: str
    check_name: str
    origin: str
    documents_checked: int = 0
    issues: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    pass_count: int = 0
    unclear: int = 0
    not_applicable: int = 0
    affected_documents: list[str] = field(default_factory=list)
    top_display_text: str = ""
    top_review_message: str = ""


@dataclass
class DocumentSummaryRow:
    """Агрегат по одному document_id."""
    document_id: str
    document_name: str
    doc_type: str
    folder_path: str = ""
    checks: int = 0
    issues: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    pass_count: int = 0
    unclear: int = 0


@dataclass
class GlobalChecksFacts:
    """Global checks: матрица check × document."""
    by_check: dict[str, CheckSummaryRow] = field(default_factory=dict)
    by_document: dict[str, DocumentSummaryRow] = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)
    top_issues: list[dict] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=dict)


@dataclass
class DocTypeGroup:
    """Одна группа doc-type checks (например, все credit_agreement)."""
    doc_type: str
    label: str
    documents: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    by_check: dict[str, CheckSummaryRow] = field(default_factory=dict)
    top_issues: list[dict] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=dict)
    summary: dict = field(default_factory=dict)


@dataclass
class DocTypeChecksFacts:
    """Doc-type checks: сгруппированы по doc_type."""
    by_doc_type: dict[str, DocTypeGroup] = field(default_factory=dict)
    summaries: list[dict] = field(default_factory=list)


@dataclass
class FactBundle:
    """Полный bundle фактов для отчёта."""
    meta: FactBundleMeta
    totals: dict[str, int] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    conditional: dict[str, Any] = field(default_factory=dict)

    global_checks: GlobalChecksFacts = field(default_factory=GlobalChecksFacts)
    doc_type_checks: DocTypeChecksFacts = field(default_factory=DocTypeChecksFacts)

    extracted_values: list[dict] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)
    documents_reviewed: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Сериализация в dict для LLM payload."""
        return _to_serializable(asdict(self))



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _is_issue(result_val: str) -> bool:
    """
    True, если результат — issue (не pass, не unclear, не not_applicable).

    check_results может содержать result-значения:
    - "pass" — проверка пройдена
    - "fail" — проверка не пройдена (issue)
    - "unclear" — не удалось определить
    - "not_applicable" — не применимо
    - "missing_required_cla" — отсутствует обязательная клауза (issue)
    - "clause_missing" — отсутствует пункт (issue)
    - "clause_partially_defined" — частично определён (issue)
    - "clause_defined" — определён (НЕ issue)
    - "no_issue_detected" — проблем не обнаружено (НЕ issue)
    """
    rv = (result_val or "").lower().strip()
    if not rv:
        return False
    if rv in ("pass", "unclear", "not_applicable",
              "clause_defined", "no_issue_detected",
              "present", "defined", "no"):
        return False
    return True


def build_fact_bundle(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    checks_by_id: dict[str, Any],
    *,
    deal_name: str,
    run_id: str,
    playbook_version: str = "1.0.0",
    playbook_profile: str = "M&A Russia DD",
    checks_mode: str = "",
    pipeline_strategy: str = "",
    environment_hash: str = "",
    locale: str = "en",
    generated_at: str = "",
    buyer_name: str = "",
    target_name: str = "",
    seller_name: str = "",
) -> FactBundle:
    """
    Собрать FactBundle из результатов run'а.

    Args:
        check_results: overlay'd результаты (39 полей из runner_repo).
        documents: dict[document_id, doc_info] — 8 полей из core.py.
        checks_by_id: dict[check_id, CheckDefinition] — global + doc-type.
        deal_name, run_id, ...: метаданные.

    Returns:
        FactBundle — dataclass с полной структурой.
    """
    meta = FactBundleMeta(
        deal_name=deal_name,
        run_id=run_id,
        playbook_version=playbook_version,
        playbook_profile=playbook_profile,
        checks_mode=checks_mode,
        pipeline_strategy=pipeline_strategy,
        environment_hash=environment_hash,
        locale=locale,
        generated_at=generated_at,
        buyer_name=buyer_name,
        target_name=target_name,
        seller_name=seller_name,
        excluded_areas=DEFAULT_EXCLUDED_AREAS.get(playbook_profile, []),
        limitations=list(DEFAULT_LIMITATIONS),
        assumptions=list(DEFAULT_ASSUMPTIONS),
    )

    totals = _compute_totals(check_results, documents)
    quality = _compute_quality(check_results, documents)
    conditional = _compute_conditional(check_results, documents)

    global_rows, doc_type_rows_by_type = _split_by_scope(check_results, documents)

    global_checks = _build_global_facts(global_rows, documents)
    doc_type_checks = _build_doc_type_facts(doc_type_rows_by_type, documents)

    extracted_values = _compute_extracted_values(check_results, documents, checks_by_id)
    requests = _compute_requests(check_results, documents, checks_by_id, locale)
    documents_reviewed = _build_documents_reviewed(documents)

    return FactBundle(
        meta=meta,
        totals=totals,
        quality=quality,
        conditional=conditional,
        global_checks=global_checks,
        doc_type_checks=doc_type_checks,
        extracted_values=extracted_values,
        requests=requests,
        documents_reviewed=documents_reviewed,
    )


# ---------------------------------------------------------------------------
# Внутренние функции
# ---------------------------------------------------------------------------


def _compute_totals(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Totals для Overall Summary."""
    counts = {
        "documents": len(documents),
        "checks_planned": 0,
        "checks_completed": 0,
        "checks_not_applicable": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "pass": 0,
        "unclear": 0,
    }

    for cr in check_results:
        counts["checks_planned"] += 1
        result = cr.get("result", "unclear")
        severity = cr.get("severity", "medium")
        execution_status = (cr.get("execution_status") or "").upper()

        if execution_status == "SUCCESS":
            counts["checks_completed"] += 1

        if result == "not_applicable":
            counts["checks_not_applicable"] += 1
            continue

        if _is_issue(result):
            sev = severity if severity in ("critical", "high", "medium") else "medium"
            counts[sev] += 1
        elif result == "pass":
            counts["pass"] += 1
        elif result == "not_applicable":
            counts["checks_not_applicable"] += 1
        else:
            counts["unclear"] += 1

    return counts


def _compute_quality(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Quality metrics для Overall Summary и Methodology."""
    quarantined = sum(
        1 for doc in documents.values()
        if (doc.get("status") or "").lower() == "quarantine"
    )

    degraded_docs: set[str] = set()
    fail_high_crit: list[dict] = []

    for cr in check_results:
        quality_flags = cr.get("quality_flags") or {}
        if isinstance(quality_flags, dict) and quality_flags.get("structure_degraded"):
            degraded_docs.add(cr.get("document_id", ""))

        if _is_issue(cr.get("result")) and cr.get("severity") in ("critical", "high"):
            fail_high_crit.append(cr)

    # Evidence — используем display_text / review_message / value_text
    evidence_valid = sum(
        1 for cr in fail_high_crit
        if (
            (cr.get("display_text") or "").strip()
            or (cr.get("review_message") or "").strip()
            or (cr.get("value_text") or "").strip()
        )
    )

    evidence_validity_rate = (
        evidence_valid / len(fail_high_crit) if fail_high_crit else 1.0
    )

    confidences = [
        cr.get("confidence") for cr in check_results
        if isinstance(cr.get("confidence"), (int, float))
    ]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    low_confidence_count = sum(1 for c in confidences if c < 0.6)

    # Detector coverage
    detector_counts: dict[str, int] = {"rules": 0, "hybrid": 0, "llm": 0, "unknown": 0}
    for cr in check_results:
        detector = (cr.get("detector_used") or "").lower()
        if detector in detector_counts:
            detector_counts[detector] += 1
        else:
            detector_counts["unknown"] += 1

    # Classification confidence
    classification_confidences = [
        doc.get("classification_confidence")
        for doc in documents.values()
        if isinstance(doc.get("classification_confidence"), (int, float))
    ]
    avg_class_conf = (
        sum(classification_confidences) / len(classification_confidences)
        if classification_confidences else 0.0
    )

    needs_manual_review_count = sum(
        1 for cr in check_results if cr.get("needs_manual_review")
    )

    return {
        "quarantine_count": quarantined,
        "degraded_count": len(degraded_docs),
        "evidence_validity_rate": evidence_validity_rate,
        "avg_confidence": avg_confidence,
        "low_confidence_count": low_confidence_count,
        "avg_classification_confidence": avg_class_conf,
        "needs_manual_review_count": needs_manual_review_count,
        "detector_coverage": detector_counts,
    }


def _compute_conditional(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Conditional checks facts."""
    total_triggered = sum(
        1 for cr in check_results if cr.get("conditional_check_triggered")
    )
    total_failed = sum(
        1 for cr in check_results
        if cr.get("conditional_check_triggered") and cr.get("result") == "fail"
    )

    rows: list[dict] = []
    for cr in check_results:
        if not cr.get("conditional_check_triggered"):
            continue
        doc_id = cr.get("document_id", "")
        doc_info = documents.get(doc_id, {})
        rows.append({
            "check_id": cr.get("check_id", ""),
            "check_name": cr.get("check_name", ""),
            "document_id": doc_id,
            "document_name": doc_info.get("name", ""),
            "doc_type": doc_info.get("doc_type", ""),
            "trigger_name": cr.get("trigger_name", ""),
            "result": cr.get("result", "unclear"),
            "severity": cr.get("severity", "medium"),
            "clause_uid": cr.get("clause_uid", ""),
            "display_text": (cr.get("display_text") or "")[:300],
            "review_message": (cr.get("review_message") or "")[:300],
        })

    return {
        "total_triggered": total_triggered,
        "total_failed": total_failed,
        "rows": rows,
    }


def _split_by_scope(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
) -> tuple[list[dict], dict[str, list[dict]]]:
    """
    Разделяет check_results на global и doc-type.

    Логика — 1:1 с dd_grid_v1_builder._is_global_check:
    - origin == "GLOBAL_PLAYBOOK" → global
    - origin пустой → global (fallback)
    - origin == "DOCUMENT_TYPE" → doc-type

    Дополнительно обогащает каждую строку _doc_type и _document_name
    (из documents[document_id]).
    """
    global_rows: list[dict] = []
    doc_type_rows: dict[str, list[dict]] = {}

    for cr in check_results:
        doc_id = cr.get("document_id", "")
        doc_info = documents.get(doc_id, {})
        doc_type = doc_info.get("doc_type", "Generic")

        # Обогащаем row
        enriched = dict(cr)
        enriched["_doc_type"] = doc_type
        enriched["_document_name"] = doc_info.get("name", "")
        enriched["_document_folder"] = doc_info.get("folder_path", "")

        origin = (cr.get("origin") or "").strip().upper()

        if origin == "DOCUMENT_TYPE":
            doc_type_rows.setdefault(doc_type, []).append(enriched)
        else:
            # "GLOBAL_PLAYBOOK" или пустой → global
            global_rows.append(enriched)

    return global_rows, doc_type_rows


def _build_global_facts(
    rows: list[dict],
    documents: dict[str, dict[str, Any]],
) -> GlobalChecksFacts:
    """Собирает GlobalChecksFacts."""
    by_check = _group_by_check(rows)
    by_document = _group_by_document(rows, documents)
    top_issues = _get_top_risks(rows, limit=20)
    totals = _count_severity_from_rows(rows)

    return GlobalChecksFacts(
        by_check=by_check,
        by_document=by_document,
        rows=rows,
        top_issues=top_issues,
        totals=totals,
    )


def _build_doc_type_facts(
    doc_type_rows: dict[str, list[dict]],
    documents: dict[str, dict[str, Any]],
) -> DocTypeChecksFacts:
    """Собирает DocTypeChecksFacts."""
    by_doc_type: dict[str, DocTypeGroup] = {}
    summaries: list[dict] = []

    for doc_type, rows in doc_type_rows.items():
        label = _get_doc_type_label(doc_type)
        by_check = _group_by_check(rows)
        top_issues = _get_top_risks(rows, limit=10)
        totals = _count_severity_from_rows(rows)

        doc_ids: list[str] = []
        seen: set[str] = set()
        for row in rows:
            doc_id = row.get("document_id", "")
            if doc_id and doc_id not in seen:
                seen.add(doc_id)
                doc_ids.append(doc_id)

        summary = _get_doc_type_summary(doc_type, rows, documents)

        by_doc_type[doc_type] = DocTypeGroup(
            doc_type=doc_type,
            label=label,
            documents=doc_ids,
            rows=rows,
            by_check=by_check,
            top_issues=top_issues,
            totals=totals,
            summary=summary,
        )
        summaries.append(summary)

    summaries.sort(
        key=lambda s: -(s.get("critical", 0) * 10 + s.get("high", 0))
    )

    return DocTypeChecksFacts(by_doc_type=by_doc_type, summaries=summaries)


def _group_by_check(rows: list[dict]) -> dict[str, CheckSummaryRow]:
    """Группирует rows по check_id."""
    result: dict[str, CheckSummaryRow] = {}

    for row in rows:
        check_id = row.get("check_id", "")
        if not check_id:
            continue

        if check_id not in result:
            result[check_id] = CheckSummaryRow(
                check_id=check_id,
                check_name=row.get("check_name") or check_id,
                origin=row.get("origin") or "",
            )

        summary = result[check_id]
        summary.documents_checked += 1

        result_val = row.get("result", "unclear")
        severity = row.get("severity", "medium")

        if _is_issue(result_val):
            summary.issues += 1
            if severity == "critical":
                summary.critical += 1
            elif severity == "high":
                summary.high += 1
            elif severity == "medium":
                summary.medium += 1

            # top_display_text / top_review_message — первое найденное
            if not summary.top_display_text:
                summary.top_display_text = (row.get("display_text") or "")[:300]
            if not summary.top_review_message:
                summary.top_review_message = (row.get("review_message") or "")[:300]

            doc_name = row.get("_document_name", "")
            if doc_name and doc_name not in summary.affected_documents:
                summary.affected_documents.append(doc_name)
        elif result_val == "pass":
            summary.pass_count += 1
        elif result_val == "not_applicable":
            summary.not_applicable += 1
        else:
            summary.unclear += 1

    return result


def _group_by_document(
    rows: list[dict],
    documents: dict[str, dict[str, Any]],
) -> dict[str, DocumentSummaryRow]:
    """Группирует rows по document_id."""
    result: dict[str, DocumentSummaryRow] = {}

    for row in rows:
        doc_id = row.get("document_id", "")
        if not doc_id:
            continue

        if doc_id not in result:
            doc_info = documents.get(doc_id, {})
            result[doc_id] = DocumentSummaryRow(
                document_id=doc_id,
                document_name=doc_info.get("name", ""),
                doc_type=doc_info.get("doc_type", ""),
                folder_path=doc_info.get("folder_path", ""),
            )

        summary = result[doc_id]
        summary.checks += 1

        result_val = row.get("result", "unclear")
        severity = row.get("severity", "medium")

        if _is_issue(result_val):
            summary.issues += 1
            if severity == "critical":
                summary.critical += 1
            elif severity == "high":
                summary.high += 1
            elif severity == "medium":
                summary.medium += 1
        elif result_val == "pass":
            summary.pass_count += 1
        else:
            summary.unclear += 1

    return result


def _count_severity_from_rows(rows: list[dict]) -> dict[str, int]:
    """Подсчёт severity прямо из rows."""
    counts = {
        "critical": 0, "high": 0, "medium": 0,
        "pass": 0, "unclear": 0, "not_applicable": 0,
    }
    for row in rows:
        result_val = row.get("result", "")
        severity = row.get("severity", "medium")
        rv_lower = (result_val or "").lower().strip()

        if rv_lower == "not_applicable":
            counts["not_applicable"] += 1
            continue
        if rv_lower == "unclear":
            counts["unclear"] += 1
            continue
        if rv_lower == "pass":
            counts["pass"] += 1
            continue

        # Все остальные статусы (fail, missing_required_cla, ...) — issue
        sev = severity if severity in ("critical", "high", "medium") else "medium"
        counts[sev] += 1

    return counts


def _get_top_risks(rows: list[dict], limit: int = 15) -> list[dict]:
    """Top risks из rows (fail + critical/high/medium)."""
    severity_order = {"critical": 0, "high": 1, "medium": 2}

    fail_rows = [
        row for row in rows
        if _is_issue(row.get("result", ""))
        and row.get("severity") in ("critical", "high", "medium")
    ]

    fail_rows.sort(key=lambda r: (
        severity_order.get(r.get("severity", "medium"), 9),
        -(r.get("confidence") or 0.0),
    ))

    result: list[dict] = []
    for row in fail_rows[:limit]:
        result.append({
            "check_id": row.get("check_id", ""),
            "check_name": row.get("check_name", ""),
            "severity": row.get("severity", "medium"),
            "document_id": row.get("document_id", ""),
            "document_name": row.get("_document_name", ""),
            "doc_type": row.get("_doc_type", ""),
            "clause_uid": row.get("clause_uid", ""),
            "page": row.get("page"),
            "display_text": (row.get("display_text") or "")[:300],
            "review_message": (row.get("review_message") or "")[:300],
            "review_status": row.get("review_status", ""),
            "conditional_check_triggered": row.get("conditional_check_triggered", False),
            "trigger_name": row.get("trigger_name", ""),
        })

    return result


def _get_doc_type_label(doc_type: str) -> str:
    """
    Возвращает human-readable label для doc_type.

    Пытается загрузить из playbooks/document_types/registry.yaml
    через YAMLRegistry.get_config(doc_type).raw["name"].

    Fallback — генерация из кода ("credit_agreement" → "Credit Agreement").
    """
    if not doc_type:
        return ""

    try:
        from classifiers.yaml_registry import YAMLRegistry
        registry = YAMLRegistry.get_instance(validate=False)
        config = registry.get_config(doc_type)
        if config is not None:
            raw = getattr(config, "raw", None) or {}
            # registry_entry может лежать в raw или в raw["document_type"]
            entry = raw.get("registry_entry") or raw
            name = entry.get("name") if isinstance(entry, dict) else None
            if name:
                return str(name)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to load doc_type label from registry: %s", exc)

    # Fallback
    cleaned = doc_type.replace("_", " ").replace(".", " ").strip()
    return cleaned.title()


def _get_doc_type_summary(
    doc_type: str,
    rows: list[dict],
    documents: dict[str, dict[str, Any]],
) -> dict:
    """Summary для одного doc_type."""
    doc_ids: set[str] = set()
    check_ids: set[str] = set()
    counts = {
        "critical": 0, "high": 0, "medium": 0,
        "pass": 0, "unclear": 0,
    }
    conditional_fail = 0

    for row in rows:
        doc_ids.add(row.get("document_id", ""))
        check_ids.add(row.get("check_id", ""))

        result_val = row.get("result", "unclear")
        severity = row.get("severity", "medium")

        if _is_issue(result_val):
            if severity in ("critical", "high", "medium"):
                counts[severity] += 1
        elif result_val == "pass":
            counts["pass"] += 1
        else:
            counts["unclear"] += 1

        if row.get("conditional_check_triggered") and _is_issue(result_val):
            conditional_fail += 1

    confidences: list[float] = []
    low_conf_count = 0
    for doc_id in doc_ids:
        doc = documents.get(doc_id, {})
        conf = doc.get("classification_confidence")
        if isinstance(conf, (int, float)):
            confidences.append(conf)
            if conf < 0.6:
                low_conf_count += 1

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "doc_type": doc_type,
        "label": _get_doc_type_label(doc_type),
        "document_count": len(doc_ids),
        "check_count": len(check_ids),
        **counts,
        "avg_classification_confidence": avg_conf,
        "low_confidence_count": low_conf_count,
        "conditional_checks_triggered": conditional_fail,
    }


# Технические поля, которые не показываем в Extracted Values.
# Юристу не нужны статусы/коды/служебные структуры — только значения.
_TECHNICAL_FIELD_EXACT = frozenset({
    "qc", "evidence", "_evidence",
})






def _compute_extracted_values(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    checks_by_id: dict[str, Any] | None = None,
) -> list[dict]:
    """
    Extracted values — плоский список полей из structured_data.

    Фильтрация по `presentation` из ExtractionFieldConfig (playbook-driven):

    - ``fact``        → пользовательские значения (включаются)
    - ``summary``     → human-readable DD Grid value (включается)
    - ``signal``      → внутренние сигналы (ИСКЛЮЧАЮТСЯ; их видно через *_display)
    - ``diagnostic``  → обоснования / reason (включаются с is_diagnostic=True)

    Если для check_id нет CheckDefinition, или поле отсутствует в
    ``check.extraction.fields`` — presentation="fact" (backward compatible,
    не теряем данные из legacy checks).

    Исходные данные в БД (check_results.structured_data) не меняются.
    Метод только формирует плоский view для FactBundle / экспорта.

    Args:
        check_results: список dict'ов из runner_repo.load_check_results_for_run.
        documents: dict[document_id, doc_info].
        checks_by_id: dict[check_id, CheckDefinition] из check_definition_loader.
            None допустимо — тогда все поля трактуются как "fact".

    Returns:
        list[dict] — плоские строки для FactBundle.extracted_values.
    """
    from engine.checks.result_semantics import (
        get_field_config,
        get_field_label,
        get_field_presentation,
        is_field_fallback_value,
    )
    from engine.playbook.models import ExtractionFieldType

    rows: list[dict] = []

    for cr in check_results:
        doc_id = cr.get("document_id", "")
        doc_info = documents.get(doc_id, {})
        structured_data = cr.get("structured_data") or {}

        if not isinstance(structured_data, dict):
            continue

        check_id = cr.get("check_id", "") or ""
        check_def = (checks_by_id or {}).get(check_id)

        cr_page = cr.get("page")
        cr_clause = cr.get("clause_uid", "") or ""

        for field_name, field_raw in structured_data.items():
            if field_name.startswith("_"):
                continue

            presentation = get_field_presentation(check_def, field_name)

            # signal — внутренний сигнал движка, не выводится в отчёт
            if presentation == "signal":
                continue

            # EVIDENCE_LIST — служебный repr (list of dicts), не для отчёта
            cfg = get_field_config(check_def, field_name)
            if cfg is not None and getattr(cfg, "type", None) == ExtractionFieldType.EVIDENCE_LIST:
                continue

            # Извлекаем значение
            if isinstance(field_raw, dict):
                value = field_raw.get("value")
                found = bool(field_raw.get("found"))
                source = field_raw.get("source") or ""
                confidence = field_raw.get("confidence")
                loc = field_raw.get("location") or {}
                page = loc.get("page") or cr_page
                clause_ref = loc.get("clause_ref") or cr_clause
            else:
                value = field_raw
                found = value is not None
                source = ""
                confidence = None
                page = cr_page
                clause_ref = cr_clause

            if value is None and not found:
                continue

            value_str = "" if value is None else str(value).strip()
            if not value_str or value_str == "None":
                continue

            # fallback_texts → negative finding (данные отсутствуют).
            # diagnostic (reason) не считается negative — это пояснение.
            is_negative = (
                presentation != "diagnostic"
                and is_field_fallback_value(check_def, field_name, value_str)
            )

            rows.append({
                "document_id": doc_id,
                "document_name": doc_info.get("name", ""),
                "doc_type": doc_info.get("doc_type", ""),
                "check_id": check_id,
                "check_name": cr.get("check_name", "") or "",
                "field_name": field_name,
                "field_label": get_field_label(check_def, field_name) or "",
                "field_value": value_str,
                "found": found,
                "source": source,
                "confidence": confidence,
                "page": page,
                "clause_ref": clause_ref,
                "presentation": presentation,
                "is_diagnostic": presentation == "diagnostic",
                "is_negative": is_negative,
            })

    # Сортировка: document → check → presentation (fact/summary сначала,
    # diagnostic в конце) → field_name (алфавитно, детерминированно).
    presentation_order = {"fact": 0, "summary": 1, "diagnostic": 2}
    rows.sort(key=lambda r: (
        (r.get("document_name") or "").lower(),
        (r.get("check_name") or "").lower(),
        presentation_order.get(r.get("presentation", "fact"), 9),
        (r.get("field_name") or "").lower(),
    ))

    return rows

def _compute_requests(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    checks_by_id: dict[str, Any],
    locale: str,
) -> list[dict]:
    """DD requests — из report_builder._build_dd_requests_for_report."""
    try:
        from services.export.report_builder import _build_dd_requests_for_report
        return _build_dd_requests_for_report(
            check_results, documents, checks_by_id, locale=locale
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to build DD requests: %s", exc)
        return []


def _build_documents_reviewed(
    documents: dict[str, dict[str, Any]],
) -> list[dict]:
    """
    Appendix C — таблица документов.

    Используем поля, которые реально есть в documents (см. core.py):
    name, folder_path, doc_type, status, classification_*,
    applicable_triggers, language.
    """
    rows: list[dict] = []
    for doc_id, doc in documents.items():
        rows.append({
            "document_id": doc_id,
            "name": doc.get("name", ""),
            "folder_path": doc.get("folder_path", ""),
            "doc_type": doc.get("doc_type", ""),
            "doc_type_label": _get_doc_type_label(doc.get("doc_type", "")),
            "status": doc.get("status", ""),
            "classification_level": doc.get("classification_level", ""),
            "classification_confidence": doc.get("classification_confidence", 0.0),
            "classification_requires_review": bool(
                doc.get("classification_requires_review", False)
            ),
            "language": doc.get("language", "") or "",
        })
    return rows


def _to_serializable(obj: Any) -> Any:
    """Рекурсивно превращает dataclass/dict/list в JSON-сериализуемое."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_serializable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(v) for v in obj]
    if isinstance(obj, set):
        return sorted(_to_serializable(v) for v in obj)
    return obj