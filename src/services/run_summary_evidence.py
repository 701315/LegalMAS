# src/services/run_summary_evidence.py

"""
RunSummaryEvidenceBuilder — собирает canonical evidence package для LLM.

Принцип (production-стандарт LegalTech):
LLM НЕ читает исходные документы. Она читает сжатый, детерминированно
агрегированный пакет структурированных findings:

- scope        — сделка, режим проверок, статус run;
- coverage     — полнота обработки (total / failed / quarantine / review);
- classification — уверенность классификации, low-confidence документы;
- risk_distribution — счётчики по severity;
- material_checks   — топ значимых рисков (check_id, name, severity,
                      doc_types, count, примеры файлов);
- global_checks     — фокус глобальных проверок + чистые блоки;
- doc_type_checks   — риски по типам документов + low-confidence checks;
- open_items        — что требует внимания/ограничений.

Все агрегации детерминированные (SQL + сортировка), LLM не решает,
что критично — это делает domain model.
"""

import uuid
from collections import defaultdict
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.deal import Deal
from db.models.document import Document
from db.models.result import CheckResult
from db.models.run import Run
from services.run_analytics_service import RunAnalyticsService

logger = get_logger(__name__)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "unclear": 3}
_MATERIAL_SEVERITIES = {"critical", "high", "medium"}

_CHECKS_MODE_LABELS = {
    "global_only": "только глобальные проверки playbook",
    "doc_type_only": "только проверки по типам документов",
    "global_and_doc_type": (
        "совместный режим: глобальные проверки playbook и проверки по типам документов"
    ),
}

# Ограничения размера пакета, чтобы не перегружать контекст локальной LLM.
_MAX_MATERIAL_CHECKS = 12
_MAX_DOC_TYPES = 6
_MAX_SAMPLES = 3
_MAX_VALUE_CHARS = 300


class RunSummaryEvidenceBuilder:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def build(self, run_id: uuid.UUID) -> dict[str, Any]:
        """Собрать evidence package для run."""
        run = await self.session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")

        deal = await self.session.get(Deal, run.deal_id)

        # ── Классификация (переиспользуем существующий сервис) ────────
        analytics = RunAnalyticsService(self.session)
        report = await analytics.build_classification_report(run_id)

        # ── Check results с типами документов ─────────────────────────
        stmt = (
            select(
                CheckResult.check_id,
                CheckResult.check_name,
                CheckResult.severity,
                CheckResult.origin,
                CheckResult.confidence,
                CheckResult.needs_manual_review,
                CheckResult.value_text,
                Document.doc_type,
                Document.filename,
            )
            .join(Document, Document.id == CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        # ── Агрегации ─────────────────────────────────────────────────
        risk_distribution: dict[str, int] = {
            "critical": 0, "high": 0, "medium": 0, "unclear": 0
        }
        checks_meta: dict[str, dict] = {}          # check_id -> meta
        problem_check_ids: set[str] = set()
        low_conf_checks: dict[str, int] = defaultdict(int)
        manual_review_count = 0

        for row in rows:
            severity = (row.severity or "").lower()

            if severity in risk_distribution:
                risk_distribution[severity] += 1

            if row.needs_manual_review:
                manual_review_count += 1

            if severity in _MATERIAL_SEVERITIES:
                problem_check_ids.add(row.check_id)

                meta = checks_meta.setdefault(row.check_id, {
                    "check_id": row.check_id,
                    "check_name": row.check_name,
                    "severity": severity,
                    "origin": row.origin,
                    "doc_types": set(),
                    "count": 0,
                    "samples": [],
                })
                # Худшая severity по check
                if _SEVERITY_ORDER[severity] < _SEVERITY_ORDER[meta["severity"]]:
                    meta["severity"] = severity
                meta["count"] += 1
                if row.doc_type:
                    meta["doc_types"].add(row.doc_type)
                if len(meta["samples"]) < _MAX_SAMPLES and row.filename:
                    meta["samples"].append(row.filename)

                # Low-confidence LLM-детекции по значимым рискам
                if (
                    severity in ("critical", "high")
                    and row.confidence is not None
                    and row.confidence < 0.6
                ):
                    low_conf_checks[row.check_id] += 1

        # ── Material checks: сортировка детерминированная ─────────────
        material_checks = [
            {
                "check_id": m["check_id"],
                "check_name": m["check_name"],
                "severity": m["severity"],
                "origin": m["origin"],
                "doc_types": sorted(m["doc_types"])[:_MAX_DOC_TYPES],
                "count": m["count"],
                "samples": m["samples"],
            }
            for m in checks_meta.values()
        ]
        material_checks.sort(
            key=lambda c: (_SEVERITY_ORDER.get(c["severity"], 9), -c["count"])
        )
        material_checks = material_checks[:_MAX_MATERIAL_CHECKS]

        # ── Риски по типам документов ─────────────────────────────────
        doc_type_risk_counts: dict[str, int] = defaultdict(int)
        for row in rows:
            if (row.severity or "").lower() in ("critical", "high") and row.doc_type:
                doc_type_risk_counts[row.doc_type] += 1
        top_doc_types = sorted(
            doc_type_risk_counts.items(), key=lambda kv: (-kv[1], kv[0])
        )[:_MAX_DOC_TYPES]

        # ── Глобальные проверки: фокус и чистые блоки ─────────────────
        executed_by_origin: dict[str, dict[str, str]] = defaultdict(dict)
        for row in rows:
            if row.origin:
                executed_by_origin[row.origin].setdefault(row.check_id, row.check_name)

        global_executed = executed_by_origin.get("global_playbook", {})
        global_material = [
            c for c in material_checks if c["origin"] == "global_playbook"
        ]
        global_clean = [
            global_executed[cid]
            for cid in global_executed
            if cid not in problem_check_ids
        ]

        doc_type_material = [
            c for c in material_checks if c["origin"] == "document_type_playbook"
        ]

        # ── Coverage ──────────────────────────────────────────────────
        total_documents = report.total_documents
        failed = run.failed_docs_count or 0
        quarantine = run.quarantine_docs_count or 0
        pending_review = len(report.low_confidence_docs) + len(report.unknown_type_docs)
        processed = max(0, total_documents - failed - quarantine)

        # ── Open items ────────────────────────────────────────────────
        open_items: list[str] = []
        if failed:
            open_items.append(f"{failed} документ(ов) не прошли обработку")
        if quarantine:
            open_items.append(f"{quarantine} документ(ов) в карантине")
        if report.low_confidence_docs:
            open_items.append(
                f"{len(report.low_confidence_docs)} документ(ов) с низкой "
                f"уверенностью классификации — требуется ручная проверка типа"
            )
        if report.unknown_type_docs:
            open_items.append(
                f"{len(report.unknown_type_docs)} документ(ов) с нераспознанным типом"
            )
        if manual_review_count:
            open_items.append(
                f"{manual_review_count} проверок помечены на ручную ревизию"
            )

        evidence: dict[str, Any] = {
            "scope": {
                "deal_name": deal.name if deal else None,
                "checks_mode": run.checks_mode,
                "checks_mode_label": _CHECKS_MODE_LABELS.get(
                    run.checks_mode, run.checks_mode
                ),
                "run_status": run.status,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            },
            "coverage": {
                "total": total_documents,
                "processed": processed,
                "failed": failed,
                "quarantine": quarantine,
                "pending_review": pending_review,
            },
            "classification": {
                "low_confidence_count": len(report.low_confidence_docs),
                "low_confidence_examples": [
                    d.get("filename") for d in report.low_confidence_docs[:5]
                ],
                "unknown_type_count": len(report.unknown_type_docs),
            },
            "risk_distribution": risk_distribution,
            "material_checks": material_checks,
            "global_checks": {
                "focus": [c["check_name"] for c in global_material]
                + global_clean,
                "clean": global_clean,
                "key_risks": global_material,
            },
            "doc_type_checks": {
                "key_risks": doc_type_material,
                "top_risky_doc_types": [
                    {"doc_type": dt, "critical_high_count": n}
                    for dt, n in top_doc_types
                ],
                "low_confidence_checks": [
                    {"check_id": cid, "count": n}
                    for cid, n in sorted(low_conf_checks.items())
                ],
            },
            "open_items": open_items,
        }

        logger.info(
            "Run summary evidence built",
            run_id=str(run_id),
            total_documents=total_documents,
            material_checks=len(material_checks),
            critical=risk_distribution["critical"],
            high=risk_distribution["high"],
        )
        return evidence


        