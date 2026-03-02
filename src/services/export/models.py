"""
Aggregator & Exporter Data Models.

Defines:
- SeverityCounts: how many results per severity level
- TopRisk: a single high-priority finding for summary
- DDRequest: a generated request for additional information (with addressee)
- AggregatedResults: complete deal-level summary
- ExportRow: a single row in the DD Grid Excel
- ConditionalCheckRow: row for conditional checks sheet
- StructuredValueRow: extracted structured values (amounts, dates, etc.)
- DocTypeSummary: per-doc-type aggregation with classification metadata
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SeverityCounts:
    """Count of check results by severity level."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    pass_count: int = 0
    unclear: int = 0

    @property
    def total(self) -> int:
        return self.critical + self.high + self.medium + self.pass_count + self.unclear

    @property
    def fail_total(self) -> int:
        return self.critical + self.high + self.medium

    def to_dict(self) -> dict:
        return {
            "critical": self.critical,
            "high": self.high,
            "medium": self.medium,
            "pass": self.pass_count,
            "unclear": self.unclear,
            "total": self.total,
            "fail_total": self.fail_total,
        }


@dataclass
class TopRisk:
    """A single high-priority finding for the summary."""

    check_id: str
    check_name: str
    severity: str
    document_name: str
    document_id: str
    doc_type: str
    evidence_snippet: str
    page: int | None = None
    clause_uid: str = ""
    confidence: float = 0.0
    # NEW: structured data extracted by check
    structured_data: dict[str, Any] = field(default_factory=dict)
    # NEW: was this triggered by a conditional trigger?
    conditional_check_triggered: bool = False
    trigger_name: str = ""

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "severity": self.severity,
            "document_name": self.document_name,
            "document_id": self.document_id,
            "doc_type": self.doc_type,
            "evidence_snippet": self.evidence_snippet[:300],
            "page": self.page,
            "clause_uid": self.clause_uid,
            "confidence": round(self.confidence, 3),
            "structured_data": self.structured_data,
            "conditional_check_triggered": self.conditional_check_triggered,
            "trigger_name": self.trigger_name,
        }


@dataclass
class DDRequest:
    """
    A generated DD request for additional information.

    Created from FAIL/HIGH check results. Deduplicated by check_id.
    Text loaded from YAML dd_request_templates section.
    """

    request_id: str
    check_id: str
    check_name: str
    priority: str
    text: str
    # NEW: addressee from YAML dd_request_templates
    addressee: str = "Юридический советник"
    document_ids: list[str] = field(default_factory=list)
    document_names: list[str] = field(default_factory=list)
    doc_types: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    # NEW: structured data values (amounts, dates) referenced in request
    structured_values: list[dict] = field(default_factory=list)
    dedup_key: str = ""

    @property
    def document_count(self) -> int:
        return len(self.document_ids)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "check_id": self.check_id,
            "check_name": self.check_name,
            "priority": self.priority,
            "text": self.text,
            "addressee": self.addressee,
            "document_ids": self.document_ids,
            "document_names": self.document_names,
            "doc_types": self.doc_types,
            "document_count": self.document_count,
            "structured_values": self.structured_values,
        }


@dataclass
class ExportRow:
    """A single row in the DD Grid Excel."""

    document_name: str
    folder_path: str
    doc_type: str
    check_name: str
    check_id: str
    result: str
    severity: str
    evidence_snippet: str
    page: int | None = None
    clause_uid: str = ""
    confidence: float = 0.0
    detector_used: str = ""
    quality_flags: str = ""
    qc_status: str = "pending"
    document_id: str = ""
    run_id: str = ""
    # NEW: structured extraction result (e.g. amount=5_000_000)
    structured_data_preview: str = ""
    # NEW: conditional check metadata
    conditional_check_triggered: bool = False
    trigger_name: str = ""
    # NEW: classification metadata
    classification_level: str = ""  # L0-L4
    classification_confidence: float = 0.0


@dataclass
class ConditionalCheckRow:
    """
    A row representing a triggered conditional check result.

    Used in the separate 'Conditional Checks' sheet in Excel.
    Provides visibility into which triggers fired and why.
    """

    document_name: str
    doc_type: str
    trigger_name: str
    check_id: str
    check_name: str
    result: str
    severity: str
    evidence_snippet: str
    page: int | None = None
    confidence: float = 0.0
    quality_flags: str = ""


@dataclass
class StructuredValueRow:
    """
    A structured value extracted from a document.

    Used in the 'Extracted Values' sheet — amounts, dates,
    parties, key terms extracted by structured_extraction checks.
    """

    document_name: str
    doc_type: str
    check_name: str
    field_name: str  # e.g. "amount", "effective_date", "parties"
    field_value: str  # e.g. "5 000 000 руб.", "01.01.2025", "ООО Альфа"
    field_format: str  # e.g. "money_or_not_found", "date", "entity_name"
    page: int | None = None
    clause_uid: str = ""
    document_id: str = ""


@dataclass
class DocTypeSummary:
    """
    Per-document-type aggregation row for the By Doc Type sheet.
    Extended with classification quality metadata.
    """

    doc_type: str
    document_count: int = 0
    check_count: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    pass_count: int = 0
    unclear: int = 0
    # NEW: classification quality
    avg_classification_confidence: float = 0.0
    low_confidence_count: int = 0  # docs with confidence < 0.6
    conditional_checks_triggered: int = 0


@dataclass
class AggregatedResults:
    """Complete deal-level aggregation."""

    deal_id: str
    deal_name: str
    run_id: str
    severity_counts: SeverityCounts = field(default_factory=SeverityCounts)
    top_risks: list[TopRisk] = field(default_factory=list)
    dd_requests: list[DDRequest] = field(default_factory=list)
    rows: list[ExportRow] = field(default_factory=list)
    # NEW: conditional check rows (only triggered ones)
    conditional_rows: list[ConditionalCheckRow] = field(default_factory=list)
    # NEW: structured value rows
    structured_value_rows: list[StructuredValueRow] = field(default_factory=list)
    # NEW: per-doc-type summaries
    doc_type_summaries: list[DocTypeSummary] = field(default_factory=list)
    total_documents: int = 0
    total_checks: int = 0
    quarantine_count: int = 0
    degraded_count: int = 0
    evidence_validity_rate: float = 1.0
    # NEW: conditional checks stats
    conditional_checks_total: int = 0
    conditional_checks_triggered: int = 0

    def to_dict(self) -> dict:
        return {
            "deal_id": self.deal_id,
            "deal_name": self.deal_name,
            "run_id": self.run_id,
            "severity_counts": self.severity_counts.to_dict(),
            "top_risks": [r.to_dict() for r in self.top_risks],
            "dd_requests": [r.to_dict() for r in self.dd_requests],
            "total_documents": self.total_documents,
            "total_checks": self.total_checks,
            "quarantine_count": self.quarantine_count,
            "degraded_count": self.degraded_count,
            "evidence_validity_rate": round(self.evidence_validity_rate, 3),
            "conditional_checks_total": self.conditional_checks_total,
            "conditional_checks_triggered": self.conditional_checks_triggered,
        }
