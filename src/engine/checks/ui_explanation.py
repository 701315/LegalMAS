# src/engine/checks/ui_explanation.py

"""
User-facing explanation builder for check results.

Задача:
- превратить внутренние result/execution_status/structured_data в понятный текст для юриста;
- не менять бизнес-результат и не вмешиваться в execution_status;
- вернуть компактный DTO, который можно сохранить в quality_flags.

Логика определения режима presence-check
-----------------------------------------
Функция _is_presence_style_check() определяет, является ли чек проверкой
"на наличие обязательной клаузулы" (в отличие от "есть ли риск/дефект").

Это важно, потому что UI-сообщение при result=pass разное:
- presence-check + pass → "Положение обнаружено."
- risk-check + pass    → "Признаков риска не обнаружено."

Приоритет определения:
1. Явный ui_mode из playbook (рекомендуемый способ для всех новых чеков):
   - ui_mode: clause_presence → presence-check
   - ui_mode: <любое другое непустое значение> → НЕ presence-check
   - ui_mode не задан или None → переходим к эвристике
2. Fallback-эвристика по именам check.id / check.name / полям extraction:
   - ищем подстроки из _PRESENCE_HINTS в объединённой строке кандидатов.
   - Используется только для старых чеков без ui_mode.

Как добавить новый чек правильно:
  В YAML-файле чека задайте поле ui_mode:
    ui_mode: clause_presence   # для presence-чеков
    ui_mode: risk_detection    # для risk-чеков
    ui_mode: field_extraction  # для чеков-экстракторов

Логика _has_not_found_value()
------------------------------
Возвращает True только если ВСЕ заполненные поля structured_data
имеют not-found значение. Одно пустое поле при наличии заполненных
других — не считается "клаузула не найдена".
"""

from __future__ import annotations

from typing import Any

from core.config import settings
from core.constants import CheckExecutionStatus
from core.logging import get_logger
from engine.checks.extraction_semantics import is_not_found_scalar

logger = get_logger(__name__)


# Подстроки, наличие которых в id/name/полях чека говорит о том,
# что чек относится к поиску обязательной клаузулы (presence-style).
# Используется ТОЛЬКО как fallback для старых чеков без явного ui_mode.
# НЕ добавляй сюда предметные слова конкретных чеков (например, "coc",
# "governing_law", "force_majeure") — такие чеки должны получить ui_mode в YAML.
_PRESENCE_HINTS = {
    "presence",
    "required_clause",
    "required clause",
    "mandatory_clause",
    "mandatory clause",
    "clause_presence",
    "has_clause",
    "has clause",
}


def build_user_explanation(
    *,
    check: Any,
    exec_result: dict,
    execution_status: str,
    structured_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Построить user-facing explanation для UI/отчёта.

    Возвращает:
    {
        "user_status": str,
        "user_message": str,
        "needs_manual_review": bool,
    }
    """
    result = str(exec_result.get("result") or "").strip().lower()
    reason = str(exec_result.get("reason") or "").strip().lower()

    raw = exec_result.get("raw") or {}
    if not isinstance(raw, dict):
        raw = {}

    raw_error = str(raw.get("error") or "").strip().lower()
    llm_error_type = exec_result.get("llm_error_type") or raw.get("llm_error_type")
    is_presence_check = _is_presence_style_check(check, structured_data)

    # --- 1. Технические сбои: чек не завершился нормально ---

    if execution_status in {
        CheckExecutionStatus.FAILED.value,
        CheckExecutionStatus.TIMEOUT.value,
    }:
        return {
            "user_status": "manual_review_required",
            "user_message": (
                "Проверка не завершена. Система не смогла надёжно проверить "
                "соответствующее положение из-за технического ограничения или ошибки анализа; "
                "нужен ручной просмотр."
            ),
            "needs_manual_review": True,
        }

    # --- 2. Проверка не применима к данному типу документа ---

    if raw_error == "check_not_applicable_for_document" or reason == "check_not_applicable":
        return {
            "user_status": "not_applicable",
            "user_message": (
                "Проверка не применима к данному документу. "
                "Система корректно определила, что этот тип проверки здесь не требуется."
            ),
            "needs_manual_review": False,
        }

    # --- 3. Явный результат "обязательная клаузула отсутствует" ---

    if result == "missing_required_clause":
        return {
            "user_status": "clause_missing",
            "user_message": (
                "Положение не найдено. Система проверила релевантные фрагменты "
                "договора и не обнаружила требуемую клаузулу."
            ),
            "needs_manual_review": False,
        }

    # --- 4. Presence-check: все извлечённые поля вернули not-found значения ---

    if is_presence_check and _has_not_found_value(structured_data):
        return {
            "user_status": "clause_missing",
            "user_message": (
                "Положение не найдено. Система проверила релевантные фрагменты "
                "договора и не обнаружила требуемую клаузулу."
            ),
            "needs_manual_review": False,
        }

    # --- 5. Явный провал проверки ---

    if result == "fail":
        # Проверяем confidence: если низкая — помечаем needs_manual_review=True.
        # Это позволяет юристу видеть разницу между "подтверждённый риск"
        # и "возможный риск с низкой уверенностью".
        confidence = float(exec_result.get("confidence", 1.0) or 0.0)
        severity = str(exec_result.get("severity") or "").strip().lower()

        if severity in ("critical", "high"):
            conf_threshold = float(
                getattr(settings, "CONFIDENCE_MANUAL_REVIEW_THRESHOLD_HIGH_SEVERITY", 0.65)
            )
        else:
            conf_threshold = float(
                getattr(settings, "CONFIDENCE_MANUAL_REVIEW_THRESHOLD", 0.55)
            )

        is_low_confidence = confidence < conf_threshold

        if is_low_confidence:
            return {
                "user_status": "issue_detected",
                "user_message": (
                    "Обнаружено условие или формулировка, требующие внимания. "
                    "Проверьте соответствующий фрагмент договора и оцените правовые последствия."
                ),
                "needs_manual_review": True,
            }

        return {
            "user_status": "issue_detected",
            "user_message": (
                "Обнаружено условие или формулировка, требующие внимания. "
                "Проверьте соответствующий фрагмент договора и оцените правовые последствия."
            ),
            "needs_manual_review": False,
        }

    # --- 6. Успешный результат ---

    if result == "pass":
        if is_presence_check:
            return {
                "user_status": "no_issue_detected",
                "user_message": (
                    "Требуемое положение обнаружено. Проверьте формулировку клаузулы "
                    "и убедитесь, что она соответствует вашей позиции и требованиям сделки."
                ),
                "needs_manual_review": False,
            }

        return {
            "user_status": "no_issue_detected",
            "user_message": (
                "По данной проверке система не обнаружила явных признаков риска "
                "в релевантных фрагментах документа."
            ),
            "needs_manual_review": False,
        }

    # --- 7. Неоднозначный результат ---

    if result == "unclear":
        if llm_error_type:
            return {
                "user_status": "manual_review_required",
                "user_message": (
                    "Проверка не завершена надёжно. Из-за технического ограничения "
                    "или ошибки анализа рекомендуется ручной просмотр."
                ),
                "needs_manual_review": True,
            }

        return {
            "user_status": "unclear",
            "user_message": (
                "Результат проверки неоднозначен. Система не смогла сделать "
                "достаточно надёжный вывод по этому риску; рекомендуется ручной просмотр."
            ),
            "needs_manual_review": True,
        }

    # --- 8. Неизвестное значение result — логируем для диагностики ---

    logger.warning(
        "build_user_explanation: unexpected result value, falling back to unclear",
        result=result,
        execution_status=execution_status,
        check_id=getattr(check, "id", None),
    )

    return {
        "user_status": "unclear",
        "user_message": (
            "Результат проверки требует дополнительной оценки. "
            "Рекомендуется ручной просмотр соответствующего раздела договора."
        ),
        "needs_manual_review": True,
    }


def _has_not_found_value(structured_data: dict[str, Any] | None) -> bool:
    """
    Return True only if ALL evaluated fields semantically mean "not found".

    Uses shared extraction semantics so UI explanation stays aligned with
    executor/result_semantics/business mapping.
    """
    if not isinstance(structured_data, dict):
        return False

    evaluated: list[bool] = []
    for _, field_payload in structured_data.items():
        value = field_payload.get("value") if isinstance(field_payload, dict) else field_payload
        if value is None:
            continue

        evaluated.append(is_not_found_scalar(value))

    return bool(evaluated) and all(evaluated)


def _is_presence_style_check(
    check: Any,
    structured_data: dict[str, Any] | None,
) -> bool:
    """
    Определяем, относится ли чек к поиску/наличию обязательной клаузы.

    Приоритет:
    1) Явный ui_mode из playbook (рекомендуется для всех новых чеков).
    2) Fallback-эвристика для старых checks без ui_mode.

    Подробнее о логике — в docstring модуля вверху файла.
    """
    ui_mode = getattr(check, "ui_mode", None)
    if ui_mode is not None:
        ui_mode_str = str(ui_mode).strip().lower()
        # Пустая строка ui_mode="" — трактуем как "не задан",
        # а не как "не presence". Переходим к эвристике.
        if ui_mode_str:
            return ui_mode_str == "clause_presence"

    # --- Fallback-эвристика (только для старых чеков без ui_mode) ---

    candidates: list[str] = []

    check_id = getattr(check, "id", None)
    check_name = getattr(check, "name", None)

    if check_id:
        candidates.append(str(check_id).lower())
    if check_name:
        candidates.append(str(check_name).lower())

    extraction = getattr(check, "extraction", None)
    fields = getattr(extraction, "fields", None) if extraction is not None else None
    if isinstance(fields, list):
        for field_cfg in fields:
            field_name = getattr(field_cfg, "name", None)
            if field_name:
                candidates.append(str(field_name).lower())

    if isinstance(structured_data, dict):
        candidates.extend(str(k).lower() for k in structured_data.keys())

    joined = " ".join(candidates)
    return any(hint in joined for hint in _PRESENCE_HINTS)
