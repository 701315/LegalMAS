#!/usr/bin/env python3
# scripts/pilot_dd_grid_v1.py

"""
DD Grid V1 Pilot / Smoke Validation Tool.

Запускает build_dd_grid_v1_response() на реальных данных
и показывает summary структуры ответа.

Использование:
    PYTHONPATH=src python scripts/pilot_dd_grid_v1.py \\
        --deal-id <uuid> \\
        --run-id <uuid>

Опции:
    --output console|json    (default: console)
    --save-json /path/to/file.json
    --sample-limit N         (default: 5)
    --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="DD Grid V1 Pilot / Smoke Validation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--deal-id", required=True, help="UUID сделки")
    p.add_argument("--run-id", required=True, help="UUID рана")
    p.add_argument(
        "--output",
        choices=["console", "json"],
        default="console",
        help="Формат вывода (default: console)",
    )
    p.add_argument(
        "--save-json",
        default=None,
        metavar="PATH",
        help="Сохранить полный JSON ответа в файл",
    )
    p.add_argument(
        "--sample-limit",
        type=int,
        default=5,
        metavar="N",
        help="Количество примеров в sample-секциях (default: 5)",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Расширенный вывод",
    )
    return p.parse_args()


def _validate_uuid(value: str, name: str) -> str:
    """Проверить что строка является валидным UUID."""
    try:
        return str(uuid.UUID(value))
    except ValueError:
        print(f"[ERROR] {name} должен быть валидным UUID, получено: {repr(value)}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Pure analytics helpers (testable, no I/O)
# ---------------------------------------------------------------------------


def count_cell_states(
    cell_values: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """
    Подсчитать распределение cell_state по всем ячейкам.

    Args:
        cell_values: {doc_id: {column_id: CellValueDTO-like dict}}

    Returns:
        {state: count}
    """
    counts: dict[str, int] = {
        "defined": 0,
        "not_defined": 0,
        "not_applicable": 0,
        "not_executed": 0,
        "error": 0,
    }

    for doc_cells in cell_values.values():
        for cell in doc_cells.values():
            state = _get_cell_state(cell)
            if state in counts:
                counts[state] += 1
            else:
                counts[state] = counts.get(state, 0) + 1

    return counts


def _get_cell_state(cell: Any) -> str:
    """Извлечь cell_state из cell объекта или dict."""
    if hasattr(cell, "cell_state"):
        return str(cell.cell_state)
    if isinstance(cell, dict):
        return str(cell.get("cell_state", "unknown"))
    return "unknown"


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Универсальный getter для dataclass или dict."""
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def collect_sample_cells(
    cell_values: dict[str, dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Собрать примеры ячеек для вывода.

    Приоритет: error → defined → not_defined.
    Пропускаем not_applicable и not_executed (неинформативны).

    Args:
        cell_values: {doc_id: {column_id: cell}}
        limit: максимальное количество примеров

    Returns:
        Список dict с полями doc_id, column_id, cell_state, display_value, raw_value,
        location_clause_ref, location_page, has_location_fallback.
    """
    priority = {"error": 0, "defined": 1, "not_defined": 2, "not_applicable": 3, "not_executed": 4}
    candidates: list[tuple[int, dict[str, Any]]] = []

    for doc_id, doc_cells in cell_values.items():
        for column_id, cell in doc_cells.items():
            state = _get_cell_state(cell)
            rank = priority.get(state, 99)
            candidates.append((
                rank,
                {
                    "doc_id": doc_id,
                    "column_id": column_id,
                    "cell_state": state,
                    "display_value": _get_attr(cell, "display_value", ""),
                    "raw_value": _get_attr(cell, "raw_value"),
                    "location_clause_ref": _get_attr(cell, "location_clause_ref"),
                    "location_page": _get_attr(cell, "location_page"),
                    "location_confidence": _get_attr(cell, "location_confidence"),
                    "has_location_fallback": _get_attr(cell, "has_location_fallback", False),
                    "location_fallback_reason": _get_attr(cell, "location_fallback_reason"),
                },
            ))

    candidates.sort(key=lambda x: x[0])
    return [item for _, item in candidates[:limit]]


def collect_sample_drawers(
    drawer_contents: dict[str, dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Собрать примеры drawer contents для вывода.

    Приоритет:
    - drawers с reason
    - drawers с evidence_items
    - drawers с field location
    - остальные

    Args:
        drawer_contents: {doc_id: {check_id: drawer}}
        limit: максимальное количество примеров

    Returns:
        Список dict с ключевыми полями drawer.
    """
    scored: list[tuple[int, dict[str, Any]]] = []

    for doc_id, doc_drawers in drawer_contents.items():
        for check_id, drawer in doc_drawers.items():
            reason = _get_attr(drawer, "reason")
            evidence_items = _get_attr(drawer, "evidence_items") or []
            fields = _get_attr(drawer, "fields") or []
            cell_state = _get_attr(drawer, "cell_state", "unknown")

            has_reason = bool(reason and str(reason).strip())
            has_evidence = bool(evidence_items)
            has_location = any(
                _get_attr(f, "location_clause_ref") or _get_attr(f, "location_page")
                for f in fields
            )

            # Меньший score → выше приоритет
            score = (
                (0 if has_reason else 1)
                + (0 if has_evidence else 1)
                + (0 if has_location else 1)
            )

            scored.append((
                score,
                {
                    "doc_id": doc_id,
                    "check_id": check_id,
                    "cell_state": cell_state,
                    "reason": reason,
                    "review_status": _get_attr(drawer, "review_status"),
                    "execution_status": _get_attr(drawer, "execution_status"),
                    "detection_level": _get_attr(drawer, "detection_level"),
                    "confidence": _get_attr(drawer, "confidence"),
                    "quality_flags": _get_attr(drawer, "quality_flags"),
                    "qc_status": _get_attr(drawer, "qc_status"),
                    "qc_by": _get_attr(drawer, "qc_by"),
                    "qc_at": _get_attr(drawer, "qc_at"),
                    "qc_comment": _get_attr(drawer, "qc_comment"),
                    "agent_name": _get_attr(drawer, "agent_name"),
                    "model_version": _get_attr(drawer, "model_version"),
                    "execution_time_ms": _get_attr(drawer, "execution_time_ms"),
                    "retry_attempts": _get_attr(drawer, "retry_attempts"),
                    "input_tokens": _get_attr(drawer, "input_tokens"),
                    "output_tokens": _get_attr(drawer, "output_tokens"),
                    "evidence_items": list(evidence_items),
                    "fields_count": len(fields),
                    "fields_with_location": sum(
                        1 for f in fields
                        if _get_attr(f, "location_clause_ref") or _get_attr(f, "location_page")
                    ),
                    "fields_with_fallback": sum(
                        1 for f in fields
                        if _get_attr(f, "has_location_fallback", False)
                    ),
                    "fields_with_extracted_page": sum(
                        1 for f in fields
                        if _get_attr(f, "location_page") is not None
                        and not _get_attr(f, "has_location_fallback", False)
                    ),
                },
            ))

    scored.sort(key=lambda x: x[0])
    return [item for _, item in scored[:limit]]


def build_summary(response: Any, *, sample_limit: int = 5) -> dict[str, Any]:
    """
    Собрать summary структуры DD Grid V1 response.

    Работает как с Pydantic DTO объектом, так и с dict.
    Не обращается к БД, не делает I/O.

    Args:
        response: DDGridV1ResponseDTO или dict
        sample_limit: количество примеров в sample-секциях

    Returns:
        dict с полным summary.
    """
    deal_id = _get_attr(response, "deal_id", "")
    run_id = _get_attr(response, "run_id", "")

    global_groups = _get_attr(response, "global_groups") or []
    doc_type_classes = _get_attr(response, "doc_type_classes") or []
    column_registry = _get_attr(response, "column_registry") or {}
    cell_values = _get_attr(response, "cell_values") or {}
    drawer_contents = _get_attr(response, "drawer_contents") or {}
    documents_meta = _get_attr(response, "documents_meta") or []

    # Counts
    total_groups = len(global_groups)
    total_doc_type_classes = len(doc_type_classes)
    total_columns = len(column_registry)
    total_documents = len(documents_meta)

    total_cells = sum(len(doc_cells) for doc_cells in cell_values.values())
    total_drawers = sum(len(doc_drawers) for doc_drawers in drawer_contents.values())

    cell_states = count_cell_states(cell_values)

    # Samples
    sample_groups = [
        {
            "group_id": _get_attr(g, "group_id", ""),
            "label": _get_attr(g, "label", ""),
            "display_order": _get_attr(g, "display_order", 0),
            "checks_count": len(_get_attr(g, "checks") or []),
        }
        for g in list(global_groups)[:sample_limit]
    ]

    sample_columns = [
        {
            "column_id": col_id,
            "label": _get_attr(col, "label", ""),
            "format": _get_attr(col, "format", ""),
            "unit": _get_attr(col, "unit"),
        }
        for col_id, col in list(column_registry.items())[:sample_limit]
    ]

    sample_doc_types = []
    for cls in list(doc_type_classes)[:sample_limit]:
        types = _get_attr(cls, "types") or []
        sample_doc_types.append({
            "group_id": _get_attr(cls, "group_id", ""),
            "label": _get_attr(cls, "label", ""),
            "types": [
                {
                    "type_code": _get_attr(t, "type_code", ""),
                    "name": _get_attr(t, "name", ""),
                    "checks_count": len(_get_attr(t, "checks") or []),
                }
                for t in list(types)[:sample_limit]
            ],
        })

    sample_documents = [
        {
            "document_id": _get_attr(d, "document_id", ""),
            "filename": _get_attr(d, "filename", ""),
            "doc_type": _get_attr(d, "doc_type"),
            "status": _get_attr(d, "status", ""),
        }
        for d in list(documents_meta)[:sample_limit]
    ]

    sample_cells = collect_sample_cells(cell_values, limit=sample_limit)
    sample_drawers = collect_sample_drawers(drawer_contents, limit=sample_limit)

    # Location stats
    cells_with_exact_location = 0
    cells_with_fallback_location = 0
    cells_with_extracted_page = 0

    for doc_cells in cell_values.values():
        for cell in doc_cells.values():
            has_fallback = _get_attr(cell, "has_location_fallback", False)
            has_clause_ref = bool(_get_attr(cell, "location_clause_ref"))
            has_page = _get_attr(cell, "location_page") is not None

            if has_fallback:
                cells_with_fallback_location += 1
            elif has_clause_ref or has_page:
                cells_with_exact_location += 1

            if has_page and not has_fallback:
                cells_with_extracted_page += 1

    drawers_with_reason = sum(
        1 for doc_drawers in drawer_contents.values()
        for drawer in doc_drawers.values()
        if bool(_get_attr(drawer, "reason"))
    )
    drawers_with_evidence = sum(
        1 for doc_drawers in drawer_contents.values()
        for drawer in doc_drawers.values()
        if bool(_get_attr(drawer, "evidence_items"))
    )

    # B3 P0 transparency counters
    execution_status_dist: dict[str, int] = {}
    detection_level_dist: dict[str, int] = {}
    drawers_with_confidence = 0
    drawers_with_quality_flags = 0
    drawers_with_qc = 0

    for doc_drawers in drawer_contents.values():
        for drawer in doc_drawers.values():
            exec_status = _get_attr(drawer, "execution_status") or "None"
            execution_status_dist[exec_status] = execution_status_dist.get(exec_status, 0) + 1

            det_level = _get_attr(drawer, "detection_level") or "None"
            detection_level_dist[det_level] = detection_level_dist.get(det_level, 0) + 1

            if _get_attr(drawer, "confidence") is not None:
                drawers_with_confidence += 1

            if _get_attr(drawer, "quality_flags"):
                drawers_with_quality_flags += 1

            if _get_attr(drawer, "qc_status") not in (None, "pending"):
                drawers_with_qc += 1

    # B3 P1 observability counters
    drawers_with_agent_name = 0
    drawers_with_model_version = 0
    drawers_with_execution_time = 0
    drawers_with_input_tokens = 0

    for doc_drawers in drawer_contents.values():
        for drawer in doc_drawers.values():
            if _get_attr(drawer, "agent_name") is not None:
                drawers_with_agent_name += 1
            if _get_attr(drawer, "model_version") is not None:
                drawers_with_model_version += 1
            if _get_attr(drawer, "execution_time_ms") is not None:
                drawers_with_execution_time += 1
            if _get_attr(drawer, "input_tokens") is not None:
                drawers_with_input_tokens += 1

    return {
        "deal_id": deal_id,
        "run_id": run_id,
        "counts": {
            "global_groups": total_groups,
            "doc_type_classes": total_doc_type_classes,
            "columns": total_columns,
            "documents": total_documents,
            "cells": total_cells,
            "drawers": total_drawers,
        },
        "cell_states": cell_states,
        "location": {
            "cells_with_exact_location": cells_with_exact_location,
            "cells_with_fallback_location": cells_with_fallback_location,
            "cells_with_extracted_page": cells_with_extracted_page,
        },
        "drawers": {
            "with_reason": drawers_with_reason,
            "with_evidence": drawers_with_evidence,
        },
        "transparency": {
            "execution_status_distribution": execution_status_dist,
            "detection_level_distribution": detection_level_dist,
            "drawers_with_confidence": drawers_with_confidence,
            "drawers_with_quality_flags": drawers_with_quality_flags,
            "drawers_with_qc_actioned": drawers_with_qc,
            "drawers_with_agent_name": drawers_with_agent_name,
            "drawers_with_model_version": drawers_with_model_version,
            "drawers_with_execution_time": drawers_with_execution_time,
            "drawers_with_input_tokens": drawers_with_input_tokens,
        },
        "samples": {
            "groups": sample_groups,
            "doc_type_classes": sample_doc_types,
            "columns": sample_columns,
            "documents": sample_documents,
            "cells": sample_cells,
            "drawers": sample_drawers,
        },
    }


def check_health(summary: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Проверить базовое health condition ответа.

    Returns:
        (is_healthy, list_of_warnings)
    """
    warnings: list[str] = []
    counts = summary.get("counts", {})

    if counts.get("columns", 0) == 0:
        warnings.append("WARN: column_registry пуст — нет checks с extraction config")

    if counts.get("documents", 0) == 0:
        warnings.append("WARN: documents_meta пуст — нет документов в run")

    if counts.get("cells", 0) == 0 and counts.get("documents", 0) > 0:
        warnings.append("WARN: cell_values пуст при наличии документов")

    states = summary.get("cell_states", {})
    error_count = states.get("error", 0)
    total_cells = counts.get("cells", 0)
    if total_cells > 0 and error_count / total_cells > 0.5:
        warnings.append(f"WARN: >50% ячеек в состоянии error ({error_count}/{total_cells})")

    is_healthy = (
        counts.get("columns", 0) > 0
        and counts.get("documents", 0) > 0
    )

    return is_healthy, warnings


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_console_summary(summary: dict[str, Any], *, verbose: bool = False) -> None:
    """Печать читабельного summary в console."""
    sep = "═" * 72
    thin = "─" * 72

    print(sep)
    print("  DD Grid V1 — Pilot Smoke Validation")
    print(f"  Deal ID : {summary['deal_id']}")
    print(f"  Run  ID : {summary['run_id']}")
    print(sep)

    counts = summary["counts"]
    print("\n📊 Структура ответа:")
    print(f"  Global groups      : {counts['global_groups']}")
    print(f"  Doc-type classes   : {counts['doc_type_classes']}")
    print(f"  Columns            : {counts['columns']}")
    print(f"  Documents          : {counts['documents']}")
    print(f"  Cells              : {counts['cells']}")
    print(f"  Drawers            : {counts['drawers']}")

    states = summary["cell_states"]
    print("\n🔵 Cell states:")
    for state, cnt in states.items():
        bar = "█" * min(cnt, 30) if cnt > 0 else ""
        print(f"  {state:<16}: {cnt:>5}  {bar}")

    drw = summary["drawers"]
    print("\n📋 Drawers:")
    print(f"  With reason        : {drw['with_reason']}")
    print(f"  With evidence      : {drw['with_evidence']}")

    tr = summary.get("transparency", {})
    if tr:
        print("\n🔍 Transparency (B3):")

        exec_dist = tr.get("execution_status_distribution", {})
        if exec_dist:
            print("  execution_status   :")
            for status, cnt in sorted(exec_dist.items()):
                print(f"    {status:<16}: {cnt}")

        det_dist = tr.get("detection_level_distribution", {})
        if det_dist:
            print("  detection_level    :")
            for level, cnt in sorted(det_dist.items()):
                print(f"    {level:<16}: {cnt}")

        print(f"  with confidence    : {tr.get('drawers_with_confidence', 0)}")
        print(f"  with quality_flags : {tr.get('drawers_with_quality_flags', 0)}")
        print(f"  qc actioned        : {tr.get('drawers_with_qc_actioned', 0)}")
        print(f"  with agent_name    : {tr.get('drawers_with_agent_name', 0)}")
        print(f"  with model_version : {tr.get('drawers_with_model_version', 0)}")
        print(f"  with exec_time_ms  : {tr.get('drawers_with_execution_time', 0)}")
        print(f"  with input_tokens  : {tr.get('drawers_with_input_tokens', 0)}")

    loc = summary["location"]
    print("\n📍 Location:")
    print(f"  Exact location     : {loc['cells_with_exact_location']}")
    print(f"  Fallback location  : {loc['cells_with_fallback_location']}")
    print(f"  Page extracted     : {loc.get('cells_with_extracted_page', 0)}")

    samples = summary["samples"]

    if samples["groups"]:
        print(f"\n📁 Global groups (sample {len(samples['groups'])}):")
        for g in samples["groups"]:
            print(f"  [{g['display_order']:>3}] {g['group_id']:<30} | {g['label']:<30} | checks={g['checks_count']}")

    if samples["doc_type_classes"]:
        print(f"\n🗂  Doc-type classes (sample {len(samples['doc_type_classes'])}):")
        for cls in samples["doc_type_classes"]:
            print(f"  {cls['group_id']:<30} | {cls['label']}")
            for t in cls["types"]:
                print(f"    └── {t['type_code']:<25} | {t['name']:<25} | checks={t['checks_count']}")

    if samples["columns"]:
        print(f"\n🔲 Columns (sample {len(samples['columns'])}):")
        for col in samples["columns"]:
            unit = f" [{col['unit']}]" if col["unit"] else ""
            print(f"  {col['column_id']:<40} | fmt={col['format']:<12} | {col['label']}{unit}")

    if samples["documents"]:
        print(f"\n📄 Documents (sample {len(samples['documents'])}):")
        for doc in samples["documents"]:
            print(f"  {doc['document_id']} | {doc['doc_type'] or '?':>15} | {doc['status']:<12} | {doc['filename']}")

    if verbose and samples["cells"]:
        print(f"\n🧩 Cell samples (top {len(samples['cells'])}):")
        print(thin)
        for cell in samples["cells"]:
            print(f"  [{cell['cell_state']:<14}] {cell['column_id']}")
            print(f"    doc_id        = {cell['doc_id']}")
            print(f"    display_value = {repr(cell['display_value'])}")
            print(f"    raw_value     = {repr(cell['raw_value'])}")
            has_pinpoint = cell["location_clause_ref"] or cell["location_page"]
            has_fallback = cell.get("has_location_fallback", False)
            if has_pinpoint and not has_fallback:
                print(
                    f"    location      = {cell['location_clause_ref']} "
                    f"p.{cell['location_page']} "
                    f"conf={cell['location_confidence']}"
                )
            elif has_fallback:
                ref_part = (
                    f"{cell['location_clause_ref']} p.{cell['location_page']}"
                    if has_pinpoint
                    else "no pinpoint"
                )
                print(
                    f"    location      = {ref_part} "
                    f"conf={cell['location_confidence']} [FALLBACK]"
                )
                if cell.get("location_fallback_reason"):
                    print(f"    fallback_rsn  = {repr(cell['location_fallback_reason'])}")
            print()

    if verbose and samples["drawers"]:
        print(f"\n🗃  Drawer samples (top {len(samples['drawers'])}):")
        print(thin)
        for drw in samples["drawers"]:
            print(f"  check_id={drw['check_id']} | state={drw['cell_state']}")
            print(f"    doc_id           = {drw['doc_id']}")
            print(f"    reason           = {repr(drw['reason'])}")
            print(f"    review_status    = {drw['review_status']}")
            print(f"    execution_status = {drw['execution_status']}")

            det_level = drw.get("detection_level")
            confidence = drw.get("confidence")
            level_str = det_level if det_level else "—"
            conf_str = f"{confidence:.2f}" if confidence is not None else "—"
            print(f"    detection_level  = {level_str}  |  confidence = {conf_str}")

            quality_flags = drw.get("quality_flags")
            if quality_flags:
                flags_str = ", ".join(quality_flags.keys())
                print(f"    quality_flags    = ⚠ {flags_str}")
            else:
                print(f"    quality_flags    = —")

            qc_status = drw.get("qc_status")
            if qc_status and qc_status != "pending":
                qc_by = drw.get("qc_by") or "?"
                qc_at = drw.get("qc_at") or "?"
                print(f"    qc_status        = {qc_status} by {qc_by} at {qc_at}")
                if drw.get("qc_comment"):
                    print(f"    qc_comment       = {repr(drw['qc_comment'])}")
            else:
                print(f"    qc_status        = {qc_status or '—'}")

            agent = drw.get("agent_name") or "—"
            model = drw.get("model_version") or "—"
            exec_ms = drw.get("execution_time_ms")
            exec_str = f"{exec_ms} ms" if exec_ms is not None else "—"
            retries = drw.get("retry_attempts")
            retries_str = str(retries) if retries is not None else "—"
            in_tok = drw.get("input_tokens")
            in_tok_str = str(in_tok) if in_tok is not None else "—"
            out_tok = drw.get("output_tokens")
            out_tok_str = str(out_tok) if out_tok is not None else "—"
            print(f"    agent_name       = {agent}  |  model = {model}")
            print(f"    exec_time        = {exec_str}  |  retries = {retries_str}")
            print(f"    tokens           = in:{in_tok_str}  out:{out_tok_str}")

            print(f"    fields_count     = {drw['fields_count']}")
            print(f"    with_location    = {drw['fields_with_location']}")
            print(f"    with_fallback    = {drw['fields_with_fallback']}")
            print(f"    extracted_page   = {drw.get('fields_with_extracted_page', 0)}")
            if drw["evidence_items"]:
                for ev in drw["evidence_items"][:3]:
                    print(f"    evidence         → {repr(ev)}")
            print()

    print(thin)
    is_healthy, health_warnings = check_health(summary)
    for w in health_warnings:
        print(f"  ⚠  {w}")

    status_icon = "✅" if is_healthy else "❌"
    print(f"\n{status_icon}  ИТОГ: {'OK' if is_healthy else 'ISSUES FOUND'}")
    print(sep)


def save_json_snapshot(response: Any, path: str) -> None:
    """Сохранить полный JSON ответа в файл."""
    out_path = Path(path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = response.model_dump(mode="json") if hasattr(response, "model_dump") else dict(response)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        print(f"[INFO] JSON snapshot сохранён: {out_path}", file=sys.stderr)
    except Exception as exc:
        print(f"[WARN] Не удалось сохранить JSON snapshot: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Async main
# ---------------------------------------------------------------------------


async def async_main(
    deal_id: str,
    run_id: str,
    *,
    output: str = "console",
    save_json: str | None = None,
    sample_limit: int = 5,
    verbose: bool = False,
) -> int:
    """
    Основной async entry point пилота.

    Returns:
        0 — success, 1 — failure
    """
    from services.deal_review_service import build_dd_grid_v1_response

    print(f"[INFO] Building DD Grid V1 for deal={deal_id} run={run_id} ...", file=sys.stderr)

    try:
        response = await build_dd_grid_v1_response(deal_id=deal_id, run_id=run_id)
    except ValueError as exc:
        print(f"[ERROR] Not found: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[ERROR] Unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("[INFO] Response built successfully.", file=sys.stderr)

    if save_json:
        save_json_snapshot(response, save_json)

    summary = build_summary(response, sample_limit=sample_limit)

    if output == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    else:
        print_console_summary(summary, verbose=verbose)

    _, health_warnings = check_health(summary)
    return 1 if health_warnings else 0


def main() -> None:
    args = parse_args()

    deal_id = _validate_uuid(args.deal_id, "--deal-id")
    run_id = _validate_uuid(args.run_id, "--run-id")

    exit_code = asyncio.run(
        async_main(
            deal_id=deal_id,
            run_id=run_id,
            output=args.output,
            save_json=args.save_json,
            sample_limit=args.sample_limit,
            verbose=args.verbose,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()


    