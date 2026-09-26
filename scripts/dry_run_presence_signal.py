"""
Dry-run симуляция: как правка loader.py + правки YAML повлияют на 5 checks
в playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml.

Read-only. Ничего не пишет в ФС. Ничего не запускает в БД.
Не вызывает LLM.

Запуск:
    cd /srv/steloom-dev
    source .venv/bin/activate
    export PYTHONPATH=src:.
    python scripts/dry_run_presence_signal.py
"""

import copy
from pathlib import Path
from typing import Any

import yaml

from engine.playbook.models import (
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
    ExtractionMode,
    PresenceSignalConfig,
)


YAML_PATH = Path(
    "playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml"
)

TARGET_IDS = [
    "parties_and_authority",
    "subject_quantity_price",
    "payment_terms",
    "delivery_and_transfer_docs",
    "title_risk_retention",
]

RESULT_TO_DDGRID = {
    "pass": "зелёная строка + LOCATION",
    "missing_required_clause": '"clause_missing", LOCATION = "—"',
    "unclear": '"clause_unclear", LOCATION = "—"',
}


# ─── 1. Загрузка YAML ────────────────────────────────────────────────

def load_yaml() -> dict:
    with YAML_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─── 2. Симуляция YAML-правок (в памяти) ────────────────────────────

def add_presence_signal(raw_check: dict) -> dict:
    """
    Возвращает deepcopy check'а, в котором:
    - в extraction.fields добавлено поле <id>_presence (первым);
    - в extraction добавлен presence_signal.
    """
    check = copy.deepcopy(raw_check)
    check_id = check["id"]
    ext = check.setdefault("extraction", {})
    fields = ext.setdefault("fields", [])

    presence_field = {
        "name": f"{check_id}_presence",
        "type": "string",
        "presentation": "signal",
        "risk_weight": "info",
        "allowed_values": ["present", "missing", "unclear"],
        "display_in_grid": False,
        "description": "Наличие регулирования по теме check'а. Внутреннее агрегатное signal-поле.",
        "required": True,
    }
    fields.insert(0, presence_field)

    ext["presence_signal"] = {
        "field": f"{check_id}_presence",
        "present_values": ["present"],
        "missing_values": ["missing"],
        "unclear_values": ["unclear"],
    }
    return check


# ─── 3. Симуляция loader'а: до и после патча ────────────────────────

def _build_fields(extraction_cfg: dict) -> list[ExtractionFieldConfig]:
    fields = []
    for f in extraction_cfg.get("fields") or []:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        if not name:
            continue
        try:
            field_type = ExtractionFieldType(f.get("type", "string"))
        except ValueError:
            field_type = ExtractionFieldType.STRING
        fields.append(
            ExtractionFieldConfig(
                name=name,
                type=field_type,
                label=f.get("label"),
                label_en=f.get("label_en"),
                presentation=f.get("presentation", "fact"),
                display_in_grid=bool(f.get("display_in_grid", False)),
                display_priority=f.get("display_priority"),
                risk_weight=f.get("risk_weight"),
                description=f.get("description", ""),
                regex_patterns=f.get("regex_patterns") or [],
                keyword_hints=f.get("keyword_hints") or [],
                allowed_values=f.get("allowed_values") or [],
                unit=f.get("unit"),
                required=f.get("required", False),
                max_value_chars=f.get("max_value_chars"),
                role=f.get("role"),
            )
        )
    return fields


def parse_extraction_current(extraction_cfg: dict | None) -> ExtractionConfig | None:
    """Текущая реализация _parse_extraction. presence_signal НЕ пробрасывается."""
    if not extraction_cfg or not extraction_cfg.get("enabled"):
        return None

    try:
        mode = ExtractionMode(extraction_cfg.get("mode", "rules"))
    except ValueError:
        mode = ExtractionMode.RULES

    fields = _build_fields(extraction_cfg)
    if not fields:
        return None

    _raw_compact = extraction_cfg.get("compact_output")
    _compact_output = None if _raw_compact is None else bool(_raw_compact)

    return ExtractionConfig(
        enabled=True,
        mode=mode,
        fields=fields,
        store_payload=extraction_cfg.get("store_payload", True),
        llm_prompt_extraction=extraction_cfg.get("llm_prompt_extraction"),
        llm_max_tokens=extraction_cfg.get("llm_max_tokens"),
        compact_output=_compact_output,
        dd_grid_columns=extraction_cfg.get("dd_grid_columns"),
        # presence_signal не передаётся — текущее поведение
    )


def parse_extraction_patched(extraction_cfg: dict | None) -> ExtractionConfig | None:
    """Симуляция после патча: + одна строка presence_signal."""
    if not extraction_cfg or not extraction_cfg.get("enabled"):
        return None

    try:
        mode = ExtractionMode(extraction_cfg.get("mode", "rules"))
    except ValueError:
        mode = ExtractionMode.RULES

    fields = _build_fields(extraction_cfg)
    if not fields:
        return None

    _raw_compact = extraction_cfg.get("compact_output")
    _compact_output = None if _raw_compact is None else bool(_raw_compact)

    return ExtractionConfig(
        enabled=True,
        mode=mode,
        fields=fields,
        store_payload=extraction_cfg.get("store_payload", True),
        llm_prompt_extraction=extraction_cfg.get("llm_prompt_extraction"),
        llm_max_tokens=extraction_cfg.get("llm_max_tokens"),
        compact_output=_compact_output,
        dd_grid_columns=extraction_cfg.get("dd_grid_columns"),
        presence_signal=extraction_cfg.get("presence_signal"),  # ← ПАТЧ
    )


# ─── 4. Симуляция executor'а ────────────────────────────────────────

def classify_presence_signal(
    structured_data: dict | None, signal: PresenceSignalConfig
) -> str:
    """Копия CheckExecutor._classify_presence_signal."""
    if not isinstance(structured_data, dict):
        return "not_extracted"
    payload = structured_data.get(signal.field)
    if not isinstance(payload, dict):
        return "not_extracted"
    if not payload.get("found"):
        return "not_extracted"
    return signal.classify(payload.get("value"))


def build_structured_data(
    cfg: ExtractionConfig, llm_response: dict[str, Any]
) -> dict[str, Any]:
    """Собираем structured_data так, как это делал бы ExtractionExecutor."""
    sd: dict[str, Any] = {}
    for f in cfg.fields:
        value = llm_response.get(f.name)
        found = value is not None
        sd[f.name] = {
            "value": value if found else None,
            "found": found,
            "confidence": 0.9 if found else 0.0,
            "location": None,
        }
    return sd


def _has_meaningful_extraction_simple(
    cfg: ExtractionConfig, structured_data: dict
) -> bool:
    """
    Упрощённая симуляция _has_meaningful_extraction:
    meaningful = хотя бы одно поле с непустым value и found=True.
    (Реальная логика сложнее — через iter_meaningful_fields,
    но для демонстрации достаточно.)
    """
    for f in cfg.fields:
        p = structured_data.get(f.name)
        if not p or not p.get("found"):
            continue
        val = p.get("value")
        if val is None or str(val).strip() in ("", "not_defined"):
            continue
        return True
    return False


def simulate_executor(
    cfg: ExtractionConfig, llm_response: dict[str, Any]
) -> dict[str, str]:
    """Симулирует business-result mapping (executor.py:1438–1555)."""
    sd = build_structured_data(cfg, llm_response)
    ps = getattr(cfg, "presence_signal", None)

    if ps is not None:
        verdict = classify_presence_signal(sd, ps)
        if verdict == "present":
            result = "pass"
        elif verdict == "missing":
            result = "missing_required_clause"
        elif verdict == "unclear":
            result = "unclear"
        else:  # undeclared / not_extracted
            result = "unclear"
        return {"path": "presence_signal_gate", "verdict": verdict, "result": result}

    meaningful = _has_meaningful_extraction_simple(cfg, sd)
    return {
        "path": "_has_meaningful_extraction",
        "verdict": "n/a",
        "result": "pass" if meaningful else "unclear",
    }


# ─── 5. Сценарии LLM-ответов ────────────────────────────────────────

def build_scenarios(cfg: ExtractionConfig) -> list[tuple[str, dict[str, Any]]]:
    ps = cfg.presence_signal
    if ps is None:
        return [("без presence_signal — сценарии не применимы", {})]

    content_fields = [f.name for f in cfg.fields if f.name != ps.field]
    status_field = next((n for n in content_fields if n.endswith("_status")), None)
    value_field = next(
        (n for n in content_fields if n.endswith("_value") or n.endswith("_details")),
        None,
    )

    present_resp: dict[str, Any] = {ps.field: "present"}
    if status_field:
        present_resp[status_field] = "defined"
    if value_field:
        present_resp[value_field] = "Пример значения"

    return [
        ("LLM вернул present (тема есть, данные извлечены)", present_resp),
        ("LLM вернул missing (темы нет в документе)", {ps.field: "missing"}),
        ("LLM вернул unclear (фрагменты противоречивы)", {ps.field: "unclear"}),
    ]


# ─── 6. Main ─────────────────────────────────────────────────────────

def main() -> None:
    if not YAML_PATH.exists():
        print(f"[!] Не найден {YAML_PATH.resolve()}")
        return

    raw = load_yaml()
    checks_by_id = {c["id"]: c for c in raw.get("checks_v8", [])}

    print("=" * 100)
    print("DRY-RUN: как правка loader.py и YAML повлияют на 5 checks")
    print("=" * 100)
    print(f"Файл: {YAML_PATH}")
    print(f"Всего checks в файле: {len(checks_by_id)}")
    print(f"Наши targets: {len(TARGET_IDS)}")
    print()

    for check_id in TARGET_IDS:
        if check_id not in checks_by_id:
            print(f"[!] {check_id}: НЕ найден в YAML — пропускаем")
            continue

        raw_check = checks_by_id[check_id]
        raw_check_patched = add_presence_signal(raw_check)

        ext_current = raw_check.get("extraction", {}) or {}
        ext_patched = raw_check_patched.get("extraction", {}) or {}

        print("─" * 100)
        print(f"CHECK: {check_id}")
        print("─" * 100)

        # A. Сегодня
        print()
        print("【A. СЕГОДНЯ: текущий код + текущий YAML】")
        cfg_a = parse_extraction_current(ext_current)
        if cfg_a is None:
            print("  extraction.enabled=False или fields пусты → check не работает.")
            continue
        print(f"  presence_signal: {cfg_a.presence_signal}")
        print(f"  → gate НЕ сработает, fallback _has_meaningful_extraction")

        # B. Патч кода, без правки YAML
        print()
        print("【B. ПОСЛЕ ПАТЧА loader.py, БЕЗ правки YAML】")
        cfg_b = parse_extraction_patched(ext_current)
        print(f"  presence_signal: {cfg_b.presence_signal}")
        print(f"  → поведение идентично A (presence_signal=None в YAML)")

        # C. Патч кода + правка YAML
        print()
        print("【C. ПОСЛЕ ПАТЧА loader.py + ПРАВКИ YAML】")
        try:
            cfg_c = parse_extraction_patched(ext_patched)
        except Exception as exc:
            print(f"  [ОШИБКА ВАЛИДАЦИИ] {type(exc).__name__}: {exc}")
            continue

        ps = cfg_c.presence_signal
        print(f"  presence_signal: field={ps.field}")
        print(f"                   present_values={ps.present_values}")
        print(f"                   missing_values={ps.missing_values}")
        print(f"                   unclear_values={ps.unclear_values}")

        new_field = next((f for f in cfg_c.fields if f.name == ps.field), None)
        if new_field:
            print(
                f"  Новое поле в fields: {new_field.name} "
                f"(presentation={new_field.presentation}, "
                f"risk_weight={new_field.risk_weight}, "
                f"allowed_values={new_field.allowed_values})"
            )
        print()

        # Симуляция сценариев
        print("  Симуляция бизнес-результата для 3 сценариев LLM:")
        print()
        for i, (desc, llm_resp) in enumerate(build_scenarios(cfg_c), 1):
            print(f"  Сценарий {i}: {desc}")
            print(f"    LLM вернул: {llm_resp}")
            out = simulate_executor(cfg_c, llm_resp)
            print(f"    путь:  {out['path']}")
            if out["verdict"] != "n/a":
                print(f"    gate:  {out['verdict']}")
            print(f"    result: {out['result']}")
            print(f"    DD Grid: {RESULT_TO_DDGRID.get(out['result'], '?')}")
            print()

    print("=" * 100)
    print("ИТОГ")
    print("=" * 100)
    print(
        """
СЕГОДНЯ (A):
  Для doc-type field_extraction checks gate НЕ срабатывает.
  Пользователь видит только: pass | unclear.
  Состояние "missing" в DD Grid недостижимо.

ПОСЛЕ ПАТЧА loader.py + ПРАВОК YAML (C):
  gate работает.
  Пользователь видит: pass | missing_required_clause | unclear.
  Принцип "missing visible in DD Grid" реализован для doc-type checks.
"""
    )


if __name__ == "__main__":
    main()

    