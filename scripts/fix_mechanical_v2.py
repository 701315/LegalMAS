#!/usr/bin/env python3
"""Механическое исправление форматирования v3. 
Использует ruamel.yaml для сохранения форматирования."""
import argparse, re, sys
from pathlib import Path

try:
    from ruamel.yaml import YAML
except ImportError:
    print("ERROR: ruamel.yaml не установлен. Установите: pip install ruamel.yaml", file=sys.stderr)
    sys.exit(1)

FINAL_LINE = "Технический формат JSON (value / confidence / location) задан отдельным контрактом — соблюдай его, но не описывай здесь."
TYPO = ".без markdown."


def fix_check_text(raw_text: str) -> tuple[str, list[str]]:
    """Исправляет опечатки в сыром тексте YAML (до парсинга)."""
    changes = []
    if TYPO in raw_text:
        raw_text = raw_text.replace(TYPO, "")
        changes.append(f"FIX X2: удалена опечатка '{TYPO}'")
    return raw_text, changes


def fix_check_structured(check: dict) -> list[str]:
    """Исправляет структурные проблемы в распарсенном check."""
    changes = []
    ex = check.get("extraction", {})
    
    # 1. Исправление display_priority (FAIL:D4)
    fields = ex.get("fields", [])
    grid_fields = [f for f in fields if f.get("display_in_grid") is True]
    if grid_fields:
        expected_priorities = list(range(1, len(grid_fields) + 1))
        actual_priorities = [f.get("display_priority") for f in grid_fields]
        if actual_priorities != expected_priorities:
            for i, f in enumerate(grid_fields):
                f["display_priority"] = i + 1
            changes.append(f"FIX D4: display_priority пересчитан на {expected_priorities}")

    # 2. Исправление финальной строки в output_expectations (FAIL:L4)
    l2 = ex.get("llm_prompt_extraction", "")
    if "<output_expectations>" in l2 and "</output_expectations>" in l2:
        if FINAL_LINE.strip() not in l2:
            l2_new = re.sub(
                r"(</output_expectations>)",
                f"- {FINAL_LINE}\n\\1",
                l2
            )
            if l2_new != l2:
                ex["llm_prompt_extraction"] = l2_new
                changes.append("FIX L4: добавлена финальная строка в output_expectations")

    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="playbooks/document_types")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.allow_duplicate_keys = True  # <-- ИГНОРИРУЕМ ДУБЛИКАТЫ КЛЮЧЕЙ В YAML

    files = sorted(Path(a.root).rglob("*.yaml"))
    total_changes = 0
    files_to_modify = 0

    for p in files:
        raw = p.read_text(encoding="utf-8")
        
        new_raw, text_changes = fix_check_text(raw)
        
        try:
            doc = yaml.load(new_raw)
        except Exception as e:
            print(f"[ERR] {p}: {e}", file=sys.stderr)
            continue

        checks = doc.get("checks_v8") or doc.get("checks") or []
        if not checks:
            continue

        file_changed = bool(text_changes)
        all_changes = list(text_changes)
        
        for i, c in enumerate(checks):
            changes = fix_check_structured(c)
            if changes:
                file_changed = True
                all_changes.extend(changes)
                if not a.dry_run:
                    checks[i] = c

        if file_changed:
            files_to_modify += 1
            total_changes += len(all_changes)
            print(f"\n[{p}]")
            for ch in all_changes:
                print(f"  -> {ch}")
            
            if not a.dry_run:
                with open(p, "w", encoding="utf-8") as f:
                    yaml.dump(doc, f)
                print(f"[OK] Записано: {p}")

    print("\n" + "="*60)
    if a.dry_run:
        print(f"РЕЖИМ DRY-RUN. Изменений не внесено.")
        print(f"Потенциальных исправлений: {total_changes} в {files_to_modify} файлах.")
    else:
        print(f"ГОТОВО. Внесено {total_changes} исправлений в {files_to_modify} файлах.")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Игнорируем BrokenPipeError при использовании с head/tail
        sys.stderr.close()