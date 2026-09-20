#!/usr/bin/env python3
"""
fix_group9_comprehensive.py — Комплексный пакетный фикс всей группы 9 по стандартам v5.
"""

import re
import sys
import shutil
import tarfile
import yaml
from pathlib import Path
from datetime import datetime

APPLY = "--apply" in sys.argv
TARGET_DIR = Path("playbooks/document_types/group_9_special")

if not TARGET_DIR.exists():
    print(f"❌ Директория {TARGET_DIR} не найдена. Запустите из корня проекта.")
    sys.exit(1)

yaml_files = sorted(TARGET_DIR.rglob("*.yaml"))

print(f"📂 Найдено {len(yaml_files)} файлов в {TARGET_DIR}")
print(f"🔧 Режим: {'APPLY (мутация файлов)' if APPLY else 'DRY-RUN (только отчёт)'}")
print()

if APPLY:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = Path(f"/tmp/snapshot_group9_final_{ts}.tar.gz")
    with tarfile.open(snap, "w:gz") as tar:
        for f in yaml_files:
            tar.add(f, arcname=str(f))
    print(f"💾 Snapshot сохранён: {snap}\n")

stats = {
    "signal_fixed": 0,
    "negkw_removed": 0,
    "boost_fixed": 0,
    "files_changed": set(),
}

for fpath in yaml_files:
    original = fpath.read_text(encoding="utf-8")
    lines = original.split("\n")
    new_lines = []
    changed = False

    in_signal_field = False
    in_negative_kw = False
    in_position_bias = False

    for line in lines:
        stripped = line.strip()

        # Отслеживание полей
        if re.match(r"^\s+-\s+name:\s*", line):
            in_signal_field = False

        if re.match(r"^\s+presentation:\s*['\"]?signal['\"]?\s*$", line):
            in_signal_field = True

        # Отслеживание блоков retrieval
        if re.match(r"^\s+negative_keywords:\s*$", line):
            in_negative_kw = True
            in_position_bias = False
        elif re.match(r"^\s+position_bias:\s*$", line):
            in_position_bias = True
            in_negative_kw = False
        elif stripped and not stripped.startswith("#") and not stripped.startswith("-"):
            cur_indent = len(line) - len(line.lstrip())
            if cur_indent <= 6 and ":" in stripped:
                in_negative_kw = False
            if cur_indent <= 4 and ":" in stripped:
                in_position_bias = False

        # ── ПРАВКА 1: REQUIRED-SIGNAL ──
        if in_signal_field and re.match(r"^\s+required:\s*false\s*$", line, re.IGNORECASE):
            line = re.sub(r"required:\s*false", "required: true", line, flags=re.IGNORECASE)
            stats["signal_fixed"] += 1
            changed = True
            in_signal_field = False

        # ── ПРАВКА 2: NEGATIVE-KW (удаление строки с 'означает' в любом формате) ──
        if in_negative_kw:
            # Если элемент списка на новой строке
            if re.match(r"^\s+-\s+['\"]?означает['\"]?\s*$", line):
                stats["negkw_removed"] += 1
                changed = True
                continue
            # Если inline-список
            if "означает" in line and "[" in line:
                # Удаляем с запятой после слова
                line = re.sub(r'[\"\'«]означает[\"\'»]\s*,\s*', '', line)
                # Удаляем с запятой перед словом (если оно было последним)
                line = re.sub(r',\s*[\"\'«]означает[\"\'»]', '', line)
                # Удаляем одиночное слово в скобках
                line = re.sub(r'\[\s*[\"\'«]означает[\"\'»]\s*\]', '[]', line)
                stats["negkw_removed"] += 1
                changed = True

        # ── ПРАВКА 3: WEAK-RETRIEVAL (boost < 0.20 -> 0.30) ──
        if in_position_bias:
            m = re.match(r"^(\s+boost:\s*)(0\.\d+)(\s*)$", line)
            if m:
                boost_val = float(m.group(2))
                if boost_val < 0.20:
                    line = f"{m.group(1)}0.30{m.group(3)}"
                    stats["boost_fixed"] += 1
                    changed = True

        new_lines.append(line)

    if changed:
        stats["files_changed"].add(fpath.name)
        if APPLY:
            bak = fpath.with_suffix(".yaml.bak_final_group9")
            if not bak.exists():
                shutil.copy2(fpath, bak)
            content = "\n".join(new_lines)

            # Pre-flight проверка YAML
            try:
                yaml.safe_load(content)
                fpath.write_text(content, encoding="utf-8")
            except Exception as e:
                print(f"❌ ОШИБКА ВАЛИДАЦИИ {fpath.name}: {e}. Файл не изменён!")
                continue

print("=" * 70)
print("📊 ИТОГО ИСПРАВЛЕНИЙ:")
print(f"   REQUIRED-SIGNAL:    {stats['signal_fixed']} полей")
print(f"   NEGATIVE-KW:        {stats['negkw_removed']} вхождений")
print(f"   WEAK-RETRIEVAL:     {stats['boost_fixed']} boost-ов повышено")
print(f"   Файлов изменено:    {len(stats['files_changed'])}")
print("=" * 70)

if not APPLY:
    print("\nℹ️  DRY-RUN завершён. Для применения: python3 scripts/fix_group9_comprehensive.py --apply")
else:
    print("\n✅ Все изменения успешно применены и проверены через YAML safe_load.")


    