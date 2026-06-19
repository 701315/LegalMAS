#!/usr/bin/env python3
"""
DD Grid Output Validator (supports wrapped structured_data payloads)

Usage:
    python3 scripts/validate_dd_grid_output.py \
      --document-id 79095553-b6bd-43f7-9cea-16a1e285601e

Optional:
    --verbose
    --output json
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://mas:mas_dev_password@localhost:5432/mas_dd"
).replace("postgresql+asyncpg://", "postgresql://")

FORBIDDEN_VALUES = {
    "", "None", "null", "NULL", "undefined", "not_specified", "N/A", "n/a"
}


# ══════════════════════════════════════════════════════════════════════════════
# ARGS
# ══════════════════════════════════════════════════════════════════════════════

def get_args():
    p = argparse.ArgumentParser(description="DD Grid Output Validator")
    p.add_argument("--document-id", required=True)
    p.add_argument("--verbose", action="store_true", default=False)
    p.add_argument("--output", choices=["console", "json"], default="console")
    return p.parse_args()


# ══════════════════════════════════════════════════════════════════════════════
# DB LOAD
# ══════════════════════════════════════════════════════════════════════════════

def load_check_results(document_id: str) -> list[dict]:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("[ERROR] psycopg2-binary не установлен", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            id,
            run_id,
            document_id,
            check_id,
            check_name,
            result,
            severity,
            value_text,
            evidence_ref,
            confidence,
            detector_used,
            quality_flags,
            qc_status,
            qc_by,
            qc_comment,
            qc_at,
            structured_data,
            conditional_check_triggered,
            trigger_name,
            origin,
            execution_status,
            error_details,
            segment_id,
            segment_type,
            segment_title,
            segment_order,
            is_primary_segment,
            chunk_id,
            chunk_index,
            ui_mode,
            display_text,
            machine_reason_code,
            review_status,
            review_message,
            needs_manual_review,
            created_at,
            updated_at
        FROM check_results
        WHERE document_id = %s
        ORDER BY check_id, id
    """, (document_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# PLAYBOOK SCHEMA LOAD
# ══════════════════════════════════════════════════════════════════════════════

def load_playbook_fields_by_check_ids(check_ids: set[str]) -> dict[str, dict]:
    try:
        import yaml
    except ImportError:
        print("[WARN] PyYAML не установлен — schema checks ограничены", file=sys.stderr)
        return {}

    result: dict[str, dict] = {}

    search_dirs = [
        PROJECT_ROOT / "playbooks" / "document_types",
        PROJECT_ROOT / "playbooks" / "global_checks",
    ]

    for base in search_dirs:
        for ypath in base.rglob("*.yaml"):
            try:
                with open(ypath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception:
                continue

            if not data:
                continue

            for check in data.get("checks_v8", []) or []:
                cid = check.get("id")
                if cid in check_ids:
                    fields = ((check.get("extraction") or {}).get("fields")) or []
                    result[cid] = {f["name"]: f for f in fields if isinstance(f, dict)}

    return result


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

class Issue:
    def __init__(self, level: str, check_id: str, field: str,
                 message: str, value: Any = None):
        self.level = level
        self.check_id = check_id
        self.field = field
        self.message = message
        self.value = value


def normalize_execution_status(status: Any) -> str:
    if status is None:
        return "unknown"
    s = str(status).strip().lower()
    if s in {"success", "completed"}:
        return "completed"
    if s in {"error", "failed"}:
        return "error"
    if s in {"skipped"}:
        return "skipped"
    return s


def unwrap_payload(raw_value: Any) -> tuple[Any, bool | None, dict | None]:
    """
    Возвращает:
      scalar_value,
      field_found,
      original_payload_or_none
    """
    if isinstance(raw_value, dict) and "value" in raw_value:
        return raw_value.get("value"), raw_value.get("found"), raw_value
    return raw_value, None, None


def row_is_positive(row: dict) -> bool:
    """
    Определяем, что check реально что-то извлёк / нашёл.
    """
    # 1. display_text есть
    if row.get("display_text") and str(row["display_text"]).strip() not in FORBIDDEN_VALUES:
        return True

    # 2. structured_data содержит хотя бы одно поле с found=True и meaningful value
    sd = row.get("structured_data") or {}
    for _, raw in sd.items():
        val, found, _payload = unwrap_payload(raw)
        if found is True:
            if val is None:
                continue
            sval = str(val).strip()
            if sval not in FORBIDDEN_VALUES:
                return True

    # 3. fallback по result
    rv = str(row.get("result") or "").strip().lower()
    return rv in {"pass", "positive", "found", "defined", "present", "matched"}


def looks_like_fact_field(field_name: str, schema_meta: dict) -> bool:
    pres = schema_meta.get("presentation")
    if pres == "fact":
        return True
    return field_name.endswith((
        "_details", "_amount", "_date", "_deadline", "_name", "_description",
        "_signatory", "_address", "_value", "_text"
    ))


def scalar_to_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def validate_result(row: dict, schema_fields: dict, verbose: bool = False) -> list[Issue]:
    issues = []

    check_id = row.get("check_id", "unknown")
    execution_status = normalize_execution_status(row.get("execution_status"))
    positive = row_is_positive(row)
    structured_data = row.get("structured_data") or {}
    display_text = row.get("display_text")
    confidence = row.get("confidence")

    # 1. execution status
    if execution_status == "error":
        issues.append(Issue(
            "ERROR", check_id, "_execution",
            f"execution_status=error, error_details={row.get('error_details')}"
        ))
        return issues

    # 2. confidence range
    if confidence is not None:
        try:
            c = float(confidence)
            if c < 0 or c > 1:
                issues.append(Issue(
                    "WARNING", check_id, "confidence",
                    "confidence вне диапазона [0,1]",
                    confidence
                ))
        except Exception:
            issues.append(Issue(
                "WARNING", check_id, "confidence",
                "confidence не приводится к float",
                confidence
            ))

    # 3. display_text
    if positive:
        if display_text is None or scalar_to_str(display_text) in FORBIDDEN_VALUES:
            issues.append(Issue(
                "WARNING", check_id, "display_text",
                "У check есть данные, но display_text пуст/запрещён",
                display_text
            ))

    # 4. structured_data
    if not structured_data:
        if positive:
            issues.append(Issue(
                "WARNING", check_id, "structured_data",
                "Есть положительный результат, но structured_data пуст"
            ))
        return issues

    # 5. validate fields
    for field_name, raw_value in structured_data.items():
        scalar_value, field_found, payload = unwrap_payload(raw_value)

        schema_meta = schema_fields.get(field_name, {})
        presentation = schema_meta.get("presentation", "unknown")
        allowed_values = schema_meta.get("allowed_values", [])
        label = schema_meta.get("label")

        sval = scalar_to_str(scalar_value)

        # 5.1 Поле не найдено extraction-ом — это нормально
        if field_found is False:
            continue

        # 5.2 None допустимо только если field_found=False (это уже выше)
        if scalar_value is None:
            issues.append(Issue(
                "WARNING", check_id, field_name,
                "field_found=True, но value=None",
                raw_value
            ))
            continue

        # 5.3 Forbidden values
        if sval in FORBIDDEN_VALUES:
            issues.append(Issue(
                "ERROR", check_id, field_name,
                "Запрещённое значение", raw_value
            ))
            continue

        # 5.4 signal enum
        if presentation == "signal" and allowed_values:
            if sval not in allowed_values:
                issues.append(Issue(
                    "ERROR", check_id, field_name,
                    f"Значение '{sval}' не из allowed_values={allowed_values}",
                    raw_value
                ))

        # 5.5 fact must have label
        if looks_like_fact_field(field_name, schema_meta):
            if not label:
                issues.append(Issue(
                    "WARNING", check_id, field_name,
                    "fact-поле без label в playbook schema"
                ))

            if positive and sval in {"Данные не определены", "not_defined", "not_found"}:
                issues.append(Issue(
                    "WARNING", check_id, field_name,
                    "fact-поле осталось неопределённым при положительном результате",
                    raw_value
                ))

        # 5.6 summary forbidden
        if presentation == "summary":
            issues.append(Issue(
                "ERROR", check_id, field_name,
                "presentation='summary' запрещён"
            ))

        # 5.7 extra fields
        if presentation == "unknown" and schema_fields:
            issues.append(Issue(
                "WARNING", check_id, field_name,
                "Поле отсутствует в schema playbook",
                raw_value
            ))

    # 6. schema fields missing in SD
    if positive and schema_fields:
        for fname in schema_fields:
            if fname not in structured_data:
                issues.append(Issue(
                    "WARNING", check_id, fname,
                    "Поле есть в schema, но отсутствует в structured_data"
                ))

    return issues


def validate_dataset(rows: list[dict], schema_by_check: dict, verbose: bool = False) -> list[Issue]:
    issues = []

    seen_ids = set()
    for row in rows:
        cid = row.get("check_id", "unknown")
        rid = row.get("id")
        if rid in seen_ids:
            issues.append(Issue("WARNING", cid, "_meta", "Дубликат id", rid))
        seen_ids.add(rid)

        schema_fields = schema_by_check.get(cid, {})
        issues.extend(validate_result(row, schema_fields, verbose))

    return issues


# ══════════════════════════════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════════════════════════════

def compute_stats(rows: list[dict], issues: list[Issue]) -> dict:
    total_checks = len(rows)
    found_checks = sum(1 for r in rows if row_is_positive(r))
    completed_checks = sum(1 for r in rows if normalize_execution_status(r.get("execution_status")) == "completed")
    error_checks = sum(1 for r in rows if normalize_execution_status(r.get("execution_status")) == "error")
    with_sd = sum(1 for r in rows if r.get("structured_data"))
    with_display = sum(1 for r in rows if r.get("display_text"))

    total_fields = 0
    for r in rows:
        sd = r.get("structured_data") or {}
        total_fields += len(sd)

    errors = [i for i in issues if i.level == "ERROR"]
    warnings = [i for i in issues if i.level == "WARNING"]

    health_score = round(
        100 * (1 - (len(errors) / max(total_fields + total_checks, 1))), 1
    )

    return {
        "total_checks": total_checks,
        "found_checks": found_checks,
        "completed_checks": completed_checks,
        "error_checks": error_checks,
        "checks_with_structured_data": with_sd,
        "checks_with_display_text": with_display,
        "total_fields_extracted": total_fields,
        "errors": len(errors),
        "warnings": len(warnings),
        "health_score": health_score,
    }


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

def print_console_report(document_id: str, rows: list[dict], issues: list[Issue],
                         stats: dict, verbose: bool):
    sep = "═" * 72
    print(sep)
    print("  DD Grid Output Validator")
    print(f"  Document ID : {document_id}")
    print(sep)

    print("\nСтатистика:")
    for k, v in stats.items():
        print(f"  {k:<28}: {v}")

    if issues:
        print("\nПроблемы:")
        grouped = {}
        for i in issues:
            grouped.setdefault(i.check_id, []).append(i)

        for check_id, group in sorted(grouped.items()):
            print(f"\n  [{check_id}]")
            for i in group:
                val = f"  → {repr(i.value)}" if i.value is not None else ""
                print(f"    {i.level:<7} {i.field}: {i.message}{val}")
    else:
        print("\nПроблем не обнаружено.")

    if verbose:
        print("\nДетали structured_data:")
        for row in rows:
            cid = row.get("check_id")
            positive = row_is_positive(row)
            print(f"\n  check_id={cid} positive={positive} execution_status={row.get('execution_status')}")
            print(f"    result      = {row.get('result')}")
            print(f"    display_text= {repr(row.get('display_text'))}")
            print(f"    value_text  = {repr(row.get('value_text'))}")
            sd = row.get("structured_data") or {}
            if sd:
                for k, raw in sd.items():
                    scalar, field_found, payload = unwrap_payload(raw)
                    print(f"    {k:<40} = value={repr(scalar)} found={field_found}")
            else:
                print("    (structured_data пуст)")

    print(f"\nИТОГ: {'OK' if stats['errors'] == 0 else 'FAILED'} | Health={stats['health_score']}%")


def print_json_report(document_id: str, issues: list[Issue], stats: dict):
    payload = {
        "document_id": document_id,
        "stats": stats,
        "issues": [
            {
                "level": i.level,
                "check_id": i.check_id,
                "field": i.field,
                "message": i.message,
                "value": i.value,
            }
            for i in issues
        ]
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    args = get_args()

    print("Загружаем check_results из PostgreSQL ...", file=sys.stderr)
    rows = load_check_results(args.document_id)

    if not rows:
        print(f"[ERROR] Нет check_results для document_id={args.document_id}", file=sys.stderr)
        sys.exit(1)

    print(f"Загружено {len(rows)} записей", file=sys.stderr)

    check_ids = {r["check_id"] for r in rows if r.get("check_id")}
    schema_by_check = load_playbook_fields_by_check_ids(check_ids)

    issues = validate_dataset(rows, schema_by_check, verbose=args.verbose)
    stats = compute_stats(rows, issues)

    if args.output == "json":
        print_json_report(args.document_id, issues, stats)
    else:
        print_console_report(args.document_id, rows, issues, stats, args.verbose)

    sys.exit(1 if stats["errors"] > 0 else 0)


if __name__ == "__main__":
    main()


