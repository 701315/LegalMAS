
"""
Скрипт для сбора всех Python-файлов из директории engine
в один текстовый файл с чёткими разделителями.
"""

import os
from pathlib import Path
from datetime import datetime

# ============ НАСТРОЙКИ ============
SOURCE_DIR = "/home/vladi/projects/LegalMAS/src/engine"
OUTPUT_FILE = "/home/vladi/projects/LegalMAS/engine_code.txt"
# ===================================


def collect_python_files(source_dir: str) -> list[Path]:
    """Рекурсивно собирает все .py файлы из директории."""
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"Директория не найдена: {source_dir}")
    
    py_files = sorted(source_path.rglob("*.py"))
    return py_files


def build_output(py_files: list[Path], source_dir: str) -> str:
    """Формирует итоговый текст с разделителями."""
    source_path = Path(source_dir)
    parts = []

    # --- Заголовок ---
    parts.append("=" * 80)
    parts.append("ENGINE CODE DUMP")
    parts.append(f"Source directory: {source_dir}")
    parts.append(f"Generated at:    {datetime.now().isoformat()}")
    parts.append(f"Total files:     {len(py_files)}")
    parts.append("=" * 80)
    parts.append("")

    # --- Оглавление ---
    parts.append("TABLE OF CONTENTS:")
    parts.append("-" * 40)
    for i, fpath in enumerate(py_files, 1):
        relative = fpath.relative_to(source_path)
        parts.append(f"  {i:>3}. {relative}")
    parts.append("-" * 40)
    parts.append("")
    parts.append("")

    # --- Содержимое каждого файла ---
    for i, fpath in enumerate(py_files, 1):
        relative = fpath.relative_to(source_path)

        parts.append("=" * 80)
        parts.append(f">>> FILE_START | index={i} | path={relative}")
        parts.append("=" * 80)

        try:
            content = fpath.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = fpath.read_text(encoding="latin-1")

        parts.append(content)

        if not content.endswith("\n"):
            parts.append("")

        parts.append("=" * 80)
        parts.append(f"<<< FILE_END | index={i} | path={relative}")
        parts.append("=" * 80)
        parts.append("")
        parts.append("")

    # --- Финальный маркер ---
    parts.append("=" * 80)
    parts.append("END OF ENGINE CODE DUMP")
    parts.append("=" * 80)

    return "\n".join(parts)


def main():
    print(f"Сканирую директорию: {SOURCE_DIR}")
    py_files = collect_python_files(SOURCE_DIR)
    print(f"Найдено Python-файлов: {len(py_files)}")

    if not py_files:
        print("Нет файлов для обработки.")
        return

    output_text = build_output(py_files, SOURCE_DIR)

    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"Результат записан в: {OUTPUT_FILE}")
    print(f"Размер файла: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
