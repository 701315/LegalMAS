#!/usr/bin/env python3
"""
Аудит extraction token budget по всем YAML-инструкциям.

Сканирует:
  - playbooks/global_checks/**/*.yaml   — global checks (extraction на верх. уровне)
  - playbooks/document_types/**/*.yaml  — doc-type configs (checks_v8[].extraction)

Для каждого чека с extraction.enabled=true:
  1. Считает рекомендованный llm_max_tokens по схеме полей.
  2. Сравнивает с текущим значением (YAML или дефолт .env).
  3. Дополнительно проверяет llm.max_tokens (detection-фаза) у doc-type чеков.
  4. Выводит таблицу с рекомендациями и конкретными патчами.

Запуск:
  cd /srv/steloom-dev && python3 scripts/audit_extraction_token_budget.py

Exit code:
  0 — всё OK или только предупреждения
  1 — есть критичные проблемы (обрезание гарантировано)
"""

from __future__ import annotations

import glob
import os
import sys

# ── Читаем реальный дефолт из .env ───────────────────────────────────────────
_ENV_DEFAULT_EXTRACTION_TOKENS: int = 900
_ENV_DEFAULT_DETECTION_TOKENS: int  = 512

try:
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _env_path = os.path.join(_project_root, ".env")
    if os.path.isfile(_env_path):
        with open(_env_path, encoding="utf-8") as _ef:
            for _line in _ef:
                _line = _line.strip()
                if _line.startswith("LLM_EXTRACTION_MAX_TOKENS="):
                    try:
                        _ENV_DEFAULT_EXTRACTION_TOKENS = int(
                            _line.split("=", 1)[1].strip().strip('"').strip("'")
                        )
                    except ValueError:
                        pass
                elif _line.startswith("LLM_MAX_TOKENS="):
                    try:
                        _ENV_DEFAULT_DETECTION_TOKENS = int(
                            _line.split("=", 1)[1].strip().strip('"').strip("'")
                        )
                    except ValueError:
                        pass
except Exception:
    pass

# ── YAML loader ───────────────────────────────────────────────────────────────
try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. Выполните: pip install pyyaml")
    sys.exit(1)


# ── Весовые коэффициенты токенов на поле ─────────────────────────────────────
_TOKENS_BY_PRESENTATION: dict[str, int] = {
    "diagnostic": 160,
    "summary":    120,
    "signal":      70,
    "fact":        90,
}
_TOKENS_EVIDENCE_LIST: int = 50
_TOKENS_JSON_OVERHEAD: int = 80
_RESERVE_FACTOR: float     = 1.25
_ROUND_TO: int             = 50


def _round_up(n: int, step: int = _ROUND_TO) -> int:
    remainder = n % step
    return n if remainder == 0 else n + step - remainder


def compute_recommended_extraction_tokens(fields: list[dict]) -> int:
    if not fields:
        return 0
    raw = _TOKENS_JSON_OVERHEAD
    for field in fields:
        field_type   = (field.get("type")         or "string").strip().lower()
        presentation = (field.get("presentation") or "fact").strip().lower()
        if field_type == "evidence_list":
            raw += _TOKENS_EVIDENCE_LIST
        else:
            raw += _TOKENS_BY_PRESENTATION.get(presentation, 90)
    return _round_up(int(raw * _RESERVE_FACTOR))


# ── Парсинг одного чека ───────────────────────────────────────────────────────

def _parse_single_check(
    check: dict,
    filepath: str,
    source_type: str,
) -> dict | None:
    extr = check.get("extraction")
    if not isinstance(extr, dict) or not extr.get("enabled"):
        return None

    fields = extr.get("fields") or []

    llm_section = check.get("llm") or {}
    detection_max_tokens = (
        llm_section.get("max_tokens")
        if isinstance(llm_section.get("max_tokens"), int)
        else None
    )

    return {
        # идентификация
        "check_id":              check.get("id", "???"),
        "check_name":            check.get("name", ""),
        "source":                source_type,
        "file":                  filepath,
        # extraction-фаза
        "fields":                fields,
        "fields_count":          len(fields),
        "extraction_max_tokens": extr.get("llm_max_tokens"),
        # Читаем как tri-state: None (авто), True (explicit on), False (explicit off)
        "compact_output":        extr.get("compact_output"),   # None если не задан
        "has_custom_prompt":     bool(extr.get("llm_prompt_extraction")),
        # detection-фаза
        "detection_max_tokens":  detection_max_tokens,
    }


def extract_checks_from_yaml(filepath: str) -> list[dict]:
    try:
        with open(filepath, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return [{"_error": str(e), "_file": filepath}]

    if not isinstance(data, dict):
        return []

    results: list[dict] = []

    # Формат 1: global check — extraction на верхнем уровне
    if "extraction" in data and isinstance(data["extraction"], dict):
        rec = _parse_single_check(data, filepath, source_type="global_check")
        if rec:
            results.append(rec)
        return results

    # Формат 2: doc-type config — массив чеков в секциях
    for section_key in ("checks_v8", "doc_type_checks", "compliance_rules"):
        checks_list = data.get(section_key)
        if not isinstance(checks_list, list):
            continue
        for check in checks_list:
            if not isinstance(check, dict):
                continue
            rec = _parse_single_check(
                check,
                filepath,
                source_type=f"doc_type/{section_key}",
            )
            if rec:
                results.append(rec)

    return results


# ── Классификация ─────────────────────────────────────────────────────────────

def classify_check(rec: dict) -> None:
    """Добавить вычисленные поля и статус. Мутирует rec."""
    recommended = compute_recommended_extraction_tokens(rec["fields"])
    current     = rec["extraction_max_tokens"] or _ENV_DEFAULT_EXTRACTION_TOKENS

    rec["_recommended"] = recommended
    rec["_current"]     = current
    rec["_deficit"]     = recommended - current
    rec["_from_env"]    = rec["extraction_max_tokens"] is None

    if current < recommended:
        rec["_status"] = "critical"
    elif current < _round_up(int(recommended * 1.10)):
        rec["_status"] = "warning"
    else:
        rec["_status"] = "ok"


# ── Форматирование ────────────────────────────────────────────────────────────

_W   = 110
_SEP = "─" * _W


def _rel(filepath: str) -> str:
    return filepath.replace("/srv/steloom-dev/", "")


def _source_tag(rec: dict) -> str:
    return " [дефолт .env]" if rec.get("_from_env") else ""


def _print_table_header() -> None:
    print(f"  {'check_id':<42} {'полей':>5} {'тек.':>6} {'рек.':>6} {'δ':>7}  файл")
    print(_SEP)


def _print_row(rec: dict, show_delta_sign: str = "+") -> None:
    delta = abs(rec["_deficit"])
    if rec["_status"] == "critical":
        sign = "+"   # дефицит — нужно добавить
    else:
        delta = rec["_current"] - rec["_recommended"]
        sign  = "+"

    print(
        f"  {rec['check_id']:<42} {rec['fields_count']:>5}"
        f" {rec['_current']:>6} {rec['_recommended']:>6}"
        f" {sign}{rec['_deficit'] if rec['_status'] == 'critical' else delta:>6}"
        f"  {_rel(rec['file'])}{_source_tag(rec)}"
    )


def _print_patch(rec: dict) -> None:
    print(f"\n  Файл : {_rel(rec['file'])}")
    print(f"  Чек  : {rec['check_id']}")
    print(f"  Патч : в секции extraction добавьте/замените:")
    print(f"           llm_max_tokens: {rec['_recommended']}")
    if rec.get("has_custom_prompt") and rec.get("compact_output", True):
        print(f"           compact_output: false"
              f"   # есть custom prompt — generic footer конфликтует")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    scan_dirs = [
        "/srv/steloom-dev/playbooks/global_checks",
        "/srv/steloom-dev/playbooks/document_types",
    ]

    all_records: list[dict] = []
    errors: list[dict]      = []
    yaml_files_scanned      = 0

    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            print(f"⚠️  Директория не найдена: {scan_dir}")
            continue
        for filepath in sorted(
            glob.glob(os.path.join(scan_dir, "**/*.yaml"), recursive=True)
        ):
            yaml_files_scanned += 1
            for rec in extract_checks_from_yaml(filepath):
                if "_error" in rec:
                    errors.append(rec)
                else:
                    classify_check(rec)
                    all_records.append(rec)

    critical         = [r for r in all_records if r["_status"] == "critical"]
    warning          = [r for r in all_records if r["_status"] == "warning"]
    ok_list          = [r for r in all_records if r["_status"] == "ok"]
    # Конфликт compact_output: только если YAML явно задаёт compact_output=true
    # при наличии custom prompt. После перехода на tri-state policy
    # отсутствие поля = авто-режим = не конфликт.
    compact_conflicts = [
        r for r in all_records
        if r.get("has_custom_prompt")
        and r.get("compact_output") is True   # только явный True, не None
    ]
    detection_low    = [
        r for r in all_records
        if r.get("detection_max_tokens") is not None
        and r["detection_max_tokens"] < 256
    ]

    # ── шапка ────────────────────────────────────────────────────────────────
    print()
    print("=" * _W)
    print("  АУДИТ EXTRACTION TOKEN BUDGET — Steloom Legal Platform")
    print(
        f"  .env: LLM_EXTRACTION_MAX_TOKENS={_ENV_DEFAULT_EXTRACTION_TOKENS}"
        f"  |  LLM_MAX_TOKENS(detection)={_ENV_DEFAULT_DETECTION_TOKENS}"
    )
    print(
        f"  Просканировано YAML: {yaml_files_scanned}"
        f"  |  Extraction-чеков: {len(all_records)}"
        f"  |  Ошибок парсинга: {len(errors)}"
    )
    print("=" * _W)

    # ── 1. КРИТИЧНО ───────────────────────────────────────────────────────────
    if critical:
        print()
        print(f"🔴  КРИТИЧНО — вывод будет обрезан ({len(critical)} чеков)")
        print("    текущий llm_max_tokens < рекомендованного минимума")
        print(_SEP)
        _print_table_header()
        for r in sorted(critical, key=lambda x: -x["_deficit"]):
            _print_row(r)
        print()
        print("  ── КОНКРЕТНЫЕ ПАТЧИ ─────────────────────────────────────────────────")
        for r in sorted(critical, key=lambda x: x["file"]):
            _print_patch(r)
        print()

    # ── 2. НА ГРАНИ ───────────────────────────────────────────────────────────
    if warning:
        print()
        print(f"🟡  НА ГРАНИ — может обрезать при длинных значениях ({len(warning)} чеков)")
        print(_SEP)
        _print_table_header()
        for r in sorted(warning, key=lambda x: x["_deficit"], reverse=True):
            _print_row(r)
        print()

    # ── 3. OK ─────────────────────────────────────────────────────────────────
    if ok_list:
        print()
        print(f"✅  OK — бюджет достаточен ({len(ok_list)} чеков)")
        print(_SEP)
        _print_table_header()
        for r in sorted(ok_list, key=lambda x: x["check_id"]):
            _print_row(r)
        print()

    # ── 4. compact_output конфликты ───────────────────────────────────────────
    if compact_conflicts:
        print()
        print(f"⚠️   КОНФЛИКТ compact_output ({len(compact_conflicts)} чеков)")
        print("    Custom llm_prompt_extraction + compact_output=true (дефолт).")
        print("    Generic footer 'пиши кратко' противоречит детальному промпту.")
        print("    Патч: добавить  compact_output: false  в секцию extraction.")
        print(_SEP)
        for r in compact_conflicts:
            print(
                f"  {r['check_id']:<44}"
                f"  extraction={r['_current']:>4} tok"
                f"  {_rel(r['file'])}"
            )
        print()

    # ── 5. Detection-фаза: низкий llm.max_tokens ─────────────────────────────
    if detection_low:
        print()
        print(f"⚠️   DETECTION llm.max_tokens < 256 ({len(detection_low)} чеков)")
        print("    Рекомендованный минимум для detection: 256-640 токенов.")
        print(_SEP)
        for r in detection_low:
            print(
                f"  {r['check_id']:<44}"
                f"  detection={r['detection_max_tokens']:>4} tok"
                f"  {_rel(r['file'])}"
            )
        print()

    # ── 6. Ошибки парсинга ───────────────────────────────────────────────────
    if errors:
        print()
        print(f"❌  ОШИБКИ ПАРСИНГА YAML ({len(errors)})")
        print(_SEP)
        for e in errors:
            print(f"  {e['_file']}: {e['_error']}")
        print()

    # ── сводка ───────────────────────────────────────────────────────────────
    print("=" * _W)
    print(
        f"  ИТОГО:  🔴 {len(critical)} критичных"
        f"  |  🟡 {len(warning)} на грани"
        f"  |  ✅ {len(ok_list)} OK"
        f"  |  ⚠️  {len(compact_conflicts)} конфликтов compact_output"
        f"  |  ❌ {len(errors)} ошибок парсинга"
    )
    print("=" * _W)
    print()

    if critical:
        sys.exit(1)


if __name__ == "__main__":
    main()
