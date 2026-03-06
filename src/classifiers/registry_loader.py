"""
Two-level registry loader:
  1. registry.yaml — index of document types (type, name, category, group)
  2. <type>.yaml — detailed instructions per type

Supports two YAML layouts for classification data:
  - Flat: rules/filename_patterns/trigger_definitions at top level
  - Nested: inside classification_runtime_v1 block

The combined result is cached via lru_cache.
All classifiers (L1, L2, L3) and TriggerDetector use this single cache.
"""

import yaml
import os

from functools import lru_cache

from core.logging import get_logger

logger = get_logger(__name__)


def _extract_classification_fields(detail: dict) -> dict:
    """
    Extracts classification-relevant fields from a type instruction file.
    Supports both flat layout and nested classification_runtime_v1 layout.

    Returns dict with normalized top-level keys:
      rules, filename_patterns, folder_patterns, trigger_definitions,
      weights, party_roles, essential_terms, section_markers, aliases.
    """
    runtime = detail.get("classification_runtime_v1", {})

    # --- rules (keywords, phrases, exclusions) ---
    rules = detail.get("rules") or runtime.get("rules", {})

    # --- filename/folder patterns (may be nested in rules or at top) ---
    filename_patterns = (
        detail.get("filename_patterns")
        or runtime.get("filename_patterns")
        or rules.get("filename_patterns", [])
    )
    folder_patterns = (
        detail.get("folder_patterns")
        or runtime.get("folder_patterns")
        or rules.get("folder_patterns", [])
    )

    # Remove filename/folder from rules dict (they are not keywords)
    clean_rules = {
        k: v for k, v in rules.items() if k not in ("filename_patterns", "folder_patterns")
    }

    # --- trigger_definitions ---
    trigger_definitions = detail.get("trigger_definitions") or runtime.get(
        "trigger_definitions", {}
    )

    # --- weights ---
    weights = detail.get("weights") or runtime.get("weights", {})

    # --- validation_engine fields (for L3 prototypes and future) ---
    engine = detail.get("validation_engine_v3_2", {})
    engine_rules = engine.get("rules_enhanced", {})

    party_roles = detail.get("party_roles") or engine_rules.get("party_roles", [])
    essential_terms = detail.get("essential_terms") or engine_rules.get("essential_terms", [])
    section_markers = detail.get("section_markers") or engine_rules.get("section_markers", [])
    aliases = detail.get("aliases") or engine_rules.get("aliases", [])

    # --- phrases: merge from validation_engine if not in runtime ---
    if "phrases" not in clean_rules and "phrases" in engine_rules:
        clean_rules["phrases"] = engine_rules["phrases"]

    return {
        "rules": clean_rules,
        "filename_patterns": filename_patterns,
        "folder_patterns": folder_patterns,
        "trigger_definitions": trigger_definitions,
        "weights": weights,
        "party_roles": party_roles,
        "essential_terms": essential_terms,
        "section_markers": section_markers,
        "aliases": aliases,
    }


@lru_cache(maxsize=1)
def load_registry(registry_path: str) -> dict:
    """
    Loads and caches the full registry:
      1. Reads registry.yaml to get the list of types
      2. For each type, tries to load <type>.yaml with detailed rules
      3. Merges index entry + normalized classification fields

    Returns:
        {"document_types": [merged_config_1, merged_config_2, ...]}

    Call load_registry.cache_clear() in tests to reset.
    """
    if os.path.isdir(registry_path):
        registry_dir = registry_path
        registry_file = os.path.join(registry_path, "registry.yaml")
    else:
        registry_dir = os.path.dirname(registry_path)
        registry_file = registry_path

    if not os.path.exists(registry_file):
        logger.warning("Registry file not found", path=registry_file)
        return {"document_types": []}

    with open(registry_file, encoding="utf-8") as f:
        index = yaml.safe_load(f)

    merged_types = []
    types_list = index.get("document_types", [])

    for entry in types_list:
        doc_type = entry.get("type", "")
        if not doc_type:
            continue

        # Try to load detailed instruction file
        detail_file = os.path.join(registry_dir, f"{doc_type}.yaml")
        detail = {}
        if os.path.exists(detail_file):
            with open(detail_file, encoding="utf-8") as f:
                detail = yaml.safe_load(f) or {}
            logger.debug(
                "Loaded type instructions",
                doc_type=doc_type,
                file=detail_file,
            )

        # Start with index entry
        merged = dict(entry)

        # Preserve raw detail sections for future stages
        for key in (
            "description",
            "metadata",
            "version",
            "engine_expectations",
            "classification_runtime_v1",
            "validation_engine_v3_2",
        ):
            if key in detail:
                merged[key] = detail[key]

        # Extract and normalize classification fields to top level
        if detail:
            classification_fields = _extract_classification_fields(detail)
            merged.update(classification_fields)

        merged["type"] = doc_type
        merged_types.append(merged)

    logger.info(
        "Registry loaded",
        path=registry_file,
        total_types=len(merged_types),
        with_instructions=sum(1 for t in merged_types if t.get("rules")),
    )

    return {"document_types": merged_types}


def get_doc_type_config(registry: dict, doctype: str) -> dict | None:
    """Finds a specific document type config from the merged registry."""
    for cfg in registry.get("document_types", []):
        if cfg.get("type") == doctype:
            return cfg
    return None


def get_all_trigger_names(registry: dict) -> set[str]:
    """
    Collects all unique trigger names across all document types.
    Useful for validation and reporting.
    """
    triggers: set[str] = set()
    for cfg in registry.get("document_types", []):
        trigger_defs = cfg.get("trigger_definitions", {})
        if isinstance(trigger_defs, dict):
            triggers.update(trigger_defs.keys())
    return triggers
