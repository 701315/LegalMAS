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
      text: "Please provide information regarding «{check_name}» in {doc_names}."
      addressee: "Legal Counsel"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.i18n.export_translator import normalize_export_locale
from core.logging import get_logger

logger = get_logger(__name__)

# Built-in fallback templates per locale (canonical default: "en")
_BUILTIN_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "coc": {
            "text": (
                "Please provide information regarding change of control conditions "
                "provided in {doc_names}. Please clarify: "
                "(a) whether counterparty consent is required; "
                "(b) whether the transaction triggers termination rights."
            ),
            "addressee": "Seller / Seller's Legal Counsel",
        },
        "consent": {
            "text": (
                "Please confirm receipt of all necessary third-party consents "
                "for the transaction in respect of {doc_names}."
            ),
            "addressee": "Corporate Secretary",
        },
        "termination": {
            "text": (
                "Please provide a list of termination grounds "
                "provided in {doc_names}, specifying the notice procedure."
            ),
            "addressee": "Legal Counsel",
        },
        "non_compete": {
            "text": (
                "Please clarify the terms and conditions of non-compete restrictions "
                "contained in {doc_names}."
            ),
            "addressee": "Legal Counsel",
        },
        "indemnity": {
            "text": (
                "Please provide information on indemnity caps in {doc_names}."
            ),
            "addressee": "Seller's Legal Counsel",
        },
        "re_encumbrance": {
            "text": (
                "Please provide extracts from the state register confirming the absence of "
                "encumbrances on the properties specified in {doc_names}."
            ),
            "addressee": "Registration Authority / Cadastral Engineer",
        },
        "emp_key_man": {
            "text": (
                "Please provide information on key employees "
                "specified in {doc_names}, including retention terms."
            ),
            "addressee": "HR Director / Legal Counsel",
        },
        "_default": {
            "text": (
                "Please provide additional information regarding "
                "«{check_name}» in respect of {doc_names}."
            ),
            "addressee": "Legal Counsel",
        },
    },
    "ru": {
        "coc": {
            "text": (
                "Просим предоставить информацию об условиях смены контроля, "
                "предусмотренных в {doc_names}. Необходимо уточнить: "
                "(а) требуется ли согласие контрагента; "
                "(б) порождает ли сделка право на расторжение."
            ),
            "addressee": "Продавец / Юридический советник продавца",
        },
        "consent": {
            "text": (
                "Просим подтвердить получение всех необходимых согласий "
                "третьих лиц для совершения сделки в отношении {doc_names}."
            ),
            "addressee": "Корпоративный секретарь",
        },
        "termination": {
            "text": (
                "Просим предоставить перечень оснований для расторжения, "
                "предусмотренных в {doc_names}, с указанием процедуры уведомления."
            ),
            "addressee": "Юридический советник",
        },
        "non_compete": {
            "text": (
                "Просим уточнить условия и сроки ограничений на конкуренцию, "
                "содержащихся в {doc_names}."
            ),
            "addressee": "Юридический советник",
        },
        "indemnity": {
            "text": (
                "Просим предоставить информацию о предельных суммах возмещения "
                "убытков (indemnity cap) в {doc_names}."
            ),
            "addressee": "Юридический советник продавца",
        },
        "re_encumbrance": {
            "text": (
                "Просим предоставить выписки из ЕГРН, подтверждающие отсутствие "
                "обременений на объекты, указанные в {doc_names}."
            ),
            "addressee": "Регистрационный орган / Кадастровый инженер",
        },
        "emp_key_man": {
            "text": (
                "Просим предоставить информацию о ключевых сотрудниках, "
                "указанных в {doc_names}, включая условия их удержания."
            ),
            "addressee": "HR-директор / Юридический советник",
        },
        "_default": {
            "text": (
                "Просим предоставить дополнительную информацию по вопросу "
                "«{check_name}» в отношении {doc_names}."
            ),
            "addressee": "Юридический советник",
        },
    },
}


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

        merged: dict[str, dict] = dict(_BUILTIN_TEMPLATES["en"])

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
            from_yaml=len(merged) - len(_BUILTIN_TEMPLATES["en"]),
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
        builtins = _BUILTIN_TEMPLATES.get(target_locale) or _BUILTIN_TEMPLATES["en"]

        doc_names_str = ", ".join(f"«{n}»" for n in doc_names[:5])
        if len(doc_names) > 5:
            more_count = len(doc_names) - 5
            if target_locale == "ru":
                doc_names_str += f" и ещё {more_count} документ(ов)"
            else:
                doc_names_str += f", and {more_count} more document(s)"

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
                or builtins.get("_default", _BUILTIN_TEMPLATES["en"]["_default"])
            )

        default_addressee = builtins["_default"].get("addressee", "Legal Counsel")

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


    