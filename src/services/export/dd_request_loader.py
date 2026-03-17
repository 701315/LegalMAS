# src/services/export/dd_request_loader.py

"""
DD Request Template Loader.

Loads request text templates from YAML document_type instruction files.
Falls back to built-in templates if the YAML section is missing.

YAML structure expected (in playbooks/document_types/*.yaml):
  dd_request_templates:
    coc_001:
      text: "Просим предоставить информацию о смене контроля в {doc_names}."
      addressee: "Продавец / Юридический советник продавца"
    consent_001:
      text: "Просим подтвердить получение согласий по {doc_names}."
      addressee: "Корпоративный секретарь"
    _default:
      text: "Просим предоставить информацию по «{check_name}» в {doc_names}."
      addressee: "Юридический советник"
"""

from pathlib import Path

import yaml

from core.logging import get_logger

logger = get_logger(__name__)

# Built-in fallback templates (used when YAML section is absent)
_BUILTIN_TEMPLATES: dict[str, dict] = {
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

        merged: dict[str, dict] = dict(_BUILTIN_TEMPLATES)

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
            from_yaml=len(merged) - len(_BUILTIN_TEMPLATES),
        )
        self._cache = merged
        return merged

    def render(
        self,
        check_id: str,
        check_name: str,
        doc_names: list[str],
    ) -> tuple[str, str]:
        """
        Render request text and addressee for a check.

        Lookup order:
          1. Exact check_id match (e.g. "coc_001")
          2. check_id prefix match (e.g. "coc")
          3. _default template

        Returns:
            (rendered_text, addressee)
        """
        templates = self.get_all_templates()

        doc_names_str = ", ".join(f"«{n}»" for n in doc_names[:5])
        if len(doc_names) > 5:
            doc_names_str += f" и ещё {len(doc_names) - 5} документ(ов)"

        # Try exact match first
        tmpl = templates.get(check_id)

        # Try prefix match (check_id prefix before first underscore)
        if tmpl is None:
            prefix = check_id.split("_")[0] if "_" in check_id else check_id
            tmpl = templates.get(prefix)

        # Fallback to _default
        if tmpl is None:
            tmpl = templates.get("_default", _BUILTIN_TEMPLATES["_default"])

        text = tmpl["text"].format(
            doc_names=doc_names_str,
            check_name=check_name,
        )
        addressee = tmpl.get("addressee", "Юридический советник")

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
