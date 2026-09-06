# src/core/playbooks/compiler.py

"""
Playbook compiler.

This module is responsible for:

1) Loading definitions of global checks from YAML files
   (playbooks/global_checks directory, recursively across subfolders).

2) Loading bundle configurations (UI presets) from YAML files
   (playbooks/bundles directory).

3) Building a "compiled playbook" (compiled_checks) for saving
   in PlaybookVersion.compiled_checks.

Compiled playbook is a simple JSON-compatible dict with the structure:

    {
      "checks": [ GlobalCheckConfig, ... ],
      "meta": {
        "config": { ... PlaybookConfig ... },
        "bundle_id": "...",
        "check_ids": ["CHK_001", "CHK_002", ...],
        "version_schema": 1,
        "source_type": "global_checks_v1"
      }
    }

Where:

- GlobalCheckConfig describes a single check available to the validation engine.
- The 'source' field in GlobalCheckConfig identifies the origin of the check and
  is used, among other things, for filtering in the DD Grid:

    - GLOBAL_PLAYBOOK  – check came from a global playbook
                         (universal risks "for any contract").
    - DOCUMENT_TYPE    – check came from document-type instructions.
                         For the current global_checks_v1 generator,
                         this might not be used, but the field is reserved.
    - SYSTEM           – system / technical checks created by code.

The current implementation of build_compiled_checks produces only GLOBAL_PLAYBOOK
(global checks assembled by bundles + include/exclude).
However, the data structure is ready to support DOCUMENT_TYPE and SYSTEM in the future
without breaking format compatibility.

Changes (keyword_groups support):
- GlobalCheckConfig received keyword_groups: Dict[str, Any] field.
  This allows storing multi-level keyword groups (high/medium/low)
  separately from the rules block. The loader then combines:
    * rules.keywords (if dict — inline groups),
    * rules.keyword_groups (nested field),
    * keyword_groups (top-level GlobalCheckConfig field).

Changes (severity_if_* support):
- GlobalCheckConfig received severity_if_fail / severity_if_pass /
  severity_if_unclear fields. They allow setting severity dependent on
  the check result (fail/pass/unclear), which is then used by the check runner.

Changes (DD Grid V1 support):
- GlobalCheckConfig received display_order and dd_grid_columns.
  display_order defines the render order of the check in the DD Grid.
  dd_grid_columns — explicit configuration of DD Grid columns (raw dict,
  parsing into DDGridColumnSpec is done by the loader in V1.2).
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# These paths can be made configurable via project settings if needed.
GLOBAL_CHECKS_DIR = Path("playbooks/global_checks")
BUNDLES_DIR = Path("playbooks/bundles")


# ===== Pydantic schemas for compiled_checks =====


class PlaybookConfig(BaseModel):
    """Snapshot of settings used by the user to compile the playbook.

    This is the "recipe" used to generate the final check set.
    It can be shown in the UI and used for recompilation.
    """

    bundles: list[str] = Field(
        default_factory=list,
        description="List of bundle file IDs that were included.",
    )
    include_ids: list[str] = Field(
        default_factory=list,
        description="Check IDs explicitly added by the user on top of bundles.",
    )
    exclude_ids: list[str] = Field(
        default_factory=list,
        description="Check IDs explicitly excluded by the user.",
    )
    profile: str | None = Field(
        default=None,
        description="Depth profile: core/full/quick etc.",
    )


class PlaybookMeta(BaseModel):
    """Metadata describing how the playbook was compiled and is interpreted."""

    config: PlaybookConfig = Field(
        default_factory=PlaybookConfig,
        description="Recipe for compiling the playbook (for UI and recompilation).",
    )
    bundle_id: str | None = Field(
        default=None,
        description="Primary bundle if a single one was selected (for convenience).",
    )
    check_ids: list[str] = Field(
        default_factory=list,
        description="Final list of checks after all include/exclude logic.",
    )
    global_instruction_refs: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "References to published global instruction versions used "
            "during playbook compilation: {instruction_code: version_id}"
        ),
    )
    version_schema: int = Field(
        default=1,
        description="Compiled_checks/meta schema version.",
    )
    source_type: str = Field(
        default="global_checks_v1",
        description="Origin of the check definitions (for traceability).",
    )


class CheckSource(str, Enum):
    """Origin of a check definition (used by both backend and UI).

    Values:

    - GLOBAL_PLAYBOOK  – check originated from the global playbook
                         (universal topics for any contract).
    - DOCUMENT_TYPE    – check is defined in instructions for a specific document type.
    - SYSTEM           – check was generated by the system (technical/diagnostic check).
    """

    GLOBAL_PLAYBOOK = "GLOBAL_PLAYBOOK"
    DOCUMENT_TYPE = "DOCUMENT_TYPE"
    SYSTEM = "SYSTEM"


class GlobalCheckConfig(BaseModel):
    """Description of a single global check (as stored in compiled_checks).

    This is a flattened structure ready for the validation engine
    and for display in the UI (via PlaybookDefinition / CheckDefinition).
    """

    id: str
    name: str
    description: str | None = None
    category: str | None = None
    group: str | None = Field(
        default=None,
        description="Large UX section/block (e.g., 'liability').",
    )
    display_order: int = Field(
        default=0,
        description=(
            "Display order of the check within its group/list in DD Grid. "
            "Lower = earlier. Checks with the same display_order "
            "are sorted alphabetically by name."
        ),
    )
    severity: str = Field(
        default="medium",
        description="low | medium | high | critical",
    )
    # Outcome-dependent severities (optional, override base severity)
    severity_if_fail: str | None = Field(
        default=None,
        description="Severity to apply if the check result is fail (optional).",
    )
    severity_if_pass: str | None = Field(
        default=None,
        description="Severity to apply if the check result is pass (optional).",
    )
    severity_if_unclear: str | None = Field(
        default=None,
        description="Severity to apply if the check result is unclear (optional).",
    )

    ui_mode: str | None = Field(
        default=None,
        description=(
            "Semantic type of check for business-result mapping and UI display. "
            "Supported values: 'clause_presence', 'risk_detection', 'field_extraction'. "
            "None = legacy fallback behavior."
        ),
    )

    doc_types: list[str] = Field(
        default_factory=list,
        description="Document types to which this check is applicable.",
    )

    # IMPORTANT: this field will be mapped to the origin level of CheckDefinition.
    # For global playbook checks, we set this to GLOBAL_PLAYBOOK, for future document-specific
    # instructions, we can set it to DOCUMENT_TYPE, and for system checks, to SYSTEM.
    source: CheckSource = Field(
        default=CheckSource.GLOBAL_PLAYBOOK,
        description="Origin: GLOBAL_PLAYBOOK / DOCUMENT_TYPE / SYSTEM.",
    )

    detector_type: str = Field(
        ...,
        description="'rules' | 'llm' | 'hybrid'",
    )

    # Configuration for rule-based detector (keywords, regex, etc.).
    # Stored as a raw dict, loader parses this into RulesConfig.
    rules: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration for rule-based detector (keywords, regex, etc.).",
    )

    # Level-based keyword groups (high/medium/low).
    # Stored separately from rules to pass directly to RulesConfig.keyword_groups.
    # If provided, it is used by the loader as an additional source:
    #   1) rules.keywords (if dict — inline groups),
    #   2) rules.keyword_groups,
    #   3) keyword_groups (this field).
    keyword_groups: dict[str, Any] = Field(
        default_factory=dict,
        description="Level-based keyword groups: {'high': [...], 'medium': [...], 'low': [...]}",
    )

    llm: dict[str, Any] = Field(
        default_factory=dict,
        description="LLM detector configuration (prompt, model, parameters).",
    )
    retrieval: dict[str, Any] = Field(
        default_factory=dict,
        description="Context retrieval configuration (scope, k, etc.).",
    )
    extraction: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured extraction configuration.",
    )
    dd_grid_columns: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Explicit DD Grid column configuration for field_extraction checks. "
            "Raw list[dict] — parsed into DDGridColumnSpec by the loader."
        ),
    )
    red_flags: dict[str, Any] = Field(
        default_factory=dict,
        description="Red flags search configuration.",
    )

    profiles_enabled: list[str] = Field(
        default_factory=list,
        description="Depth profiles that enable this check: ['core', 'full'], etc.",
    )
    deal_profiles: list[str] = Field(
        default_factory=list,
        description="Deal profiles for which this check is highly relevant.",
    )
    industries: list[str] = Field(
        default_factory=list,
        description="Industries for which this check is highly relevant.",
    )
    jurisdictions: list[str] = Field(
        default_factory=list,
        description="Jurisdictions for which this check is highly relevant.",
    )


class BundleConfig(BaseModel):
    """UI preset (bundle) description from YAML.

    A bundle is simply a named set of check IDs that can be chosen
    in the interface for a quick start (e.g., "Core SPA checks").
    """

    id: str
    name: str
    description: str | None = None
    check_ids: list[str]


class CompiledPlaybook(BaseModel):
    """JSON schema stored in PlaybookVersion.compiled_checks.

    - checks: final list of checks (GlobalCheckConfig) after applying all filters.
    - meta: metadata describing how this list was generated.
    """

    checks: list[GlobalCheckConfig]
    meta: PlaybookMeta


# ===== Loading global_checks and bundles =====


def load_global_checks() -> dict[str, GlobalCheckConfig]:
    """Load all global check definitions from GLOBAL_CHECKS_DIR.

    Each YAML file is expected to describe one check in a format
    compatible with GlobalCheckConfig (id, name, severity, detector_type, etc.).

    Searches recursively across subdirectories (rglob("*.yaml")).

    Returns:
        dict: {check_id: GlobalCheckConfig}.

    Raises:
        RuntimeError – on file reading error or invalid schema.
    """
    import yaml

    if not GLOBAL_CHECKS_DIR.exists():
        logger.warning("GLOBAL_CHECKS_DIR does not exist: %s", GLOBAL_CHECKS_DIR)
        return {}

    checks: dict[str, GlobalCheckConfig] = {}

    # Recursively find YAML files: playbooks/global_checks/**.yaml
    for path in sorted(GLOBAL_CHECKS_DIR.rglob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to read global check YAML %s: %s", path, e)
            raise RuntimeError(f"Cannot read global check file: {path}") from e

        # NORMALIZATION of source before validation:
        source_raw = raw.get("source")
        if isinstance(source_raw, str):
            normalized = source_raw.strip().upper()
            if normalized == "GLOBAL_PLAYBOOK":
                raw["source"] = CheckSource.GLOBAL_PLAYBOOK
            elif normalized == "DOCUMENT_TYPE":
                raw["source"] = CheckSource.DOCUMENT_TYPE
            elif normalized == "SYSTEM":
                raw["source"] = CheckSource.SYSTEM
            else:
                logger.error(
                    "Unknown check source '%s' in %s. "
                    "Expected one of: GLOBAL_PLAYBOOK, DOCUMENT_TYPE, SYSTEM",
                    source_raw,
                    path,
                )
                raise RuntimeError(
                    f"Invalid 'source' value '{source_raw}' in {path}. "
                    "Use GLOBAL_PLAYBOOK / DOCUMENT_TYPE / SYSTEM."
                )

        try:
            cfg = GlobalCheckConfig(**raw)
        except ValidationError as e:
            logger.error("Invalid global check config in %s: %s", path, e)
            raise RuntimeError(f"Invalid global check config in {path}: {e}") from e

        if cfg.id in checks:
            logger.error("Duplicate global check id=%s in %s", cfg.id, path)
            raise RuntimeError(f"Duplicate global check id={cfg.id} in {path}")

        checks[cfg.id] = cfg

    return checks


def load_bundle(bundle_id: str) -> BundleConfig:
    """Load YAML bundle by its ID from the playbooks/bundles directory.

    bundle_id maps to a file named <bundle_id>.yaml.

    Returns:
        BundleConfig.

    Raises:
        FileNotFoundError – if file is not found.
        RuntimeError      – if file is unreadable or schema is invalid.
    """
    import yaml

    path = BUNDLES_DIR / f"{bundle_id}.yaml"
    if not path.exists():
        logger.warning("Bundle %s not found at %s", bundle_id, path)
        raise FileNotFoundError(f"Bundle {bundle_id} not found")

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to read bundle YAML %s: %s", path, e)
        raise RuntimeError(f"Cannot read bundle file: {path}") from e

    try:
        cfg = BundleConfig(**raw)
    except ValidationError as e:
        logger.error("Invalid bundle config in %s: %s", path, e)
        raise RuntimeError(f"Invalid bundle config in {path}: {e}") from e

    if cfg.id != bundle_id:
        logger.error(
            "Bundle id mismatch for %s: file name id=%s, YAML id=%s",
            path,
            bundle_id,
            cfg.id,
        )
        raise RuntimeError(f"Bundle id mismatch: file={bundle_id}, yaml={cfg.id}")

    if not cfg.check_ids:
        logger.error("Bundle %s has empty check_ids list", bundle_id)
        raise RuntimeError(f"Bundle {bundle_id} has empty check_ids list")

    return cfg


# ===== Building compiled_checks =====


def build_compiled_checks(
    all_checks: dict[str, GlobalCheckConfig],
    *,
    bundles: list[str] | None = None,
    include_ids: list[str] | None = None,
    exclude_ids: list[str] | None = None,
    profile: str | None = None,
    primary_bundle_id: str | None = None,
    global_instruction_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the structure for PlaybookVersion.compiled_checks.

    Input:
        all_checks:
            All available global checks (result of load_global_checks()).
        bundles:
            List of bundle_ids selected by the user.
        include_ids:
            Check IDs explicitly added by the user on top of bundles.
        exclude_ids:
            Check IDs explicitly excluded by the user.
        profile:
            Depth profile (e.g., 'core' / 'full' / 'quick').
        primary_bundle_id:
            Primary bundle ID for traceability (can be None).

    Algorithm:

        1) Collect the base set of check IDs from the selected bundles.
        2) Add include_ids.
        3) Deduplicate while preserving order.
        4) Apply exclude_ids.
        5) Validate that all IDs exist in all_checks.
        6) Filter by profile if necessary.
        7) Generate CompiledPlaybook (checks + meta) and return as a dict.

    Important:

    - The GlobalCheckConfig.source field is already populated during YAML parsing.
      For the current global_checks_v1 generator, this is typically
      CheckSource.GLOBAL_PLAYBOOK.
    - This field is subsequently mapped to the origin field at the CheckDefinition
      level (see engine/playbook/loader.py) and is used by DD Grid for
      "Global playbook" and "By document type" filters.
    """
    bundles = bundles or []
    include_ids = include_ids or []
    exclude_ids = exclude_ids or []
    global_instruction_refs = global_instruction_refs or {}

    # 1. Base set of IDs: all check IDs from selected bundles
    base_ids: list[str] = []

    for bundle_id in bundles:
        bundle_cfg = load_bundle(bundle_id)
        base_ids.extend(bundle_cfg.check_ids)

    # 2. Add explicit include_ids
    base_ids.extend(include_ids)

    if not base_ids:
        raise ValueError("No checks selected: bundles and include_ids are both empty")

    # 3. Deduplicate preserving order
    seen: set[str] = set()
    unique_ids: list[str] = []
    for cid in base_ids:
        if cid in seen:
            continue
        seen.add(cid)
        unique_ids.append(cid)

    # 4. Apply exclude_ids
    excluded_set = set(exclude_ids)
    final_ids: list[str] = [cid for cid in unique_ids if cid not in excluded_set]

    if not final_ids:
        raise ValueError("All checks were excluded; resulting list is empty")

    # 5. Validate that all exist in all_checks
    missing: list[str] = [cid for cid in final_ids if cid not in all_checks]
    if missing:
        raise KeyError(f"Unknown check_id(s): {', '.join(missing)}")

    # 6. Filter by profile (if requested)
    if profile:
        filtered_ids: list[str] = []
        for cid in final_ids:
            cfg = all_checks[cid]
            if not cfg.profiles_enabled or profile in cfg.profiles_enabled:
                filtered_ids.append(cid)
        if not filtered_ids:
            raise ValueError(f"No checks left after applying profile='{profile}'")
        final_ids = filtered_ids

    # 7. Construct CompiledPlaybook
    compiled = CompiledPlaybook(
        checks=[all_checks[cid] for cid in final_ids],
        meta=PlaybookMeta(
            config=PlaybookConfig(
                bundles=bundles,
                include_ids=include_ids,
                exclude_ids=exclude_ids,
                profile=profile,
            ),
            bundle_id=primary_bundle_id,
            check_ids=final_ids,
            global_instruction_refs={
                cid: global_instruction_refs[cid]
                for cid in final_ids
                if cid in global_instruction_refs
            },
            version_schema=1,
            source_type="global_checks_v1",
        ),
    )

    # Return a plain dict to store easily in JSONB via ORM.
    return compiled.model_dump()
