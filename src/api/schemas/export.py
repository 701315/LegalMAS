# src/api/schemas/export.py

"""
Pydantic schemas for the export API.

Purpose of this module:
- Defines the input payload format for export trigger requests;
- Defines the output response schemas for export job status;
- Decouples the ORM Export model from the public API contract;
- Facilitates the safe inclusion of computed attributes like download_url.

Note:
- The ORM model resides in db/models/export.py and manages persistence;
- The schemas below handle API serialization and request validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Allowed export format types.
# Can be expanded if additional formats are introduced in future releases.
ExportType = Literal[
    "grid_xlsx",
    "deal_summary_xlsx",
    "report_docx",
    "aggregated_json",
]

# Allowed export lifecycle status values.
ExportStatus = Literal[
    "pending",
    "processing",
    "completed",
    "failed",
]


class ExportRequest(BaseModel):
    """
    Request body for initiating an export job for a single run.

    Corresponds to endpoint:
        POST /api/v1/runs/{run_id}/export
    """

    export_type: ExportType = Field(
        ...,
        description="Type of export format: grid_xlsx, deal_summary_xlsx, report_docx, aggregated_json",
        examples=["deal_summary_xlsx"],
    )

    requested_by: str | None = Field(
        default=None,
        description="Identifier or email of the user who requested the export",
        examples=["admin@legalmas.local"],
    )

    requester_role: str | None = Field(
        default=None,
        description="Project workspace role of the user at request time",
        examples=["editor"],
    )


class ExportRecord(BaseModel):
    """
    Public API schema representing a single export record.

    Provides a clean response representation for UI clients:
    - Core Export entity attributes from the database;
    - file_ref / file_refs for debugging and backward compatibility;
    - download_url as a computed convenience field when artifacts are ready.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deal_id: UUID
    run_id: UUID

    export_type: ExportType = Field(
        ...,
        description="Type of export artifact",
        examples=["report_docx"],
    )

    status: ExportStatus = Field(
        ...,
        description="Export job status. For completed jobs, file_ref is guaranteed; download_url is computed from it.",
        examples=["completed"],
    )

    file_ref: str | None = Field(
        default=None,
        description="Primary artifact storage reference",
        examples=["exports/deal-123/run-456/deal_summary.xlsx"],
    )

    file_refs: dict[str, Any] | None = Field(
        default=None,
        description="Additional file references if multiple artifacts were produced",
        examples=[{"main": "exports/deal-123/run-456/report.docx"}],
    )

    requested_by: str | None = Field(
        default=None,
        description="User who initiated the export job",
        examples=["admin@legalmas.local"],
    )

    requester_role: str | None = Field(
        default=None,
        description="Workspace role of the requester at creation time",
        examples=["admin"],
    )

    file_size_bytes: int | None = Field(
        default=None,
        description="Total artifact size in bytes, if available",
        examples=[245760],
    )

    created_at: datetime | None = Field(
        default=None,
        description="Creation timestamp of the export record",
    )

    updated_at: datetime | None = Field(
        default=None,
        description="Last updated timestamp of the export record",
    )

    download_url: str | None = Field(
        default=None,
        description="Direct download URL. Available for completed jobs when storage resolves file_ref.",
        examples=["/api/v1/exports/3fa85f64-5717-4562-b3fc-2c963f66afa6/download"],
    )

    error_message: str | None = Field(
        default=None,
        description="Error detail message if export processing failed",
        examples=["Export generation failed"],
    )


class ExportListResponse(BaseModel):
    """
    Response schema for paginated or batch lists of export records.

    Used by endpoints such as:
        GET /api/v1/runs/{run_id}/exports
        GET /api/v1/deals/{deal_id}/exports
    """

    items: list[ExportRecord]
    total: int = Field(..., description="Total count of export records")
