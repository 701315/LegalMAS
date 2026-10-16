#!/usr/bin/env python3
"""Механическое исправление форматирования v3. Работает в режиме dry-run по умолчанию."""
import argparse, re, sys
from pathlib import Path
import yaml

FINAL_LINE = "Технический формат JSON (value / confidence / location) задан отдельным контрактом — соблюдай его, но не описывай здесь."
TYPO = ".без markdown."

def fix_check(c: dict, raw_text: str) -> tuple[dict, str, list[str]]:
    """Возвращает (измененный чек, измененный raw_text, список изменений)"""
    changes = []
    ex = c.get("extraction", {})
    
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
        # Проверяем, есть ли уже финальная строка (с учетом возможных пробелов/переносов)
        if FINAL_LINE.strip() not in l2:
            # Находим место перед закрывающим тегом
            l2_new = re.sub(
                r"(</output_expectations>)",
                f"- {FINAL_LINE}\n\\1",
                l2
            )
            if l2_new != l2:
                ex["llm_prompt_extraction"] = l2_new
                changes.append("FIX L4: добавлена финальная строка в output_expectations")

    # 3. Удаление опечатки (WARN:X2)
    if TYPO in raw_text:
        raw_text = raw_text.replace(TYPO, "")
        changes.append(f"FIX X2: удалена опечатка '{TYPO}'")
        # Также чистим в словаре, если yaml парсер уже прочитал
        if c.get("llm", {}).get("prompt_template"):
            c["llm"]["prompt_template"] = c["llm"]["prompt_template"].replace(TYPO, "")
        if ex.get("llm_prompt_extraction"):
            ex["llm_prompt_extraction"] = ex["llm_prompt_extraction"].replace(TYPO, "")

    return c, raw_text, changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="playbooks/document_types")
    ap.add_argument("--dry-run", action="store_true", help="Не записывать изменения, только показать")
    a = ap.parse_args()

    files = sorted(Path(a.root).rglob("*.yaml"))
    total_changes = 0
    files_to_modify = 0

    for p in files:
        raw = p.read_text(encoding="utf-8")
        try:
            doc = yaml.safe_load(raw)
        except Exception as e:
            print(f"[ERR] {p}: {e}", file=sys.stderr)
            continue

        checks = doc.get("checks_v8") or doc.get("checks") or []
        if not checks:
            continue

        file_changed = False
        new_raw = raw
        
        for i, c in enumerate(checks):
            new_c, new_raw, changes = fix_check(c, new_raw)
            if changes:
                file_changed = True
                total_changes += len(changes)
                if not a.dry_run:
                    checks[i] = new_c
                else:
                    print(f"\n[{p}] Чек: {c.get('id')}")
                    for ch in changes:
                        print(f"  -> {ch}")

        if file_changed:
            files_to_modify += 1
            if not a.dry_run:
                # Пересобираем YAML, сохраняя порядок ключей
                with open(p, "w", encoding="utf-8") as f:
                    yaml.dump(doc, f, allow_unicode=True, sort_keys=False, width=1000)
                print(f"[OK] Записано: {p}")

    print("\n" + "="*60)
    if a.dry_run:
        print(f"РЕЖИМ DRY-RUN. Изменений не внесено.")
        print(f"Потенциальных исправлений: {total_changes} в {files_to_modify} файлах.")
        print("Чтобы применить правки, запустите: python3 scripts/fix_mechanical.py")
    else:
        print(f"ГОТОВО. Внесено {total_changes} исправлений в {files_to_modify} файлах.")


if __name__ == "__main__":
    main()



    