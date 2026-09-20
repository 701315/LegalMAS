#!/usr/bin/env python3
"""Fix DD Grid naming contract: singleton -> *_code for 3 alimony checks."""
import re
from pathlib import Path

PATH = Path("playbooks/document_types/group_9_special/contract_9.4_alimony_agreement.yaml")
RENAMES = {
    "adjustment_procedure":      "adjustment_procedure_code",
    "family_category":           "family_category_code",
    "pm_category":               "pm_category_code",
}

text = PATH.read_text(encoding="utf-8")
orig = text

# Не трогаем *_details, *_status, *_value — заменяем ТОЛЬКО точное имя поля
for old, new in RENAMES.items():
    # word-boundary: old как отдельный ключ JSON, имя поля, или имя переменной
    pattern = rf'(?<![\w_]){re.escape(old)}(?![\w_])'
    text = re.sub(pattern, new, text)

if text == orig:
    print("⚠️  Никаких изменений — проверь, что файл уже не исправлен.")
else:
    backup = PATH.with_suffix(".yaml.bak_naming_contract")
    backup.write_text(orig, encoding="utf-8")
    PATH.write_text(text, encoding="utf-8")
    print(f"✅ Исправлено. Бэкап: {backup}")



    