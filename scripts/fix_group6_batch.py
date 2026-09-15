#!/usr/bin/env python3
"""
fix_group6_batch.py — Пакетное исправление group_6_intermediary по стандартам v5.
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
    print(f"❌ Директория {TARGET_DIR} не найдена. Запустите из корня проекта.")
    sys.exit(1)

yaml_files = sorted(TARGET_DIR.rglob("*.yaml"))

print(f"📂 Найдено {len(yaml_files)} файлов в {TARGET_DIR}")
print(f"🔧 Режим: {'APPLY (мутация файлов)' if APPLY else 'DRY-RUN (только отчёт)'}")
print()

if APPLY:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = Path(f"/tmp/snapshot_group6_{ts}.tar.gz")
    with tarfile.open(snap, "w:gz") as tar:
        for f in yaml_files:
            tar.add(f, arcname=str(f))
    print(f"💾 Snapshot сохранён: {snap}\n")

stats = {
    "signal_fixed": 0,
    "negkw_removed": 0,
    "boost_fixed": 0,
    "counters_synced": 0,
    "duplicates_removed": 0,
    "files_changed": set(),
}

for fpath in yaml_files:
    original = fpath.read_text(encoding="utf-8")
    
    # ── ПРЕДВАРИТЕЛЬНОЕ УДАЛЕНИЕ ДУБЛИКАТОВ ЧЕКОВ ──
    try:
        data = yaml.safe_load(original) or {}
        checks = data.get("checks_v8") or []
        ids_seen = set()
        unique_checks = []
        has_dups = False
        
        for c in checks:
            cid = c.get("id")
            if cid in ids_seen:
                has_dups = True
                stats["duplicates_removed"] += 1
                continue
            ids_seen.add(cid)
            unique_checks.append(c)
            
        if has_dups and APPLY:
            data["checks_v8"] = unique_checks
            original = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
            changed = True
    except Exception as e:
        print(f"⚠️ Ошибка чистки дубликатов в {fpath.name}: {e}")

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
            if re.match(r"^\s+-\s+['\"]?означает['\"]?\s*$", line):
                stats["negkw_removed"] += 1
                changed = True
                continue
            if "означает" in line and "[" in line:
                line = re.sub(r'[\"\'«]означает[\"\'»]\s*,\s*', '', line)
                line = re.sub(r',\s*[\"\'«]означает[\"\'»]', '', line)
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

    raw_text = "\n".join(new_lines)

    # ── ПРАВКА 4: ТОЧЕЧНАЯ СИНХРОНИЗАЦИЯ СЧЁТЧИКОВ (БЛОЧНО) ──
    try:
        data = yaml.safe_load(raw_text) or {}
        checks = data.get("checks_v8") or []
        field_counts = {c.get("id"): len(c.get("extraction", {}).get("fields") or []) for c in checks}
        
        chunks = re.split(r"(?m)(?=^  - id:\s+)", raw_text)
        new_chunks = []
        file_modified = False
        
        for chunk in chunks:
            m_id = re.search(r"(?m)^  - id:\s+([a-zA-Z0-9_]+)", chunk)
            if not m_id:
                new_chunks.append(chunk)
                continue
                
            cid = m_id.group(1)
            n_fields = field_counts.get(cid, 0)
            if n_fields == 0:
                new_chunks.append(chunk)
                continue
                
            n_keys = n_fields + 1
            old_chunk = chunk
            
            # Синхронизация <task>
            chunk = re.sub(
                r"Заполни строго следующие\s+\d+\s+полей(?:\s*\+\s*evidence\s*\(всего\s*\d+\s*ключей\))?:",
                f"Заполни строго следующие {n_fields} полей + evidence (всего {n_keys} ключей):",
                chunk
            )
            # Вспомогательный вариант для agency_subject_extraction
            chunk = re.sub(
                r"Заполни строго следующие\s+\d+\s+полей\s*\(всего\s*\d+\s*ключей\s+в\s+JSON\):",
                f"Заполни строго следующие {n_fields} полей + evidence (всего {n_keys} ключей):",
                chunk
            )
            # Синхронизация CoVe
            chunk = re.sub(
                r"Проверь, что все\s+\d+\s+ключей\s*\(\d+\s+полей\s*\+\s*evidence\)\s*присутствуют",
                f"Проверь, что все {n_keys} ключей ({n_fields} полей + evidence) присутствуют",
                chunk
            )
            chunk = re.sub(
                r"Все\s+\d+\s+ключей\s*присутствуют в JSON\?",
                f"Все {n_keys} ключей ({n_fields} полей + evidence) присутствуют в JSON?",
                chunk
            )
            # Синхронизация [ПРАВИЛА]
            chunk = re.sub(
                r"со всеми\s+\d+\s+ключами",
                f"со всеми {n_keys} ключами",
                chunk
            )
            
            if chunk != old_chunk:
                stats["counters_synced"] += 1
                changed = True
                
            new_chunks.append(chunk)
        raw_text = "".join(new_chunks)
    except Exception as e:
        print(f"⚠️ Ошибка подсчёта полей в {fpath.name}: {e}")

    if changed:
        stats["files_changed"].add(fpath.name)
        if APPLY:
            bak = fpath.with_suffix(".yaml.bak_fix_group6")
            if not bak.exists():
                shutil.copy2(fpath, bak)
            
            try:
                yaml.safe_load(raw_text)
                fpath.write_text(raw_text, encoding="utf-8")
            except Exception as e:
                print(f"❌ ОШИБКА ВАЛИДАЦИИ YAML {fpath.name}: {e}. Файл не изменён!")
                continue

print("=" * 70)
print("📊 ИТОГО ИСПРАВЛЕНИЙ:")
print(f"   REQUIRED-SIGNAL:    {stats['signal_fixed']} полей")
print(f"   NEGATIVE-KW:        {stats['negkw_removed']} вхождений")
print(f"   WEAK-RETRIEVAL:     {stats['boost_fixed']} boost-ов повышено")
print(f"   COUNTERS SYNCED:    {stats['counters_synced']} чеков")
print(f"   DUPLICATES REMOVED: {stats['duplicates_removed']} чеков")
print(f"   Файлов изменено:    {len(stats['files_changed'])}")
print("=" * 70)

if not APPLY:
    print("\nℹ️  DRY-RUN завершён. Для применения: python3 scripts/fix_group6_batch.py --apply")
else:
    print("\n✅ Все изменения применены и проверены через YAML safe_load.")

    