# src/core/document_columns.py

"""
Document columns definition (single source of truth for the backend).

Used:
- for exports (Excel / Word / PDF);
- for potential frontend type generation in the future.

Note:
- Not all columns correspond directly to raw fields of the ORM Document model;
- Some columns can be computed read-model columns (e.g. applicable_triggers_count or composition type);
- The DocumentColumnDef.field attribute is interpreted as:
  * either the name of an actual Document model attribute;
  * or a pseudo-field name handled by the export/read layer.
"""

from dataclasses import dataclass
from typing import Literal

# Complete list of column IDs (synchronized with frontend src/types/index.ts)
DocumentColumnId = Literal[
    "filename",
    "folder_path",
    "doc_type",
    "status",
    "human_review_status",
    "reviewed_by_person",
    "risk_level",
    "language",
    "jurisdiction_guess",
    "page_count",
    "classification_level",
    "classification_confidence",
    "applicable_triggers_count",
    "composition_type",
    "segment_count",
    "primary_segment_label",
    "is_composite_file",
    "created_at",
    "updated_at",
    "id",
    "deal_id",
]


@dataclass(frozen=True)
class DocumentColumnDef:
    """
    Definition of a single document column.

    id:
        Unique column identifier (used in settings, exports, and filtering).
    label:
        Human-readable header label (used for Excel/Word/PDF and optionally the frontend).
    description:
        Brief explanation of the column meaning.
    field:
        Name of the attribute in the Document model or a custom pseudo-field alias
        (e.g., "applicable_triggers_count", "composition_type").
    default_visible:
        Whether the column is visible by default (used by both backend and frontend).
    """

    id: DocumentColumnId
    label: str
    description: str
    field: str  # Document model attribute name or alias
    default_visible: bool


# Full list of all possible document columns.
# 1:1 match with frontend ALL_DOCUMENT_COLUMNS.
ALL_DOCUMENT_COLUMNS: list[DocumentColumnDef] = [
    DocumentColumnDef(
        id="filename",
        label="Document Name",
        description="The filename of the document inside the Data Room.",
        field="filename",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="folder_path",
        label="Folder",
        description="Path to the document within the Data Room structure.",
        field="folder_path",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="doc_type",
        label="Document Type",
        description="The classified document type (e.g., SPA, NDA).",
        field="doc_type",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="status",
        label="Processing Status",
        description="Current processing status of the document in the pipeline.",
        field="status",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="human_review_status",
        label="Lawyer Review Status",
        description="Human-readable status of the lawyer verification process.",
        field="human_review_status",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="reviewed_by_person",
        label="Review Flag",
        description="Boolean flag indicating if the document has been reviewed by a lawyer.",
        field="reviewed_by_person",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="risk_level",
        label="Risk Level",
        description="Overall risk level of the document: low/medium/high/critical.",
        field="risk_level",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="language",
        label="Language",
        description="The primary language of the document (RU, EN, etc.).",
        field="language",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="jurisdiction_guess",
        label="Jurisdiction",
        description="Assumed jurisdiction applicable to the document.",
        field="jurisdiction_guess",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="page_count",
        label="Pages",
        description="Total page count of the document.",
        field="page_count",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="classification_level",
        label="Classification Level",
        description="The pipeline level at which the document type was resolved (L0–L4, L_manual).",
        field="classification_level",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="classification_confidence",
        label="Classification Confidence",
        description="Confidence score (value between 0 and 1) for the resolved document type.",
        field="classification_confidence",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="applicable_triggers_count",
        label="Triggers",
        description="Number of triggered check triggers associated with this document.",
        field="applicable_triggers_count",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="composition_type",
        label="File Composition",
        description=(
            "Indicates if the file contains a single logical document ('single') "
            "or multiple appended documents ('multi')."
        ),
        field="composition_type",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="segment_count",
        label="Segments",
        description="Total number of logical documents (segments) discovered inside the file.",
        field="segment_count",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="primary_segment_label",
        label="Primary Segment",
        description="Human-readable name of the primary logical document inside the file.",
        field="primary_segment_label",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="is_composite_file",
        label="Composite File",
        description="Boolean flag indicating if the file contains multiple logically isolated documents.",
        field="is_composite_file",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="created_at",
        label="Created At",
        description="Timestamp when the document was uploaded to the deal.",
        field="created_at",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="updated_at",
        label="Updated At",
        description="Timestamp of the last modification to the document metadata.",
        field="updated_at",
        default_visible=True,
    ),
    DocumentColumnDef(
        id="id",
        label="Document ID",
        description="Unique technical identifier of the document (UUID).",
        field="id",
        default_visible=False,
    ),
    DocumentColumnDef(
        id="deal_id",
        label="Deal ID",
        description="Unique identifier of the deal associated with this document.",
        field="deal_id",
        default_visible=False,
    ),
]


# Convenient helper functions for exports and settings


def get_column_by_id(column_id: DocumentColumnId) -> DocumentColumnDef:
    for col in ALL_DOCUMENT_COLUMNS:
        if col.id == column_id:
            return col
    raise KeyError(f"Unknown DocumentColumnId: {column_id!r}")


def get_columns_by_ids(ids: list[DocumentColumnId] | None) -> list[DocumentColumnDef]:
    if not ids:
        return list(ALL_DOCUMENT_COLUMNS)
    existing_ids = {col.id for col in ALL_DOCUMENT_COLUMNS}
    unknown = [c for c in ids if c not in existing_ids]
    if unknown:
        raise KeyError(f"Unknown column ids: {unknown!r}")
    return [get_column_by_id(cid) for cid in ids]


def get_default_visible_ids() -> list[DocumentColumnId]:
    return [c.id for c in ALL_DOCUMENT_COLUMNS if c.default_visible]
