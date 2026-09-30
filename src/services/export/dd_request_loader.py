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

    def __init__(self, dirs: list[str | Path] | None = None):
        """
        Args:
            dirs: Список каталогов для поиска YAML-инструкций.
                  По умолчанию: playbooks/document_types + playbooks/global_checks
                  — оба источника содержат dd_request_templates-секции,
                  и оба должны участвовать в lookup по check_id.
                  Передача явного списка используется только в тестах.
        """
        if dirs is None:
            dirs = [
                "playbooks/document_types",
                "playbooks/global_checks",
            ]
        self._dirs = [Path(d) for d in dirs]
        self._cache: dict[str, dict] | None = None

    def _load_cache(self) -> dict[str, dict]:
        """
        Build and cache two maps in a single YAML pass.

        Returns:
            {
              "templates": {check_id: explicit dd_request_templates entry}
                           + builtin fallback (backward-compatible view),
              "defaults":  {check_id: _default of the YAML where check_id
                           is declared in checks_v8}. File-scoped fallback
                           used by render() when a check has no explicit
                           dd_request_templates entry.
            }

        Why two maps: a single flat ``_default`` in ``templates`` would be
        last-wins (whichever YAML sorts last), which is wrong for
        instruction-scoped generic text. A file-scoped ``_default`` gives
        each check_id the generic template from its own instruction.
        """
        if self._cache is not None:
            return self._cache

        templates: dict[str, dict] = dict(_BUILTIN_TEMPLATES.get("en", {}))
        file_defaults: dict[str, dict] = {}

        yaml_files: list[Path] = []
        for d in self._dirs:
            if not d.exists():
                logger.warning(
                    "DD template dir not found, skipping",
                    path=str(d),
                )
                continue
            yaml_files.extend(d.rglob("*.yaml"))

        for yaml_file in sorted(yaml_files):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception as e:
                logger.warning(
                    "Failed to load DD templates from YAML",
                    file=yaml_file.name,
                    error=str(e),
                )
                continue
            if not isinstance(data, dict):
                continue

            dd_tmpl = data.get("dd_request_templates") or {}
            if not isinstance(dd_tmpl, dict):
                continue

            file_default = dd_tmpl.get("_default")

            # (1) explicit per-check templates
            for check_id, tmpl in dd_tmpl.items():
                if check_id == "_default":
                    continue
                if isinstance(tmpl, dict) and "text" in tmpl:
                    templates[check_id] = tmpl
                    logger.debug(
                        "Loaded DD template from YAML",
                        check_id=check_id,
                        source=yaml_file.name,
                    )

            # (2) file-scoped default for checks declared in this file
            if isinstance(file_default, dict) and "text" in file_default:
                checks_list = data.get("checks_v8") or []
                for c in checks_list:
                    if not isinstance(c, dict):
                        continue
                    cid = c.get("id") or c.get("check_id")
                    if not cid:
                        continue
                    # explicit template (if any) always wins over file default
                    if cid in templates:
                        continue
                    file_defaults[cid] = file_default

        logger.info(
            "DD request templates loaded",
            total=len(templates),
            from_yaml=len(templates) - len(_BUILTIN_TEMPLATES.get("en", {})),
            file_scoped_defaults=len(file_defaults),
        )
        self._cache = {"templates": templates, "defaults": file_defaults}
        return self._cache

    def get_all_templates(self) -> dict[str, dict]:
        """Backward-compatible flat view: explicit YAML templates + builtin."""
        return self._load_cache()["templates"]

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
          3. File-scoped YAML _default (from the instruction that
             declares check_id in checks_v8)
          4. Built-in locale-specific template (exact/prefix/_default)

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

        cache = self._load_cache()
        templates = cache["templates"]
        file_defaults = cache["defaults"]

        # 1. Exact match in YAML
        tmpl = templates.get(check_id)
        prefix = check_id.split("_")[0] if "_" in check_id else check_id

        # 2. Prefix match in YAML
        if tmpl is None:
            tmpl = templates.get(prefix)

        # 3. File-scoped _default from the YAML that declared this check
        #    (via checks_v8). Ensures doc-type checks without an explicit
        #    dd_request_templates entry get the correct instruction-scoped
        #    generic text instead of an unrelated file's last-wins _default.
        if tmpl is None:
            tmpl = file_defaults.get(check_id)

        # 4. Builtin locale-specific fallback (checks not in any instruction)
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


    