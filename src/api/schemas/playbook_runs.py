# src/api/schemas/playbook_runs.py

"""
Schemas for operations:
- Recompilation of deal playbook and recomputation of results (rebuild-and-rerun);
- Playbook change history per deal.

Important note:

We currently have two playbook configuration layers:

1) The "Recipe" (config) used by the compiler:
   - bundles: base presets (playbooks/bundles/*.yaml),
   - include_ids: check IDs to add,
   - exclude_ids: check IDs to remove,
   - profile: check depth profile (core/full/max).

2) The actual composition (enabled_check_ids/disabled_check_ids)
   which the frontend retrieves and modifies via the UI cards tree.

To preserve compatibility and avoid breaking existing code, we:

- Keep bundles/include_ids/exclude_ids/profile parameters for the legacy logic
  (recompilation from past configs and partial overrides),
- Add optional fields enabled_check_ids/disabled_check_ids
  to allow the frontend to supply a finalized check list after UI modifications.

If enabled_check_ids/disabled_check_ids are omitted or empty,
the backend will fall back to using bundles/include_ids/exclude_ids as before.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DealPlaybookRebuildRequest(BaseModel):
    """
    Request to compile a new playbook configuration for a deal and trigger a new analysis run.

    Use cases:

    1) Legacy / "Recipe-based" mode (backward-compatible):
       - Supply bundles/include_ids/exclude_ids/profile parameters,
       - Leave enabled_check_ids/disabled_check_ids empty,
       - The playbook configuration is assembled from:
         * The current PlaybookConfig of the compiled playbook,
         * Overrides provided in the bundles/include/exclude/profile parameters.

    2) New "UI-checked list" mode:
       - The frontend displays the tree of all available checks to the user,
         originating from a template or the current active playbook;
       - The user checks/unchecks individual checkboxes;
       - The frontend dispatches:
           enabled_check_ids  — the finalized list of enabled check IDs,
           disabled_check_ids — explicitly disabled check IDs (optional),
         while leaving bundles/include_ids/exclude_ids omitted or empty.
       - The backend maps enabled_check_ids as include_ids
         and disabled_check_ids as exclude_ids, or applies more advanced composition logic.

    This facilitates an evolutionary transition from compiler recipe inputs
    to explicitly configured check sets without breaking existing APIs.
    """

    # --- Compiler "Recipe" (backward-compatible parameters) ---

    bundles: list[str] = Field(
        default_factory=list,
        description="List of bundle IDs for the new playbook configuration. "
        "If empty and enabled_check_ids is not supplied, falls back to active config bundles.",
    )
    include_ids: list[str] = Field(
        default_factory=list,
        description="Check IDs explicitly added on top of bundles "
        "(evaluated if enabled_check_ids is omitted or empty).",
    )
    exclude_ids: list[str] = Field(
        default_factory=list,
        description="Check IDs explicitly excluded (evaluated if enabled_check_ids is omitted or empty).",
    )
    profile: str | None = Field(
        default=None,
        description="Validation depth profile (e.g., core/full/quick/max). "
        "If omitted and enabled_check_ids is empty, falls back to current config profile.",
    )

    # --- Explicit Final Composition Layer (UI selection output) ---

    enabled_check_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Finalized list of check IDs that must be enabled in the playbook "
            "following explicit user changes in the UI. "
            "If populated, acts as the primary check set source."
        ),
    )
    disabled_check_ids: list[str] = Field(
        default_factory=list,
        description=(
            "List of check IDs explicitly disabled by the user relative to the base configuration. "
            "Can be evaluated in tandem with enabled_check_ids for precise composition mapping."
        ),
    )


class DealPlaybookRebuildResponse(BaseModel):
    """
    Response payload returning details of the recompiled playbook and the triggered analysis run.

    Used by the frontend to:
    - Update the project's current active playbook ID (Deal.playbook_version_id);
    - Map the new run as the active dataset;
    - Optionally redirect to the newly created run status workspace.
    """

    deal_id: UUID
    new_playbook_version_id: UUID
    new_run_id: UUID


class DealPlaybookHistoryItem(BaseModel):
    """
    Single history log record of deal playbook configuration changes.

    Corresponds to a unique Run and PlaybookVersion relationship:
    - Playbook profile properties (name/semver) applied;
    - Executed run identifier;
    - Run status and completion timestamps;
    - Configured depth profile.
    """

    run_id: UUID
    playbook_version_id: UUID
    playbook_name: str
    playbook_semver: str
    run_status: str
    created_at: datetime
    completed_at: datetime | None = None
    profile: str


class DealPlaybookHistoryResponse(BaseModel):
    """
    Historical log of playbook configurations applied to a deal.

    Returns the collection of all executions with their respective playbooks (newest first)
    to facilitate rendering:

    - Playbook configuration progression (versions/semver evolution);
    - Analysis executions triggered for each unique version;
    - The active current run reference.
    """

    deal_id: UUID
    items: list[DealPlaybookHistoryItem]
