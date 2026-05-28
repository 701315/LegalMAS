"""Построение контекстных окон для анализа последовательностей."""

from __future__ import annotations
from collections import defaultdict
from typing import Any
from services.structure.heading_patterns import normalize_spaces, parse_raw_heading
from ._utils import _element_scope

def _build_context_windows(elements: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    parsed_by_scope: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for i, el in enumerate(elements):
        try:
            raw_text = normalize_spaces(str(el.get("text") or ""))
            if not raw_text: continue
            parsed = parse_raw_heading(raw_text)
            if parsed and parsed[0]:
                parsed_by_scope[_element_scope(el)].append((i, normalize_spaces(str(parsed[0]))))
        except: continue

    context_map: dict[int, dict[str, Any]] = {}
    for scope, items in parsed_by_scope.items():
        items.sort(key=lambda x: x[0])
        for pos, (elem_i, raw_uid) in enumerate(items):
            context_map[elem_i] = {
                "scope": scope,
                "prev_heading_uid": items[pos - 1][1] if pos > 0 else None,
                "next_heading_uid": items[pos + 1][1] if pos + 1 < len(items) else None,
            }
    return context_map


