# src/engine/detectors/rules_detector.py

"""
Rules-based detector: ищет риски по keywords и regex.

Назначение:
- Быстрый, интерпретируемый детектор без LLM.
- Работает поверх RulesConfig из playbook (keywords, keyword_mode, regex_patterns,
  clause_patterns, negative_keywords, keyword_groups).
- Используется как первый этап в HybridDetector перед LLM-детектором.

Возвращает DetectionResult-подобный словарь:
- found / evidence / confidence / method="rules";
- reason, rule_name;
- span (позиция совпадения в тексте);
- raw с полным списком hits, spans и использованных паттернов.

Изменения (keyword_groups support + regex levels):
- Добавлен расчёт confidence на основе уровней из _group_map (RulesConfig).
  * Если keyword_groups задан — confidence определяется уровнем лучшего совпадения:
      high   → base 0.85
      medium → base 0.65
      low    → base 0.45
    плюс небольшой бонус за количество совпадений (не более +0.10).
  * Если keyword_groups не задан — старая эвристика (0.4 + 0.1 * hits).
- Для regex/clause-паттернов теперь учитывается именно паттерн (а не только match),
  чтобы связать совпадения с уровнями из _group_map.
- В raw.hit_levels ключом остаётся текст evidence, значением — уровень (high/medium/low).
"""

import re
from typing import Any

from ..playbook.models import KeywordMode, RulesConfig

# Уровни → базовый confidence при совпадении
_LEVEL_CONFIDENCE: dict[str, float] = {
    "high": 0.85,
    "medium": 0.65,
    "low": 0.45,
}

# Приоритет уровней для выбора "лучшего" при нескольких совпадениях
_LEVEL_PRIORITY: dict[str, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
}

# Базовый confidence для паттернов без группы (старая эвристика недоступна)
_DEFAULT_LEVEL_BASE = 0.50


def _make_empty_raw(rules: RulesConfig) -> dict[str, Any]:
    """Заготовка raw-блока для результатов без совпадений."""
    return {
        "hits": [],
        "negative_hits": [],
        "clause_hits": [],
        "keyword_mode": getattr(rules, "keyword_mode", None),
        "regex_patterns": list(getattr(rules, "regex_patterns", [])),
        "clause_patterns": list(getattr(rules, "clause_patterns", [])),
        "keyword_groups": dict(getattr(rules, "keyword_groups", {}) or {}),
        "hit_levels": {},
    }


def _calc_confidence(patterns: list[str], group_map: dict[str, str]) -> float | None:
    """
    Рассчитать confidence на основе уровней сработавших паттернов.

    patterns: список "ключей" для _group_map (keywords/regex/clause-паттерны).

    Если group_map пуст (keyword_groups не задан) — возвращает None,
    и вызывающий код применяет старую эвристику.
    """
    if not group_map or not patterns:
        return None  # сигнал: использовать старую эвристику

    levels_hit = [group_map.get(p, "low") for p in patterns if p in group_map]
    if not levels_hit:
        return None

    best_level = max(levels_hit, key=lambda lvl: _LEVEL_PRIORITY.get(lvl, 0))
    base = _LEVEL_CONFIDENCE.get(best_level, _DEFAULT_LEVEL_BASE)
    # Бонус за количество: +0.02 за каждое совпадение, не более +0.10
    bonus = min(0.10, 0.02 * len(patterns))
    return min(1.0, base + bonus)


class RulesDetector:
    def detect(self, text: str, rules: RulesConfig) -> dict[str, Any]:
        """
        Вернуть DetectionResult-подобный словарь.

        DetectionResult:
        {
            "found": bool,
            "evidence": str | None,
            "confidence": float,          # 0.0–1.0
            "method": str,                # "rules"
            "reason": str | None,         # краткое объяснение
            "rule_name": str | None,      # имя/ID правила из playbook
            "check_id": str | None,       # заполняется выше по стеку (в HybridDetector)
            "severity": str | None,       # задаётся в CheckExecutor/playbook
            "span": dict | None,          # {"start": int, "end": int}
            "location": dict | None,      # {"chunk_id": "..."} — задаётся выше
            "sources": list | None,       # какие чанки/источники участвовали
            "raw": dict | None,           # сырые данные для дебага
        }
        """
        if not text:
            return {
                "found": False,
                "evidence": "",
                "confidence": 0.0,
                "method": "rules",
                "reason": "empty_text",
                "rule_name": getattr(rules, "name", None),
                "check_id": None,
                "severity": None,
                "span": None,
                "location": None,
                "sources": None,
                "raw": _make_empty_raw(rules),
            }

        text_lower = text.lower()

        # hits: фактические совпадения в тексте (строки)
        hits: list[str] = []
        # hit_patterns: паттерны, которыми эти hits были найдены (keyword/regex/clause)
        hit_patterns: list[str] = []
        spans: list[dict] = []

        # Получаем карту уровней из model_validator (пустая если keyword_groups не задан)
        group_map: dict[str, str] = getattr(rules, "_group_map", {}) or {}

        # ── 1. Positive keywords с учётом keyword_mode ──────────────────────
        pos_hits: list[str] = []
        pos_spans: list[dict] = []

        for kw in rules.keywords:
            kw_lower = kw.lower()
            idx = text_lower.find(kw_lower)
            if idx != -1:
                pos_hits.append(kw)
                pos_spans.append({"start": idx, "end": idx + len(kw)})

        if rules.keyword_mode == KeywordMode.ALL:
            # Требуем все keywords — если хоть одно не найдено, сбрасываем
            if len(rules.keywords) > 0 and len(pos_hits) != len(rules.keywords):
                pos_hits = []
                pos_spans = []

        hits.extend(pos_hits)
        # Для keyword-совпадений паттерн = сам keyword
        hit_patterns.extend(pos_hits)
        spans.extend(pos_spans)

        # ── 2. Regex patterns ────────────────────────────────────────────────
        regex_hits: list[str] = []
        regex_patterns_used: list[str] = []
        regex_spans: list[dict] = []

        for pattern in rules.regex_patterns:
            try:
                m = re.search(pattern, text, flags=re.IGNORECASE)
            except re.error:
                # Некорректный паттерн не ломает детектор
                continue
            if m:
                match_val = m.group(0)
                regex_hits.append(match_val)
                regex_patterns_used.append(pattern)
                regex_spans.append({"start": m.start(), "end": m.end()})

        hits.extend(regex_hits)
        hit_patterns.extend(regex_patterns_used)
        spans.extend(regex_spans)

        # ── 3. Clause patterns ───────────────────────────────────────────────
        clause_hits: list[str] = []
        clause_patterns_used: list[str] = []
        clause_spans: list[dict] = []

        for pattern in getattr(rules, "clause_patterns", []) or []:
            try:
                m = re.search(pattern, text, flags=re.IGNORECASE)
            except re.error:
                continue
            if m:
                match_val = m.group(0)
                clause_hits.append(match_val)
                clause_patterns_used.append(pattern)
                clause_spans.append({"start": m.start(), "end": m.end()})

        hits.extend(clause_hits)
        hit_patterns.extend(clause_patterns_used)
        spans.extend(clause_spans)

        # ── 4. Negative keywords: если нашли — глушим сигнал ────────────────
        negative_hits: list[str] = []
        for kw in getattr(rules, "negative_keywords", []) or []:
            kw_lower = kw.lower()
            if kw_lower in text_lower:
                negative_hits.append(kw)

        if negative_hits:
            return {
                "found": False,
                "evidence": "",
                "confidence": 0.0,
                "method": "rules",
                "reason": "negative_keywords_matched",
                "rule_name": getattr(rules, "name", None),
                "check_id": None,
                "severity": None,
                "span": None,
                "location": None,
                "sources": None,
                "raw": {
                    "hits": hits,
                    "negative_hits": negative_hits,
                    "clause_hits": clause_hits,
                    "keyword_mode": getattr(rules, "keyword_mode", None),
                    "regex_patterns": list(getattr(rules, "regex_patterns", [])),
                    "clause_patterns": list(getattr(rules, "clause_patterns", [])),
                    "keyword_groups": dict(getattr(rules, "keyword_groups", {}) or {}),
                    "hit_levels": {
                        value: group_map[pattern]
                        for value, pattern in zip(hits, hit_patterns)
                        if pattern in group_map
                    },
                },
            }

        # ── 5. Нет положительных совпадений ─────────────────────────────────
        if not hits:
            return {
                "found": False,
                "evidence": "",
                "confidence": 0.0,
                "method": "rules",
                "reason": "no_keywords_or_patterns_matched",
                "rule_name": getattr(rules, "name", None),
                "check_id": None,
                "severity": None,
                "span": None,
                "location": None,
                "sources": None,
                "raw": {
                    "hits": [],
                    "negative_hits": negative_hits,
                    "clause_hits": clause_hits,
                    "keyword_mode": getattr(rules, "keyword_mode", None),
                    "regex_patterns": list(getattr(rules, "regex_patterns", [])),
                    "clause_patterns": list(getattr(rules, "clause_patterns", [])),
                    "keyword_groups": dict(getattr(rules, "keyword_groups", {}) or {}),
                    "hit_levels": {},
                },
            }

        # ── 6. Расчёт confidence ─────────────────────────────────────────────
        #
        # Если keyword_groups задан — используем уровневую логику по паттернам.
        # Иначе — старая эвристика для обратной совместимости.
        confidence_from_levels = _calc_confidence(hit_patterns, group_map)
        if confidence_from_levels is not None:
            confidence = confidence_from_levels
        else:
            confidence = min(1.0, 0.4 + 0.1 * len(hits))

        # hit_levels: текст evidence → уровень паттерна для дебага в UI
        hit_levels = {}
        for value, pattern in zip(hits, hit_patterns):
            if pattern in group_map:
                hit_levels[value] = group_map[pattern]

        # Лучший hit для evidence: сначала ищем high, потом medium, потом low,
        # потом всё остальное (паттерны без уровня).
        if group_map and hit_levels:
            best_evidence = max(
                hit_levels.keys(),
                key=lambda v: _LEVEL_PRIORITY.get(hit_levels[v], 0),
            )
            best_idx = hits.index(best_evidence)
        else:
            best_idx = 0

        evidence = hits[best_idx]
        span = spans[best_idx] if spans else None

        return {
            "found": True,
            "evidence": evidence,
            "confidence": confidence,
            "method": "rules",
            "reason": (
                f"matched rules: keywords/regex/clause_patterns, "
                f"total_hits={len(hits)}"
                + (f", best_level={hit_levels.get(evidence, 'ungrouped')}" if hit_levels else "")
            ),
            "rule_name": getattr(rules, "name", None),
            "check_id": None,  # заполнит HybridDetector
            "severity": None,  # заполнит CheckExecutor/playbook
            "span": span,
            "location": None,  # заполнит HybridDetector (chunk_id/page/clause_uid)
            "sources": None,  # заполнит HybridDetector
            "raw": {
                "hits": hits,
                "spans": spans,
                "negative_hits": negative_hits,
                "clause_hits": clause_hits,
                "keyword_mode": getattr(rules, "keyword_mode", None),
                "regex_patterns": list(getattr(rules, "regex_patterns", [])),
                "clause_patterns": list(getattr(rules, "clause_patterns", [])),
                "keyword_groups": dict(getattr(rules, "keyword_groups", {}) or {}),
                "hit_levels": hit_levels,
            },
        }
