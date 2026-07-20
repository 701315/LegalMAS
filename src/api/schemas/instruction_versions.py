# src/api/schemas/instruction_versions.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


InstructionVersionStatus = Literal["draft", "published", "archived"]


class InstructionVersionItem(BaseModel):
    id: str
    doc_type_code: str
    name: str | None = None
    source_format: str
    source_sha256: str
    version_status: InstructionVersionStatus
    immutable_content_hash: str | None = None
    validation_report: dict[str, Any] | None = None
    parent_version_id: str | None = None
    published_at: datetime | None = None
    created_by: str | None = None
    change_summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InstructionVersionDetailItem(InstructionVersionItem):
    source_yaml: str
    source_path: str | None = None
    git_commit: str | None = None
    semver: str | None = None
    compiled_payload: dict[str, Any] | None = None
    checks_count: int | None = None


class InstructionCatalogItem(BaseModel):
    doc_type_code: str
    name: str
    category: str | None = None
    risk_level: str | None = None
    language: str | None = None
    jurisdiction: str | None = None
    is_registry_available: bool = True

    total_versions_count: int = 0
    draft_versions_count: int = 0
    has_published: bool = False

    latest_version_id: str | None = None
    latest_version_status: InstructionVersionStatus | None = None
    latest_version_updated_at: datetime | None = None

    latest_published_version_id: str | None = None
    latest_published_at: datetime | None = None
    latest_published_immutable_content_hash: str | None = None

    latest_draft_version_id: str | None = None
    latest_draft_is_valid: bool | None = None
    latest_draft_updated_at: datetime | None = None


class InstructionCatalogResponse(BaseModel):
    items: list[InstructionCatalogItem] = Field(default_factory=list)


class InstructionVersionListResponse(BaseModel):
    doc_type_code: str
    items: list[InstructionVersionItem] = Field(default_factory=list)


class InstructionVersionResponse(BaseModel):
    item: InstructionVersionItem


class InstructionVersionDetailResponse(BaseModel):
    item: InstructionVersionDetailItem


class InstructionVersionValidationResponse(BaseModel):
    item: InstructionVersionItem
    is_valid: bool
    checks_count: int
    validation_report: dict[str, Any]


class CreateInstructionDraftRequest(BaseModel):
    source_yaml: str
    name: str | None = None
    source_path: str | None = None
    git_commit: str | None = None
    semver: str | None = None
    change_summary: str | None = None
    parent_version_id: UUID | None = None


class UpdateInstructionDraftRequest(BaseModel):
    source_yaml: str
    name: str | None = None
    source_path: str | None = None
    git_commit: str | None = None
    semver: str | None = None
    change_summary: str | None = None


class CloneDraftRequest(BaseModel):
    change_summary: str | None = None


class PreviewInstructionRequest(BaseModel):
    source_yaml: str


class PreviewInstructionResponse(BaseModel):
    is_valid: bool
    checks_count: int
    triggers_used: list[str] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    validation_report: dict[str, Any]
    compiled_payload: dict[str, Any]
    source_sha256: str
    already_exists: bool
    existing_version_id: str | None = None


class InstructionDiffResponse(BaseModel):
    from_version_id: str
    to_version_id: str
    from_source_sha256: str
    to_source_sha256: str
    are_identical: bool
    unified_diff: list[str] = Field(default_factory=list)


