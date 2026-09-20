#!/usr/bin/env python3
import re
import yaml
from pathlib import Path

p = Path("playbooks/document_types/group_6_intermediary/contract_6.1_mandate.yaml")
text = p.read_text(encoding="utf-8")

# Заменяем "8 полей" на "13 полей"
text = re.sub(
    r"Заполни строго следующие 8 полей \+ evidence \(всего 14 ключей\):",
    "Заполни строго следующие 13 полей + evidence (всего 14 ключей):",
    text
)

# Проверяем валидность YAML перед сохранением
try:
    yaml.safe_load(text)
    p.write_text(text, encoding="utf-8")
    print("✅ Успешно обновлено: 13 полей + evidence (всего 14 ключей)")
except Exception as e:
    print(f"❌ Ошибка валидации YAML: {e}")

    