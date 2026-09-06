# src/services/export/dd_request_loader.py

"""
DD Request Template Loader.

Loads request text templates from YAML document_type instruction files.
Falls back to built-in templates if the YAML section is missing.

YAML structure expected (in playbooks/document_types/*.yaml):
  dd_request_templates:
    coc_001:
      text: "Please provide information regarding change of control in {doc_names}."
      addressee: "Seller / Seller's Legal Counsel"
    consent_001:
      text: "Please confirm receipt of consents for {doc_names}."
      addressee: "Corporate Secretary"
    _default:
      text: "Please provide information regarding \"{check_name}\" in {doc_names}."
      addressee: "Legal Counsel"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from core.i18n.export_translator import normalize_export_locale
from core.logging import get_logger

logger = get_logger(__name__)

# Built-in fallback templates per locale (loaded from JSON, default fallback: "en")
GLOBAL_CHECKS_DIR = Path("playbooks/global_checks")
TEMPLATES_JSON_PATH = Path(__file__).parent / "builtin_templates.json"


def _load_builtin_templates() -> dict[str, dict[str, Any]]:
    """
    Safely load builtin templates from local JSON configuration.
    Falls back to a minimal English hardcoded schema if the file is unreadable.
    """
    if not TEMPLATES_JSON_PATH.exists():
        logger.error("Builtin templates JSON not found at %s", TEMPLATES_JSON_PATH)
        return {
            "en": {
                "more_documents": ", and {count} more document(s)",
                "_default": {
                    "text": "Please provide additional information regarding \"{check_name}\" in respect of {doc_names}.",
                    "addressee": "Legal Counsel",
                },
            }
        }

    try:
        with TEMPLATES_JSON_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.exception("Failed to parse builtin templates JSON from %s", TEMPLATES_JSON_PATH)
        return {
            "en": {
                "more_documents": ", and {count} more document(s)",
                "_default": {
                    "text": "Please provide additional information regarding \"{check_name}\" in respect of {doc_names}.",
                    "addressee": "Legal Counsel",
                },
            }
        }


_BUILTIN_TEMPLATES = _load_builtin_templates()


class DDRequestTemplateLoader:
    """
    Loads DD request templates from YAML document_type files.

    Merges templates from all applicable document_type YAML files,
    with per-file templates taking priority over built-in fallbacks.
    """

    def __init__(self, doc_types_dir: str | None = None):
        self._dir = Path(doc_types_dir or "playbooks/document_types")
        self._cache: dict[str, dict] | None = None

    def get_all_templates(self) -> dict[str, dict]:
        """Load and merge all templates from YAML files."""
        if self._cache is not None:
            return self._cache

        merged: dict[str, dict] = dict(_BUILTIN_TEMPLATES.get("en", {}))

        if not self._dir.exists():
            logger.warning(
                "document_types dir not found, using built-in templates",
                path=str(self._dir),
            )
            self._cache = merged
            return merged

        for yaml_file in sorted(self._dir.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                templates = data.get("dd_request_templates", {})
                for check_id, tmpl in templates.items():
                    if isinstance(tmpl, dict) and "text" in tmpl:
                        merged[check_id] = tmpl
                        logger.debug(
                            "Loaded DD template from YAML",
                            check_id=check_id,
                            source=yaml_file.name,
                        )
            except Exception as e:
                logger.warning(
                    "Failed to load DD templates from YAML",
                    file=yaml_file.name,
                    error=str(e),
                )

        logger.info(
            "DD request templates loaded",
            total=len(merged),
            from_yaml=len(merged) - len(_BUILTIN_TEMPLATES.get("en", {})),
        )
        self._cache = merged
        return merged

    def render(
        self,
        check_id: str,
        check_name: str,
        doc_names: list[str],
        locale: str = "en",
    ) -> tuple[str, str]:
        """
        Render request text and addressee for a check.

        Lookup order:
          1. Exact check_id match in YAML templates
          2. check_id prefix match in YAML templates
          3. Built-in locale-specific template (exact/prefix/_default)

        Returns:
            (rendered_text, addressee)
        """
        target_locale = normalize_export_locale(locale)
        builtins = _BUILTIN_TEMPLATES.get(target_locale) or _BUILTIN_TEMPLATES.get("en", {})

        doc_names_str = ", ".join(f'"{n}"' for n in doc_names[:5])
        if len(doc_names) > 5:
            more_count = len(doc_names) - 5
            more_docs_tmpl = builtins.get("more_documents", ", and {count} more document(s)")
            doc_names_str += more_docs_tmpl.format(count=more_count)

        templates = self.get_all_templates()

        # 1. Exact match in YAML
        tmpl = templates.get(check_id)

        # 2. Prefix match in YAML
        prefix = check_id.split("_")[0] if "_" in check_id else check_id
        if tmpl is None:
            tmpl = templates.get(prefix)

        # 3. Fallback to builtins for target locale
        if tmpl is None:
            tmpl = (
                builtins.get(check_id)
                or builtins.get(prefix)
                or builtins.get("_default", _BUILTIN_TEMPLATES.get("en", {}).get("_default"))
            )

        default_addressee = builtins.get("_default", {}).get("addressee", "Legal Counsel")

        text = tmpl["text"].format(
            doc_names=doc_names_str,
            check_name=check_name,
        )
        addressee = tmpl.get("addressee", default_addressee)

        return text, addressee

    def invalidate_cache(self) -> None:
        self._cache = None


# Singleton
_loader: DDRequestTemplateLoader | None = None


def get_dd_request_loader() -> DDRequestTemplateLoader:
    global _loader
    if _loader is None:
        _loader = DDRequestTemplateLoader()
    return _loader


    