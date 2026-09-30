# src/services/dd_request_composer.py

"""
DD-request text composer.

Single place that turns a triggered check_result into the final
(text, addressee) pair for a DD request.

Priority:
  1. Explicit YAML dd_request_templates[check_id] — manual text wins.
     Written by a legal expert, reviewed, not to be overridden.

  2. Auto-generated text from check_result.review_status:
       - clause_missing           — all signal fields missing
       - clause_partially_defined — some signal fields missing
       - unclear                  — conflict / manual review required
     Texts live in shared/locales/{locale}/export.json under the
     dd_request.* namespace; rendered via t_export() with kwargs
     {check_name} and {doc_names}.

  3. Fallback: loader.render() — file-scoped YAML _default, then
     builtin locale fallback (generic 'please provide...' text).

Composer is a pure function over its arguments + t_export (no DB,
no async). The decision to *generate* a DD-request at all is made
separately by services.dd_request_rules.should_trigger_dd_request.
"""

from __future__ import annotations

from typing import Any, Mapping

from core.i18n.export_translator import t_export
from engine.playbook.models import CheckDefinition
from services.export.dd_request_loader import DDRequestTemplateLoader

__all__ = ["compose_dd_request"]


# review_status values that have an auto-generated dd_request.* template.
# Membership here means: t_export('dd_request.{rs}.text') is a valid key.
_AUTO_STATUSES = frozenset(
    {"clause_missing", "clause_partially_defined", "unclear"}
)


def compose_dd_request(
    *,
    check_result: Mapping[str, Any],
    check_def: CheckDefinition,
    doc_names: list[str],
    loader: DDRequestTemplateLoader,
    locale: str = "ru",
) -> tuple[str, str]:
    """
    Compose (text, addressee) for a DD request.

    Args:
        check_result: row from check_results (must contain check_id;
                      optionally check_name, review_status).
        check_def:    CheckDefinition for the check.
        doc_names:    list of document display names involved.
        loader:       DDRequestTemplateLoader (used for explicit YAML
                      lookup and as final fallback).
        locale:       target locale for auto-generated text.

    Returns:
        (rendered_text, addressee)
    """
    check_id = str(check_result.get("check_id") or check_def.id or "")
    check_name = str(
        check_result.get("check_name")
        or check_def.name
        or check_id
    )

    # ── 1. Explicit YAML template wins ───────────────────────────────────
    explicit = loader.get_explicit_template(check_id)
    if explicit is not None:
        doc_names_str = loader.format_doc_names(doc_names, locale=locale)
        text = explicit["text"].format(
            doc_names=doc_names_str,
            check_name=check_name,
        )
        addressee = explicit.get("addressee") or _default_addressee(locale)
        return text, addressee

    # ── 2. Auto-generate by review_status ────────────────────────────────
    review_status = str(check_result.get("review_status") or "").strip().lower()
    if review_status in _AUTO_STATUSES:
        doc_names_str = loader.format_doc_names(doc_names, locale=locale)
        text_key = f"dd_request.{review_status}.text"
        text = t_export(
            text_key,
            locale,
            check_name=check_name,
            doc_names=doc_names_str,
        )
        # t_export falls back to the raw key when translation is missing.
        # Only accept a translated result that actually differs from the key.
        if text != text_key:
            addressee = t_export(
                f"dd_request.{review_status}.addressee",
                locale,
            )
            return text, addressee

    # ── 3. Fallback: file-scoped YAML _default / builtin ─────────────────
    return loader.render(check_id, check_name, doc_names, locale=locale)


def _default_addressee(locale: str) -> str:
    """Generic addressee when an explicit YAML template has no addressee."""
    fallback_key = "dd_request.clause_missing.addressee"
    resolved = t_export(fallback_key, locale)
    if resolved != fallback_key:
        return resolved
    return "Legal Counsel" if locale.startswith("en") else "Юридический советник"
