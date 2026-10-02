"""
llm_narratives.py — нарративы для DD Report v2.

Разделение ответственности (production-подход):

- purpose_of_report — LLM (Qwen 2.5 14B) + строгий промт + валидация.
  Здесь LLM оправдана: нужен связный текст на основе метаданных и totals.

- overall_summary, global_summary, doc_type_summary — deterministic renderer.
  Здесь LLM не нужна: все числа, счётчики, severity и связи между чеками
  и документами уже вычислены в FactBundle. LLM на этом уровне только
  добавляет риск галлюцинаций (например, номеров статей).

Принципы:
- Для фактических summary: никаких вызовов LLM, только код + шаблоны.
- Для purpose: LLM с промтом Big4-уровня, плюс валидация чисел,
  плюс fallback только при недоступности LLM.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from services.export.fact_bundle import FactBundle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_report_narratives(
    fact_bundle: FactBundle,
    locale: str = "en",
) -> dict[str, str]:
    """
    Возвращает dict:
    - "purpose_of_report"   — LLM (или fallback при недоступности)
    - "overall_summary"     — deterministic renderer
    - "global_summary"      — deterministic renderer
    - "doc_type_summary"    — deterministic renderer
    """
    narratives: dict[str, str] = {}

    # ------------------------------------------------------------------
    # 1. Purpose of Report — LLM
    # ------------------------------------------------------------------
    try:
        narratives["purpose_of_report"] = await _generate_purpose(
            fact_bundle, locale
        )
        logger.info(
            "purpose_of_report generated",
            extra={
                "source": "llm"
                if not narratives["purpose_of_report"].startswith(
                    ("This Report presents", "Настоящий Отчёт представляет")
                )
                else "fallback",
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "purpose_of_report generation failed",
            extra={"error": str(exc)},
            exc_info=True,
        )

    # ------------------------------------------------------------------
    # 2. Overall Summary — deterministic renderer
    # ------------------------------------------------------------------
    narratives["overall_summary"] = render_overall_summary(fact_bundle, locale)
    logger.info("overall_summary rendered", extra={"source": "renderer"})

    # ------------------------------------------------------------------
    # 3. Global Checks Summary — deterministic renderer
    # ------------------------------------------------------------------
    narratives["global_summary"] = render_global_summary(fact_bundle, locale)
    logger.info("global_summary rendered", extra={"source": "renderer"})

    # ------------------------------------------------------------------
    # 4. Document-Type Checks Summary — deterministic renderer
    # ------------------------------------------------------------------
    narratives["doc_type_summary"] = render_doc_type_summary(fact_bundle, locale)
    logger.info("doc_type_summary rendered", extra={"source": "renderer"})

    return narratives


# ---------------------------------------------------------------------------
# Helpers: pluralization
# ---------------------------------------------------------------------------


def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    """
    Правильное склонение русских существительных по числу.

    Примеры:
        _plural_ru(1, "документ", "документа", "документов") -> "документ"
        _plural_ru(2, "документ", "документа", "документов") -> "документа"
        _plural_ru(5, "документ", "документа", "документов") -> "документов"
        _plural_ru(11, ...) -> "документов"
        _plural_ru(21, ...) -> "документ"
    """
    n_abs = abs(n) % 100
    if 11 <= n_abs <= 19:
        return many
    n_abs = n_abs % 10
    if n_abs == 1:
        return one
    if 2 <= n_abs <= 4:
        return few
    return many


def _severity_label_ru(sev: str) -> str:
    """Русская метка severity."""
    return {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }.get(sev, sev)


def _severity_label_en(sev: str) -> str:
    """EN label severity."""
    return {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }.get(sev, sev)


def _top_severity(summary) -> str:
    """Определяет максимальную severity для CheckSummaryRow."""
    if summary.critical > 0:
        return "critical"
    if summary.high > 0:
        return "high"
    if summary.medium > 0:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Renderer: Overall Summary
# ---------------------------------------------------------------------------


def render_overall_summary(fb: FactBundle, locale: str = "ru") -> str:
    """
    Детерминированный renderer для Overall Summary.

    Все данные — из fb.totals и fb.global_checks / fb.doc_type_checks.
    Никаких LLM-вызовов.
    """
    totals = fb.totals
    global_count = len(fb.global_checks.by_check)
    doc_type_count = sum(
        len(g.by_check) for g in fb.doc_type_checks.by_doc_type.values()
    )

    documents = totals.get("documents", 0)
    checks_planned = totals.get("checks_planned", 0)
    crit = totals.get("critical", 0)
    high = totals.get("high", 0)
    med = totals.get("medium", 0)
    unclear = totals.get("unclear", 0)

    if locale.startswith("ru"):
        doc_word = _plural_ru(documents, "документ", "документа", "документов")
        check_word = _plural_ru(checks_planned, "чек", "чека", "чеков")
        global_word = _plural_ru(global_count, "глобальный", "глобальных", "глобальных")
        doctype_word = _plural_ru(
            doc_type_count, "документотипный", "документотипных", "документотипных"
        )

        parts = [
            f"Проверено {documents} {doc_word}, выполнено {checks_planned} "
            f"{check_word} (с учётом повторов по документам): "
            f"{global_count} {global_word} (уникальных) и "
            f"{doc_type_count} {doctype_word}."
        ]

        # Профиль рисков
        risk_parts: list[str] = []
        if crit > 0:
            crit_word = _plural_ru(crit, "критический риск", "критических риска", "критических рисков")
            risk_parts.append(f"{crit} {crit_word}")
        if high > 0:
            high_word = _plural_ru(high, "высокий риск", "высоких риска", "высоких рисков")
            risk_parts.append(f"{high} {high_word}")
        if med > 0:
            med_word = _plural_ru(med, "средний риск", "средних риска", "средних рисков")
            risk_parts.append(f"{med} {med_word}")

        if risk_parts:
            parts.append(
                "По итогам проверки выявлено " + ", ".join(risk_parts) + "."
            )
        else:
            parts.append("Существенных рисков не выявлено.")

        if unclear > 0:
            unclear_word = _plural_ru(unclear, "чек", "чека", "чеков")
            parts.append(
                f"{unclear} {unclear_word} требуют ручной юридической проверки."
            )

        return " ".join(parts)

    # EN
    parts = [
        f"We reviewed {documents} document(s) and performed "
        f"{checks_planned} check execution(s) (including repeats across "
        f"documents): {global_count} unique global check(s) and "
        f"{doc_type_count} document-type check(s)."
    ]

    risk_parts_en: list[str] = []
    if crit > 0:
        risk_parts_en.append(f"{crit} critical-risk")
    if high > 0:
        risk_parts_en.append(f"{high} high-risk")
    if med > 0:
        risk_parts_en.append(f"{med} medium-risk")

    if risk_parts_en:
        parts.append(
            "The review identified "
            + ", ".join(risk_parts_en)
            + " finding(s)."
        )
    else:
        parts.append("No material findings were identified.")

    if unclear > 0:
        parts.append(f"{unclear} check(s) require manual review.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Renderer: Global Checks Summary
# ---------------------------------------------------------------------------


def render_global_summary(fb: FactBundle, locale: str = "ru") -> str:
    """
    Детерминированный renderer для Global Checks Summary.

    Все данные — из fb.global_checks.
    """
    gc = fb.global_checks
    total_checks = len(gc.by_check)

    checks_with_issues = sorted(
        [s for s in gc.by_check.values() if s.issues > 0],
        key=lambda s: (-s.critical, -s.high, -s.medium, s.check_name),
    )
    checks_passed = sorted(
        [s for s in gc.by_check.values() if s.issues == 0],
        key=lambda s: s.check_name,
    )

    if locale.startswith("ru"):
        check_word = _plural_ru(total_checks, "глобальный чек", "глобальных чека", "глобальных чеков")
        parts = [f"Применено {total_checks} {check_word}."]

        if checks_with_issues:
            issue_parts: list[str] = []
            for s in checks_with_issues:
                top_sev = _top_severity(s)
                issue_word = _plural_ru(
                    s.issues, "замечание", "замечания", "замечаний"
                )
                issue_parts.append(
                    f"{s.check_name} — {s.issues} {issue_word} "
                    f"максимальной серьёзности {top_sev}"
                )
            check_word_issues = _plural_ru(
                len(checks_with_issues), "чеке", "чеках", "чеках"
            )
            parts.append(
                f"Замечания выявлены в {len(checks_with_issues)} "
                f"{check_word_issues}: " + "; ".join(issue_parts) + "."
            )
        else:
            parts.append("Замечаний не выявлено.")

        if checks_passed:
            passed_word = _plural_ru(
                len(checks_passed), "чек", "чека", "чеков"
            )
            parts.append(
                f"Без замечаний завершено {len(checks_passed)} {passed_word}."
            )
        else:
            parts.append("Чеков, завершённых без замечаний, нет.")

        return " ".join(parts)

    # EN
    parts = [f"{total_checks} global check(s) were applied."]

    if checks_with_issues:
        issue_parts: list[str] = []
        for s in checks_with_issues:
            top_sev = _top_severity(s)
            issue_parts.append(
                f"{s.check_name} — {s.issues} issue(s), top severity {top_sev}"
            )
        parts.append(
            f"Issues were identified in {len(checks_with_issues)} check(s): "
            + "; ".join(issue_parts) + "."
        )
    else:
        parts.append("No issues were identified.")

    if checks_passed:
        parts.append(
            f"Checks passed without findings: {len(checks_passed)}."
        )
    else:
        parts.append("No checks passed without findings.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Renderer: Document-Type Checks Summary
# ---------------------------------------------------------------------------


def render_doc_type_summary(fb: FactBundle, locale: str = "ru") -> str:
    """
    Детерминированный renderer для Document-Type Checks Summary.

    Все данные — из fb.doc_type_checks.
    """
    dtc = fb.doc_type_checks
    total_checks = sum(len(g.by_check) for g in dtc.by_doc_type.values())
    total_issues = sum(
        s.issues for g in dtc.by_doc_type.values() for s in g.by_check.values()
    )
    groups = len(dtc.by_doc_type)

    if groups == 0:
        if locale.startswith("ru"):
            return "Документотипные проверки в рамках данного анализа не применялись."
        return "No document-type checks were applied in this review."

    # Сортировка типов: по убыванию severity
    sorted_groups = sorted(
        dtc.by_doc_type.items(),
        key=lambda x: -(
            sum(
                s.critical * 100 + s.high * 10 + s.medium
                for s in x[1].by_check.values()
            )
        ),
    )

    if locale.startswith("ru"):
        check_word = _plural_ru(
            total_checks, "документотипный чек", "документотипных чека", "документотипных чеков"
        )
        group_word = _plural_ru(groups, "типу", "типам", "типам")
        issue_word = _plural_ru(
            total_issues, "замечание", "замечания", "замечаний"
        )
        lines = [
            f"Применено {total_checks} {check_word} по {groups} {group_word} "
            f"документов. Выявлено {total_issues} {issue_word}."
        ]

        for doc_type_code, grp in sorted_groups:
            checks_with_issues = sorted(
                [s for s in grp.by_check.values() if s.issues > 0],
                key=lambda s: (-s.critical, -s.high, -s.medium, s.check_name),
            )
            checks_passed_count = sum(
                1 for s in grp.by_check.values() if s.issues == 0
            )
            doc_count = len(grp.documents)
            doc_word = _plural_ru(
                doc_count, "документ", "документа", "документов"
            )

            if checks_with_issues:
                issue_parts: list[str] = []
                for s in checks_with_issues:
                    top_sev = _top_severity(s)
                    s_issue_word = _plural_ru(
                        s.issues, "замечание", "замечания", "замечаний"
                    )
                    issue_parts.append(
                        f"{s.check_name} — {s.issues} {s_issue_word} "
                        f"максимальной серьёзности {top_sev}"
                    )
                passed_word = _plural_ru(
                    checks_passed_count, "чек", "чека", "чеков"
                )
                lines.append(
                    f"По типу {doc_type_code} ({doc_count} {doc_word}): "
                    + "; ".join(issue_parts) + ". "
                    f"Без замечаний завершено {checks_passed_count} {passed_word}."
                )
            else:
                passed_word = _plural_ru(
                    checks_passed_count, "чек", "чека", "чеков"
                )
                lines.append(
                    f"По типу {doc_type_code} ({doc_count} {doc_word}) "
                    f"замечаний не выявлено; без замечаний завершено "
                    f"{checks_passed_count} {passed_word}."
                )

        return "\n".join(lines)

    # EN
    lines = [
        f"{total_checks} document-type check(s) were applied across "
        f"{groups} document type(s). {total_issues} issue(s) identified."
    ]

    for doc_type_code, grp in sorted_groups:
        checks_with_issues = sorted(
            [s for s in grp.by_check.values() if s.issues > 0],
            key=lambda s: (-s.critical, -s.high, -s.medium, s.check_name),
        )
        checks_passed_count = sum(
            1 for s in grp.by_check.values() if s.issues == 0
        )
        doc_count = len(grp.documents)

        if checks_with_issues:
            issue_parts: list[str] = []
            for s in checks_with_issues:
                top_sev = _top_severity(s)
                issue_parts.append(
                    f"{s.check_name} — {s.issues} issue(s), top severity {top_sev}"
                )
            lines.append(
                f"Document type {doc_type_code} ({doc_count} document(s)): "
                + "; ".join(issue_parts)
                + f". Checks passed without findings: {checks_passed_count}."
            )
        else:
            lines.append(
                f"Document type {doc_type_code} ({doc_count} document(s)) "
                f"had no issues; {checks_passed_count} check(s) passed."
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Purpose of Report — LLM path
# ---------------------------------------------------------------------------


async def _generate_purpose(fb: FactBundle, locale: str) -> str:
    """Генерирует Purpose of Report через LLM, fallback при недоступности."""
    from engine.llm.client import LLMClient
    from engine.prompts.loader import load_prompt

    payload = _build_purpose_payload(fb)
    prompt_name = f"summary/report_purpose_{locale}_v1"

    try:
        prompt = load_prompt(
            prompt_name,
            {"input_json": json.dumps(payload, ensure_ascii=False, indent=2)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to load prompt",
            extra={"prompt_name": prompt_name, "error": str(exc)},
        )
        return _fallback_purpose(fb, locale)

    client = LLMClient()
    if not client.is_available():
        logger.warning("LLM not available, using fallback")
        return _fallback_purpose(fb, locale)

    try:
        response, error_details = await client.call_with_retries_async(
            prompt,
            temperature=0.0,
            max_tokens=500,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "LLM call failed for purpose_of_report",
            extra={"error": str(exc)},
            exc_info=True,
        )
        return _fallback_purpose(fb, locale)

    if response is None or not (response.text or "").strip():
        logger.warning(
            "LLM returned empty response",
            extra={"error_details": error_details},
        )
        return _fallback_purpose(fb, locale)

    text = (response.text or "").strip()

    if not _validate_numbers(text, payload):
        logger.warning(
            "LLM invented numbers, using fallback",
            extra={"text_preview": text[:300]},
        )
        return _fallback_purpose(fb, locale)

    return text


def _build_purpose_payload(fb: FactBundle) -> dict:
    """Минимальный payload для Purpose."""
    meta = fb.meta
    totals = fb.totals
    dtc = fb.doc_type_checks

    return {
        "playbook_profile": meta.playbook_profile,
        "playbook_version": meta.playbook_version,
        "checks_mode": meta.checks_mode,
        "locale": meta.locale,
        "totals": {
            "documents": totals.get("documents", 0),
            # ВАЖНО: check_executions — это число ЗАПУСКОВ чеков
            # (глобальные считаются по каждому документу).
            # Не равно сумме уникальных check_id.
            "check_executions": totals.get("checks_planned", 0),
            "checks_completed": totals.get("checks_completed", 0),
            "critical": totals.get("critical", 0),
            "high": totals.get("high", 0),
            "medium": totals.get("medium", 0),
            "pass": totals.get("pass", 0),
            "unclear": totals.get("unclear", 0),
        },
        # ВАЖНО: unique_* — это уникальные check_id в playbook,
        # а не число исполнений. Складывать их с check_executions нельзя.
        "unique_global_checks": len(fb.global_checks.by_check),
        "unique_doc_type_checks": sum(
            len(g.by_check) for g in dtc.by_doc_type.values()
        ),
        "doc_types": [
            {
                "code": doc_type,
                "document_count": len(grp.documents),
                "issues": sum(s.issues for s in grp.by_check.values()),
            }
            for doc_type, grp in dtc.by_doc_type.items()
        ],
    }


def _fallback_purpose(fb: FactBundle, locale: str) -> str:
    """Детерминированный fallback для purpose — при недоступности LLM."""
    meta = fb.meta
    totals = fb.totals
    global_count = len(fb.global_checks.by_check)
    doc_type_count = sum(
        len(g.by_check) for g in fb.doc_type_checks.by_doc_type.values()
    )
    doc_type_codes = list(fb.doc_type_checks.by_doc_type.keys())

    if locale.startswith("ru"):
        text = (
            f"Настоящий Отчёт представляет результаты автоматизированной "
            f"юридической проверки {totals.get('documents', 0)} документа(ов) "
            f"с использованием плейбука «{meta.playbook_profile}» "
            f"(версия {meta.playbook_version}). Проверка включала "
            f"{totals.get('checks_planned', 0)} чек(ов): {global_count} "
            f"глобальных и {doc_type_count} документотипных. "
        )
        if doc_type_codes:
            text += f"Типы документов: {', '.join(doc_type_codes)}. "
        text += f"Анализ выполнен в режиме «{meta.checks_mode}»."
    else:
        text = (
            f"This Report presents the results of an automated legal review "
            f"of {totals.get('documents', 0)} document(s) using the "
            f"\u201c{meta.playbook_profile}\u201d playbook "
            f"(version {meta.playbook_version}). The review applied "
            f"{totals.get('checks_planned', 0)} check(s): {global_count} "
            f"global and {doc_type_count} document-type. "
        )
        if doc_type_codes:
            text += (
                "Reviewed documents were classified as: "
                + ", ".join(doc_type_codes)
                + ". "
            )
        text += (
            f"The analysis was performed in \u201c{meta.checks_mode}\u201d mode."
        )

    return text


# ---------------------------------------------------------------------------
# Validation (only for LLM-generated narratives)
# ---------------------------------------------------------------------------


def _validate_numbers(text: str, payload: dict) -> bool:
    """
    Проверяет, что все значимые числа в тексте присутствуют в payload.

    Разрешает «общие» числа (0–10, годы 2000–2100) — они не считаются
    выдуманными.
    """
    allowed = _collect_numbers(payload)
    for match in re.finditer(r"\b(\d+)\b", text):
        num = int(match.group(1))
        if 0 <= num <= 10:
            continue
        if 2000 <= num <= 2100:
            continue
        if num not in allowed:
            logger.warning(
                "Number %d not found in payload",
                num,
                extra={"allowed_sample": sorted(allowed)[:20]},
            )
            return False
    return True


def _collect_numbers(obj: Any) -> set[int]:
    """Рекурсивно собирает все целые числа из dict/list/primitive."""
    result: set[int] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            result |= _collect_numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            result |= _collect_numbers(v)
    elif isinstance(obj, (int, float)):
        result.add(int(obj))
    return result
