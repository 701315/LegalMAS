# src/api/schemas/global_instruction_versions.py

"""
Schemas для global instruction version API.
Зеркало instruction_versions.py с instruction_code вместо doc_type_code,
group как дополнительное поле.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

GlobalInstructionVersionStatus = Literal["draft", "published", "archived"]


class GlobalInstructionVersionItem(BaseModel):
    id: str
    instruction_code: str
    name: str | None = None
    group: str | None = None
    source_format: str
    source_sha256: str
    version_status: GlobalInstructionVersionStatus
    immutable_content_hash: str | None = None
    validation_report: dict[str, Any] | None = None
    parent_version_id: str | None = None
    published_at: datetime | None = None
    created_by: str | None = None
    change_summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GlobalInstructionVersionDetailItem(GlobalInstructionVersionItem):
    source_yaml: str
    source_path: str | None = None
    git_commit: str | None = None
    semver: str | None = None
    compiled_payload: dict[str, Any] | None = None


class GlobalInstructionCatalogItem(BaseModel):
    instruction_code: str
    name: str
    group: str | None = None
    total_versions_count: int = 0
    draft_versions_count: int = 0
    has_published: bool = False
    latest_version_id: str | None = None
    latest_version_status: GlobalInstructionVersionStatus | None = None
    latest_version_updated_at: datetime | None = None
    latest_published_version_id: str | None = None
    latest_published_at: datetime | None = None
    latest_published_immutable_content_hash: str | None = None
    latest_draft_version_id: str | None = None
    latest_draft_is_valid: bool | None = None
    latest_draft_updated_at: datetime | None = None


class GlobalInstructionCatalogResponse(BaseModel):
    items: list[GlobalInstructionCatalogItem] = Field(default_factory=list)


class GlobalInstructionVersionListResponse(BaseModel):
    instruction_code: str
    items: list[GlobalInstructionVersionItem] = Field(default_factory=list)


class GlobalInstructionVersionResponse(BaseModel):
    item: GlobalInstructionVersionItem


class GlobalInstructionVersionDetailResponse(BaseModel):
    item: GlobalInstructionVersionDetailItem


class GlobalInstructionVersionValidationResponse(BaseModel):
    item: GlobalInstructionVersionItem
    is_valid: bool
    validation_report: dict[str, Any]


class CreateGlobalInstructionDraftRequest(BaseModel):
    source_yaml: str
    name: str | None = None
    source_path: str | None = None
    git_commit: str | None = None
    semver: str | None = None
    change_summary: str | None = None
    parent_version_id: UUID | None = None


class UpdateGlobalInstructionDraftRequest(BaseModel):
    source_yaml: str
    name: str | None = None
    source_path: str | None = None
    git_commit: str | None = None
    semver: str | None = None
    change_summary: str | None = None


class CloneGlobalDraftRequest(BaseModel):
    change_summary: str | None = None


class PreviewGlobalInstructionRequest(BaseModel):
    source_yaml: str


class PreviewGlobalInstructionResponse(BaseModel):
    is_valid: bool
    instruction_code: str
    group: str | None = None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    validation_report: dict[str, Any]
    compiled_payload: dict[str, Any]
    source_sha256: str
    already_exists: bool
    existing_version_id: str | None = None


class GlobalInstructionDiffResponse(BaseModel):
    from_version_id: str
    to_version_id: str
    from_source_sha256: str
    to_source_sha256: str
    are_identical: bool
    unified_diff: list[str] = Field(default_factory=list)


    