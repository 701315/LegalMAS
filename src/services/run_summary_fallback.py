# src/services/run_summary_fallback.py

"""
Deterministic fallback для резюме.

Строится ТОЛЬКО из evidence package, без LLM. Гарантирует, что
пользователь всегда видит проверяемую сводку — даже если LLM
недоступна или валидация claims не прошла.
"""

from typing import Any


def build_fallback(evidence: dict[str, Any]) -> dict[str, Any]:
    """Построить structured fallback payload из evidence package."""
    coverage = evidence.get("coverage", {})
    risk_distribution = evidence.get("risk_distribution", {})
    material_checks = evidence.get("material_checks", [])

    top_findings = [
        {
            "check_id": c["check_id"],
            "check_name": c["check_name"],
            "severity": c["severity"],
            "doc_types": c["doc_types"],
            "count": c["count"],
        }
        for c in material_checks[:8]
    ]

    actions = []
    if risk_distribution.get("critical", 0) > 0:
        actions.append(
            {"label": "Открыть критические находки", "filter": {"severity": "critical"}}
        )
    if coverage.get("pending_review", 0) > 0:
        actions.append(
            {"label": "Проверить документы с низкой уверенностью",
             "filter": {"low_confidence": True}}
        )
    if coverage.get("failed", 0) > 0 or coverage.get("quarantine", 0) > 0:
        actions.append(
            {"label": "Открыть список документов", "filter": {"tab": "documents"}}
        )

    return {
        "title": "Ключевые показатели анализа",
        "coverage": {
            "total": coverage.get("total", 0),
            "processed": coverage.get("processed", 0),
            "failed": coverage.get("failed", 0),
            "quarantine": coverage.get("quarantine", 0),
            "pending_review": coverage.get("pending_review", 0),
        },
        "risk_distribution": risk_distribution,
        "top_findings": top_findings,
        "open_items": evidence.get("open_items", []),
        "actions": actions,
        "source": "deterministic_evidence_package",
    }



    