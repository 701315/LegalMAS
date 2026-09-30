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

Решение:
  Общее правило — по check_result.result. Значения по умолчанию:
    missing_required_cla — обязательная клауза отсутствует;
    unclear              — по клаузе не удалось принять решение.
  Эти две категории соответствуют «нужно запросить у стороны доп.
  сведения / документ».

  Per-check override:
    CheckDefinition.dd_request_when_result: list[str] | None
    Если задан — используется вместо общего правила.

Модуль без состояния, без обращений к БД, без логирования —
чистая функция, легко тестируется.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = [
    "DD_REQUEST_DEFAULT_RESULTS",
    "should_trigger_dd_request",
    "normalize_dd_request_results",
]


# Категории result, по умолчанию порождающие DD-request.
DD_REQUEST_DEFAULT_RESULTS: frozenset[str] = frozenset(
    {
        "missing_required_cla",  # mandatory clause absent
        "unclear",               # undecidable by LLM / partial match
    }
)


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

    Args:
        check_result:      dict-строка из check_results (минимум result).
        override_results:  если задан (CheckDefinition.dd_request_when_result),
                           используется вместо общего правила. Пустой список
                           также считается override: не срабатывает никогда.

    Returns:
        True, если check_result.result входит в разрешённый набор; иначе False.

    Правила:
        - result is None / empty / whitespace -> False.
        - override_results is None          -> DD_REQUEST_DEFAULT_RESULTS.
        - override_results = []             -> никогда (явное «выключить»).
        - override_results = [X, Y]         -> {X, Y}.
    """
    raw_result = check_result.get("result")
    if raw_result is None:
        return False
    normalized = str(raw_result).strip().lower()
    if not normalized:
        return False

    allowed = (
        DD_REQUEST_DEFAULT_RESULTS
        if override_results is None
        else normalize_dd_request_results(override_results)
    )
    if not allowed:
        return False

    return normalized in allowed
