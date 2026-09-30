# src/services/dd_request_rules.py

"""
Единый источник правил для авто-генерации DD-запросов.

Проблема:
  Логика «когда check_result порождает DD-request» раньше была
  скопирована в трёх местах:
    - services/review_presenter.py::build_dd_requests
    - services/export/summary_builder.py::_build_dd_requests_for_summary
    - services/export/report_builder.py::_build_dd_requests_for_report
  Каждая копия использовала legacy-триггер:
      raw_value is None or str(raw_value) in {"not_found","not_defined","None",""}
  Такой триггер работал для v1/v2-калибровки, где required-поля были
  fact-полями и пустое значение = "not_defined". В v3-калибровке
  required-поля — signal-поля, у которых LLM всегда возвращает одно из
  allowed_values (present/missing/no/not_applicable/defined/...), т.е.
  триггер не срабатывал вообще и requests не генерировались.

Решение (Commit 4d.1):
  Общее правило — по check_result.review_status. Значения по умолчанию:
    clause_missing           — все signal-поля = fallback (информации нет);
    clause_partially_defined — часть signal-полей = fallback (часть не найдена);
    unclear                  — конфликт / нужна ручная верификация.

  review_status вычисляется executor'ом из structured_data, учитывая
  presentation=signal поля чека. Это даёт точный признак «информация не
  найдена», в отличие от result: result=pass может означать как полное
  покрытие (clause_defined), так и частичное (clause_partially_defined).

  Per-check override:
    CheckDefinition.dd_request_when_result: list[str] | None
    Если задан — используется вместо общего правила.

Модуль без состояния, без обращений к БД, без логирования —
чистая функция, легко тестируется.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = [
    "DD_REQUEST_DEFAULT_REVIEW_STATUSES",
    "DD_REQUEST_DEFAULT_RESULTS",  # backward-compat alias
    "should_trigger_dd_request",
    "normalize_dd_request_results",
]


# Категории review_status, по умолчанию порождающие DD-request.
# review_status вычисляется executor'ом (см. engine/checks/result_semantics.py)
# из structured_data и presentation=signal полей чека. Это более точный
# признак "информация не найдена", чем result:
#   - clause_missing          — все signal-поля = fallback
#   - clause_partially_defined — часть signal-полей = fallback, часть defined
#   - unclear                 — конфликт в данных / ручная верификация
DD_REQUEST_DEFAULT_REVIEW_STATUSES: frozenset[str] = frozenset(
    {
        "clause_missing",
        "clause_partially_defined",
        "unclear",
    }
)

# Backward-compat alias (будет удалён после обновления тестов/consumer'ов).
DD_REQUEST_DEFAULT_RESULTS = DD_REQUEST_DEFAULT_REVIEW_STATUSES


def normalize_dd_request_results(
    values: Iterable[Any] | None,
) -> frozenset[str]:
    """
    Normalize an iterable of result values to a lowercase frozenset.

    - None / empty -> empty frozenset.
    - Whitespace and case are ignored.
    - Non-string values are coerced via str().
    """
    if not values:
        return frozenset()
    out: set[str] = set()
    for v in values:
        if v is None:
            continue
        s = str(v).strip().lower()
        if s:
            out.add(s)
    return frozenset(out)


def should_trigger_dd_request(
    *,
    check_result: Mapping[str, Any],
    override_results: Iterable[str] | None = None,
) -> bool:
    """
    Должен ли данный check_result породить DD-request.

    Единственный источник правды — check_result.review_status
    (вычисляется executor'ом на основе structured_data и signal-полей).

    Args:
        check_result:      dict-строка из check_results.
                           Читается поле review_status.
        override_results:  если задан (CheckDefinition.dd_request_when_result),
                           используется вместо общего набора. Пустой список
                           значит «никогда» (явное выключение для чека).

    Returns:
        True, если review_status ∈ разрешённый набор; иначе False.

    Правила:
        - review_status is None / empty / whitespace -> False.
        - override_results is None          -> DD_REQUEST_DEFAULT_REVIEW_STATUSES.
        - override_results = []             -> никогда.
        - override_results = [X, Y]         -> {X, Y}.
    """
    raw_status = check_result.get("review_status")
    if raw_status is None:
        return False
    normalized = str(raw_status).strip().lower()
    if not normalized:
        return False

    allowed = (
        DD_REQUEST_DEFAULT_REVIEW_STATUSES
        if override_results is None
        else normalize_dd_request_results(override_results)
    )
    if not allowed:
        return False

    return normalized in allowed
