# src/api/schemas/instruction_overrides.py

"""
Pydantic schemas for instruction overrides and preview endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── Override schemas ──────────────────────────────────────────────────────────

class InstructionOverrideItem(BaseModel):
    """A single override in a list or response."""

    id: str
    instruction_version_id: str | None = None
    global_instruction_version_id: str | None = None
    override_scope: Literal["tenant", "deal"]
    tenant_id: str
    deal_id: str | None = None
    status: Literal["draft", "active", "archived"]
    base_content_hash: str
    patch_ops: list[dict[str, Any]]
    is_stale: bool
    change_summary: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GlobalInstructionOverrideDraftRequest(BaseModel):
    global_instruction_version_id: UUID
    patch_ops: list[dict[str, Any]] = Field(
        default_factory=list,
        description="RFC 6902 JSON Patch operations",
    )
    change_summary: str | None = None
    

class InstructionOverrideListResponse(BaseModel):
    items: list[InstructionOverrideItem] = Field(default_factory=list)


class InstructionOverrideDraftRequest(BaseModel):
    instruction_version_id: UUID
    patch_ops: list[dict[str, Any]] = Field(
        default_factory=list,
        description="RFC 6902 JSON Patch operations",
    )
    change_summary: str | None = None


class InstructionOverrideRebaseRequest(BaseModel):
    new_base_version_id: UUID
    new_patch_ops: list[dict[str, Any]] = Field(
        default_factory=list,
        description="RFC 6902 JSON Patch operations for new base version",
    )
    change_summary: str | None = None


class InstructionOverrideValidationResponse(BaseModel):
    override_id: str
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks_count: int | None = None
    effective_payload: dict[str, Any] | None = None
    validation_report: dict[str, Any] | None = None


class InstructionOverrideResponse(BaseModel):
    item: InstructionOverrideItem


# ── Preview schemas ───────────────────────────────────────────────────────────

class InstructionPreviewRequest(BaseModel):
    """
    Unified preview request.

    Allows previewing effective payload with an optional tenant/deal override.
    """
    kind: Literal["doc_type"] = "doc_type"
    doc_type_code: str
    base_version_id: UUID | None = None
    tenant_override_id: UUID | None = None
    deal_override_id: UUID | None = None
    draft_patch_ops: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Optional patch ops for live preview without saving to the database. "
            "Applied on top of tenant/deal override if specified."
        ),
    )


class InstructionPreviewResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    base_version_id: str | None = None
    base_hash: str | None = None
    effective_hash: str | None = None
    effective_payload: dict[str, Any] | None = None
    checks_count: int | None = None
    check_id_collisions: list[str] = Field(default_factory=list)
    diff: list[str] = Field(default_factory=list)


# ── Run snapshot schemas ──────────────────────────────────────────────────────

class RunInstructionSnapshotResponse(BaseModel):
    """
    Frozen instruction snapshot for a historical Run.

    Shows exact instruction versions, hashes, and effective payloads
    frozen at the moment of Run execution.
    """
    run_id: str
    deal_id: str
    snapshot_schema_version: int | None
    is_reproducible: bool
    instruction_versions: dict[str, str] = Field(
        default_factory=dict,
        description="{doc_type: version_id}",
    )
    instruction_snapshot_manifest: dict[str, Any] | None = None
    execution_manifest: dict[str, Any] | None = None
    doc_types_count: int = 0
    warning: str | None = None


    