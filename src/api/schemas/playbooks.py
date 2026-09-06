# src/api/schemas/playbooks.py

"""
Pydantic schemas for playbooks (Playbook / PlaybookVersion) and playbook builder.

Purpose of these models:
- Describe requests/responses for /playbooks endpoints (see endpoints/playbooks.py);
- Separate the external API (visible to the frontend) from internal ORM models and YAML;
- Document the API contract:
  * PlaybookCreateRequest — how frontend describes the playbook configuration
    (bundles + include_ids + exclude_ids + profile + model_config_id);
  * PlaybookCreateResponse — what the backend returns after creating a version;
  * GlobalCheckInfo — short description of a single global check for the UI;
  * BundleInfo — description of a preconfigured set of checks;
  * PlaybookVersionShort — simplified representation of PlaybookVersion for lists;
  * PlaybookLineShort — logical playbook (template) for the selection page.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field


class GlobalCheckInfo(BaseModel):
    """Short information about a global check for UI lists."""

    id: str
    name: str
    description: str | None = None
    category: str | None = None
    group: str | None = None
    severity: str
    doc_types: list[str] = Field(default_factory=list)


class BundleInfo(BaseModel):
    """Bundle (preset) information for the UI."""

    id: str
    name: str
    description: str | None = None
    check_ids: list[str]


class PlaybookCreateRequest(BaseModel):
    """
    Request to create a new playbook version.

    Options:
    - User selects one or more bundles;
    - Adds/removes individual check_ids;
    - Sets depth profile (profile);
    - Specifies model_config_id with which the playbook will run;
    - Optionally links the version to a logical playbook (playbook_id).
    """

    name: str | None = Field(
        default=None,
        description="Playbook name. If not specified, it can be auto-generated on the backend.",
    )
    bundles: list[str] = Field(
        default_factory=list,
        description="List of bundle IDs to be included (mna_core, full, ...).",
    )
    include_ids: list[str] = Field(
        default_factory=list,
        description="Check IDs to be added on top of bundles.",
    )
    exclude_ids: list[str] = Field(
        default_factory=list,
        description="Check IDs to be excluded from bundles.",
    )
    profile: str | None = Field(
        default=None,
        description="Validation depth profile: core/full/quick, etc.",
    )

    model_config_id: UUID = Field(
        description=(
            "ID of the ModelConfig to be used by the runner. "
            "Required field: playbook version must always be linked "
            "to a specific model configuration."
        ),
    )

    semver: str | None = Field(
        default=None,
        description="Explicit semver value (if specified from the frontend).",
    )

    status: Literal["draft", "published", "archived"] | None = Field(
        default=None,
        description="Playbook version status: draft/published/archived. Default is draft.",
    )

    playbook_id: UUID | None = Field(
        default=None,
        description=(
            "ID of the logical Playbook (template) associated with this version. "
            "If not specified, the version will have no associated line."
        ),
    )

    from_line_id: UUID | None = Field(
        default=None,
        description=(
            "If specified, the version will be compiled based on the PlaybookLine template "
            "with this ID: its items will be transformed into a list of global checks."
        ),
    )


class PlaybookDraftUpdateRequest(BaseModel):
    """
    Partial update of a draft playbook version.

    Allowed only for status=draft.
    Published/archived versions cannot be modified.
    """

    name: str | None = None
    bundles: list[str] | None = None
    include_ids: list[str] | None = None
    exclude_ids: list[str] | None = None
    profile: str | None = None


class PlaybookCreateResponse(BaseModel):
    """Response containing the ID of the created playbook version."""

    id: UUID
    name: str
    semver: str
    status: str
    playbook_id: UUID | None = Field(
        default=None,
        description="ID of the logical Playbook to which the version is linked (if any).",
    )


class PlaybookVersionShort(BaseModel):
    """Simplified representation of PlaybookVersion (for lists/selectors)."""

    id: UUID
    name: str
    semver: str
    status: str
    playbook_id: UUID | None = Field(
        default=None,
        description="ID of the logical Playbook (for version grouping in the UI).",
    )


class PlaybookVersionDetail(BaseModel):
    """
    Detailed representation of a playbook version.

    Used to inspect the playbook composition:
    - compiled_checks;
    - triggers, DD request templates, section_markers, classification_config.
    """

    id: UUID
    name: str
    semver: str
    status: str
    playbook_id: UUID | None = None
    model_config_id: UUID | None = None

    compiled_checks: dict[str, Any] | None = None
    trigger_definitions: dict[str, Any] | None = None
    dd_request_templates: dict[str, Any] | None = None
    section_markers: dict[str, Any] | None = None
    classification_config: dict[str, Any] | None = None
    source_payload: dict[str, Any] | None = None
    source_payload_sha256: str | None = None


class PlaybookLineShort(BaseModel):
    """
    Logical playbook (Playbook) for the template selection page.

    Used by the frontend to:
    - Show the list of products/templates (Real estate RU core, M&A RU full, etc.);
    - Filter by deal type, jurisdiction, language, risk_profile.
    """

    id: UUID
    code: str
    title: str
    description: str | None = None
    deal_type: str | None = Field(
        default=None,
        description="Deal type: real_estate, mna, nda, corporate, etc.",
    )
    jurisdiction: str | None = Field(
        default=None,
        description="Primary jurisdiction, e.g., RU, EN, DE.",
    )
    language: str | None = Field(
        default=None,
        description="Primary document language: 'ru', 'en', etc.",
    )
    risk_profile: str | None = Field(
        default=None,
        description="Additional profile/role: standard, high, vendor, buyer, etc.",
    )


class PlaybookCheckInfo(BaseModel):
    code: str
    title: str
    description: str | None = None
    topic_code: str
    file_path: str


class PlaybookTopicInfo(BaseModel):
    topic_code: str
    topic_name: str
    checks: list[PlaybookCheckInfo]


class PlaybookLineItemPayload(BaseModel):
    kind: Literal["check"]
    instruction_code: str
    order_index: int


class PlaybookLineCreate(BaseModel):
    title: str
    description: str | None = None
    deal_type: str | None = None
    jurisdiction: str | None = None
    language: str | None = None
    items: list[PlaybookLineItemPayload]


class PlaybookLineDetail(PlaybookLineShort):
    items: list[PlaybookLineItemPayload]


class ModelConfigResponse(BaseModel):
    """
    Model configuration (ModelConfig) for the UI.

    Used by the frontend when selecting the model under which the playbook will run:
    - id — configuration identifier (UUID);
    - name — human-readable name for dropdown lists;
    - description — short explanation (optional);
    - embeddings_primary / embeddings_fallback etc. can be exposed for reference.
    """

    id: UUID
    name: str
    description: str | None = None

    embeddings_primary: str | None = None
    embeddings_fallback: str | None = None


class ModelConfigCreateRequest(BaseModel):
    """
    Input data for creating a new model profile (ModelConfig).
    """

    name: str
    embeddings_primary: str = "intfloat/multilingual-e5-large"
    embeddings_fallback: str | None = "cointegrated/LaBSE"

    # Simple form fields. The backend will package them into JSON.
    candidate_n: int = 50
    llm_context_k: int = 5

    dense_weight: float = 0.6
    sparse_weight: float = 0.3
    metadata_boost: float = 0.1


class ModelConfigUpdateRequest(BaseModel):
    """
    Partial update of a model profile.
    All fields are optional, only modified values should be sent.
    """

    name: str | None = None
    embeddings_primary: str | None = None
    embeddings_fallback: str | None = None

    candidate_n: int | None = None
    llm_context_k: int | None = None

    dense_weight: float | None = None
    sparse_weight: float | None = None
    metadata_boost: float | None = None


class PlaybookVersionDiffField(BaseModel):
    field: str
    old: Any | None = None
    new: Any | None = None


class PlaybookVersionDiffResponse(BaseModel):
    """
    Difference between two playbook versions based on source_payload.

    diff — list of changes across source_payload fields.
    """

    base_version_id: UUID
    compare_version_id: UUID
    has_changes: bool
    diff: list[PlaybookVersionDiffField]
