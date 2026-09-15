#!/usr/bin/env python3
"""
fix_group6_final.py — Исправление 68 дефектов в group_6_intermediary.
Гибридный режим: YAML-модель + raw-text regex.
"""
import re
import sys
import shutil
import tarfile
import yaml
from pathlib import Path
from datetime import datetime

APPLY = "--apply" in sys.argv
TARGET_DIR = Path("playbooks/document_types/group_6_intermediary")

if not TARGET_DIR.exists():
    print(f"❌ Директория {TARGET_DIR} не найдена.")
    sys.exit(1)

yaml_files = sorted(TARGET_DIR.rglob("*.yaml"))
print(f"📂 Найдено {len(yaml_files)} файлов")
print(f"🔧 Режим: {'APPLY' if APPLY else 'DRY-RUN'}\n")

if APPLY:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = Path(f"/tmp/snapshot_group6_final_{ts}.tar.gz")
    with tarfile.open(snap, "w:gz") as tar:
        for f in yaml_files:
            tar.add(f, arcname=str(f))
    print(f"💾 Snapshot: {snap}\n")

stats = {"signal": 0, "task": 0, "negkw": 0, "boost": 0, "files": set()}

for fpath in yaml_files:
    raw = fpath.read_text(encoding="utf-8")

    # 1. Читаем YAML-модель для карты {check_id: n_fields}
    try:
        data = yaml.safe_load(raw) or {}
    except Exception as e:
        print(f"❌ {fpath.name}: {e}")
        continue

    checks = data.get("checks_v8") or []
    field_map = {}
    for c in checks:
        cid = c.get("id")
        ext = c.get("extraction") or {}
        n = len(ext.get("fields") or [])
        field_map[cid] = n

    lines = raw.split("\n")
    new_lines = []
    changed = False

    # Контекстные флаги
    current_check_id = None
    in_signal_field = False
    in_negative_kw = False
    in_position_bias = False
    in_task_block = False
    task_inserted = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Отслеживание текущего чека
        m_id = re.match(r"^\s+-\s+id:\s+([a-zA-Z0-9_]+)", line)
        if m_id:
            current_check_id = m_id.group(1)
            in_task_block = False
            task_inserted = False

        # Отслеживание signal-полей
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

        # ── FIX 1: REQUIRED-SIGNAL ──
        if in_signal_field and re.match(r"^\s+required:\s*false\s*$", line, re.IGNORECASE):
            line = re.sub(r"required:\s*false", "required: true", line, flags=re.IGNORECASE)
            stats["signal"] += 1
            changed = True
            in_signal_field = False

        # ── FIX 2: NEGATIVE-KW ──
        if in_negative_kw:
            if re.match(r"^\s+-\s+['\"]?означает['\"]?\s*$", line):
                stats["negkw"] += 1
                changed = True
                continue
            if "означает" in line and "[" in line:
                line = re.sub(r'["\'«]означает["\'»]\s*,\s*', '', line)
                line = re.sub(r',\s*["\'«]означает["\'»]', '', line)
                stats["negkw"] += 1
                changed = True

        # ── FIX 3: WEAK-BOOST ──
        if in_position_bias:
            m = re.match(r"^(\s+boost:\s*)(0\.\d+)(\s*)$", line)
            if m and float(m.group(2)) < 0.20:
                line = f"{m.group(1)}0.30{m.group(3)}"
                stats["boost"] += 1
                changed = True

        # ── FIX 4: CANONICAL <task> ──
        if stripped == "<task>":
            in_task_block = True
            task_inserted = False
            new_lines.append(line)
            # Вставляем каноническую строку после <task>
            if current_check_id and current_check_id in field_map:
                n = field_map[current_check_id]
                nk = n + 1
                indent = "        "
                new_lines.append(f"{indent}Заполни строго следующие {n} полей + evidence (всего {nk} ключей):")
                new_lines.append(f"{indent}")
                stats["task"] += 1
                changed = True
                task_inserted = True
            continue

        new_lines.append(line)

    if changed:
        stats["files"].add(fpath.name)
        if APPLY:
            bak = fpath.with_suffix(".yaml.bak_final_g6")
            if not bak.exists():
                shutil.copy2(fpath, bak)
            content = "\n".join(new_lines)
            try:
                yaml.safe_load(content)
                fpath.write_text(content, encoding="utf-8")
            except Exception as e:
                print(f"❌ ОШИБКА {fpath.name}: {e}")
                continue

print("=" * 70)
print("📊 ИТОГО ИСПРАВЛЕНИЙ:")
print(f"   REQUIRED-SIGNAL:    {stats['signal']}")
print(f"   CANONICAL-TASK:     {stats['task']}")
print(f"   NEGATIVE-KW:        {stats['negkw']}")
print(f"   WEAK-BOOST:         {stats['boost']}")
print(f"   Файлов:             {len(stats['files'])}")
print("=" * 70)

if not APPLY:
    print("\nℹ️  DRY-RUN. Для применения: python3 scripts/fix_group6_final.py --apply")
else:
    print("\n✅ Все изменения применены.")


    