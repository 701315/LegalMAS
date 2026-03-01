# scripts/generate_trigger_types.py

import re
from pathlib import Path
from typing import Set, Dict, Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
DOCUMENT_TYPES_DIR = ROOT / "playbooks" / "document_types"
OUTPUT_PATH = ROOT / "src" / "core" / "generated_trigger_types.py"


def extract_trigger_defs(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Извлекает словарь trigger_definitions из структуры YAML.
    Сейчас триггеры лежат внутри classification_runtime_v1.trigger_definitions.
    """
    if not isinstance(data, dict):
        return {}

    runtime = data.get("classification_runtime_v1") or {}
    if not isinstance(runtime, dict):
        return {}

    trigger_defs = runtime.get("trigger_definitions") or {}
    if not isinstance(trigger_defs, dict):
        return {}

    return trigger_defs


def collect_trigger_keys() -> Set[str]:
    keys: Set[str] = set()

    if not DOCUMENT_TYPES_DIR.exists():
        raise SystemExit(f"Directory not found: {DOCUMENT_TYPES_DIR}")

    for path in DOCUMENT_TYPES_DIR.rglob("*.yaml"):
        with path.open("r", encoding="utf-8") as f:
            try:
                data = yaml.safe_load(f) or {}
            except Exception as e:
                raise SystemExit(f"Failed to load YAML {path}: {e}")

        trigger_defs = extract_trigger_defs(data)
        for key in trigger_defs.keys():
            if isinstance(key, str) and key.strip():
                keys.add(key.strip())

    return keys


def to_enum_name(value: str) -> str:
    """
    Преобразует строковое значение триггера в имя enum-члена:
    "land_plot_sale" -> "LAND_PLOT_SALE",
    "foreign-buyer_keywords" -> "FOREIGN_BUYER_KEYWORDS".
    """
    name = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_")
    return name.upper()


def render_enum(keys: Set[str]) -> str:
    lines = []
    lines.append("from enum import Enum")
    lines.append("")
    lines.append("")
    lines.append("class TriggerType(str, Enum):")
    lines.append('    """Автоматически сгенерированный список триггеров из YAML trigger_definitions."""')
    lines.append("")

    for key in sorted(keys):
        enum_name = to_enum_name(key)
        lines.append(f'    {enum_name} = "{key}"')

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    keys = collect_trigger_keys()
    if not keys:
        raise SystemExit("No trigger_definitions found in YAML document types.")

    code = render_enum(keys)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(code, encoding="utf-8")
    print(f"Written TriggerType enum to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
