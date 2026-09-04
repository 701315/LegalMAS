#!/usr/bin/env python3
"""
Аудит JSON-словарей i18n: en/ vs ru/
Показывает:
  1. Список файлов в каждой локали
  2. Все ключи (включая вложенные) в каждом файле
  3. Ключи, присутствующие в en/ но отсутствующие в ru/ (и наоборот)
  4. Сводку по количеству ключей
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict


def flatten_keys(obj, prefix=""):
    """Рекурсивно извлекает все leaf-ключи из вложенного JSON."""
    keys = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.extend(flatten_keys(v, full_key))
            else:
                keys.append(full_key)
    return keys


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠ Ошибка чтения {path}: {e}")
        return None


def main():
    base = Path("/srv/steloom-dev/frontend/public/locales")
    en_dir = base / "en"
    ru_dir = base / "ru"

    if not en_dir.exists():
        print(f"❌ Директория не найдена: {en_dir}")
        sys.exit(1)
    if not ru_dir.exists():
        print(f"❌ Директория не найдена: {ru_dir}")
        sys.exit(1)

    en_files = sorted(f.name for f in en_dir.glob("*.json"))
    ru_files = sorted(f.name for f in ru_dir.glob("*.json"))

    print("=" * 72)
    print("  АУДИТ СЛОВАРЕЙ i18n — Steloom")
    print("=" * 72)

    # --- 1. Файлы ---
    print("\n📁 Файлы в en/:")
    for f in en_files:
        print(f"   ✅ {f}")
    print(f"\n📁 Файлы в ru/:")
    for f in ru_files:
        print(f"   ✅ {f}")

    en_only_files = set(en_files) - set(ru_files)
    ru_only_files = set(ru_files) - set(en_files)
    if en_only_files:
        print(f"\n⚠ Файлы только в en/ (нет в ru/): {en_only_files}")
    if ru_only_files:
        print(f"\n⚠ Файлы только в ru/ (нет в en/): {ru_only_files}")

    # --- 2. Ключи по файлам ---
    common_files = sorted(set(en_files) & set(ru_files))
    total_en_keys = 0
    total_ru_keys = 0
    total_missing_in_ru = 0
    total_missing_in_en = 0

    print("\n" + "=" * 72)
    print("  ДЕТАЛИЗАЦИЯ ПО ФАЙЛАМ")
    print("=" * 72)

    summary_rows = []

    for fname in common_files:
        en_data = load_json(en_dir / fname)
        ru_data = load_json(ru_dir / fname)
        if en_data is None or ru_data is None:
            continue

        en_keys = set(flatten_keys(en_data))
        ru_keys = set(flatten_keys(ru_data))

        missing_in_ru = sorted(en_keys - ru_keys)
        missing_in_en = sorted(ru_keys - en_keys)

        total_en_keys += len(en_keys)
        total_ru_keys += len(ru_keys)
        total_missing_in_ru += len(missing_in_ru)
        total_missing_in_en += len(missing_in_en)

        status = "✅" if not missing_in_ru and not missing_in_en else "⚠"
        print(f"\n{status} {fname}")
        print(f"   en: {len(en_keys)} ключей | ru: {len(ru_keys)} ключей")

        if missing_in_ru:
            print(f"   🔴 Нет в ru/ ({len(missing_in_ru)}):")
            for k in missing_in_ru:
                print(f"      - {k}")
        if missing_in_en:
            print(f"   🟡 Нет в en/ ({len(missing_in_en)}):")
            for k in missing_in_en:
                print(f"      - {k}")

        summary_rows.append((fname, len(en_keys), len(ru_keys),
                             len(missing_in_ru), len(missing_in_en)))

    # --- 3. Сводка ---
    print("\n" + "=" * 72)
    print("  СВОДКА")
    print("=" * 72)
    print(f"{'Файл':<25} {'en':>5} {'ru':>5} {'Δ→ru':>6} {'Δ→en':>6}")
    print("-" * 50)
    for row in summary_rows:
        print(f"{row[0]:<25} {row[1]:>5} {row[2]:>5} {row[3]:>6} {row[4]:>6}")
    print("-" * 50)
    print(f"{'ИТОГО':<25} {total_en_keys:>5} {total_ru_keys:>5} "
          f"{total_missing_in_ru:>6} {total_missing_in_en:>6}")

    print(f"\n📊 Всего уникальных ключей в en/: {total_en_keys}")
    print(f"📊 Всего уникальных ключей в ru/: {total_ru_keys}")
    print(f"🔴 Ключей в en/ без перевода в ru/: {total_missing_in_ru}")
    print(f"🟡 Ключей в ru/ без аналога в en/: {total_missing_in_en}")

    if total_missing_in_ru == 0 and total_missing_in_en == 0:
        print("\n🎉 Паритет en/ ↔ ru/ достигнут по всем файлам!")
    else:
        print(f"\n⚠ Требуется синхронизация {total_missing_in_ru + total_missing_in_en} ключей.")


if __name__ == "__main__":
    main()



    