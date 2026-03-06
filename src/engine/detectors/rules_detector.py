"""
Rules-based detector: ищет риски по keywords и regex.

Назначение:
- Быстрый, интерпретируемый детектор без LLM.
- Работает поверх RulesConfig из playbook (keywords, keyword_mode, regex_patterns).
- Используется как первый этап в HybridDetector перед LLM-детектором.

Возвращает DetectionResult-подобный словарь:
- found / evidence / confidence / method="rules";
- reason, rule_name;
- span (позиция совпадения в тексте);
- raw с полным списком hits, spans и использованных паттернов.
"""

import re
from typing import Any

from ..playbook.models import KeywordMode, RulesConfig


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
            "severity": str | None,       # опционально, задаётся в CheckExecutor/playbook
            "span": dict | None,          # {"start": int, "end": int}
            "location": dict | None,      # например, {"chunk_id": "..."} — задаётся выше
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
                "raw": {
                    "hits": [],
                    "keyword_mode": getattr(rules, "keyword_mode", None),
                    "regex_patterns": list(getattr(rules, "regex_patterns", [])),
                },
            }

        text_lower = text.lower()
        hits: list[str] = []
        spans: list[dict] = []  # позиции всех совпадений

        # 1. Positive keywords с учётом keyword_mode
        pos_hits: list[str] = []
        for kw in rules.keywords:
            kw_lower = kw.lower()
            idx = text_lower.find(kw_lower)
            if idx != -1:
                pos_hits.append(kw)
                spans.append({"start": idx, "end": idx + len(kw)})

        if rules.keyword_mode == KeywordMode.ALL:
            # Требуем, чтобы все keywords встретились
            if len(pos_hits) != len(rules.keywords):
                pos_hits = []
                spans = []

        hits.extend(pos_hits)

        # 2. Regex patterns
        regex_hits: list[str] = []
        regex_spans: list[dict] = []
        for pattern in rules.regex_patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                regex_hits.append(m.group(0))
                regex_spans.append({"start": m.start(), "end": m.end()})

        hits.extend(regex_hits)
        spans.extend(regex_spans)

        # 3. (опционально) Negative keywords — пока закомментировано
        # В будущем можно добавить rules.negative_keywords и включить эту логику.
        # neg_hits = [kw for kw in rules.negative_keywords if kw.lower() in text_lower]
        # if neg_hits:
        #     return {
        #         "found": False,
        #         "evidence": "",
        #         "confidence": 0.0,
        #         "method": "rules",
        #         "reason": "negative_keywords_matched",
        #         "rule_name": getattr(rules, "name", None),
        #         "check_id": None,
        #         "severity": None,
        #         "span": None,
        #         "location": None,
        #         "sources": None,
        #         "raw": {
        #             "hits": hits,
        #             "negative_hits": neg_hits,
        #             "keyword_mode": getattr(rules, "keyword_mode", None),
        #             "regex_patterns": list(rules.regex_patterns),
        #         },
        #     }

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
                    "keyword_mode": getattr(rules, "keyword_mode", None),
                    "regex_patterns": list(rules.regex_patterns),
                },
            }

        # Простая эвристика confidence: базовый порог + бонус за количество совпадений
        confidence = min(1.0, 0.4 + 0.1 * len(hits))

        # Берём первый hit как evidence и его span, если он есть
        evidence = hits[0]
        span = spans[0] if spans else None

        return {
            "found": True,
            "evidence": evidence,
            "confidence": confidence,
            "method": "rules",
            "reason": f"matched rules: keywords/regex, total_hits={len(hits)}",
            "rule_name": getattr(rules, "name", None),
            "check_id": None,  # заполнит HybridDetector
            "severity": None,  # заполнит CheckExecutor/playbook
            "span": span,
            "location": None,  # можно будет заполнить chunk_id/page/clause_uid выше по стеку
            "sources": None,  # список чанков/источников — тоже выше
            "raw": {
                "hits": hits,
                "spans": spans,
                "keyword_mode": getattr(rules, "keyword_mode", None),
                "regex_patterns": list(rules.regex_patterns),
            },
        }
