"""
Скрипт для сбора указанных файлов проекта
в один текстовый файл с чёткими разделителями.
"""

import os
from pathlib import Path
from datetime import datetime

# ============ НАСТРОЙКИ ============
PROJECT_ROOT = "/home/vladi/projects/LegalMAS"
OUTPUT_FILE = "/home/vladi/projects/LegalMAS/all_required_heading_dump.txt"

FILES = [
    "src/classifiers/yaml_registry.py",
    "src/classifiers/base.py",
    "src/classifiers/stage8/l3_semantic.py",
    "src/classifiers/stage8/l2_header.py",
    "src/classifiers/stage8/l1_filename.py",
    "src/classifiers/stage8/hybrid_classifier.py",
    "src/classifiers/stage8/_voting.py",
    "src/classifiers/stage8/_result_builder.py",
    "src/classifiers/stage8/_l4_llm.py",
    "src/classifiers/stage8/_duplicate_handler.py",
    "src/classifiers/stage8/_content_fetcher.py",
    "src/workers/classifier.py",
    "src/workers/segment_classifier.py",
]

# ===================================


def build_output(files: list[str], project_root: str) -> str:
    """Формирует итоговый текст с разделителями."""
    root_path = Path(project_root)
    parts = []
    
    # Проверяем существование файлов
    existing_files = []
    missing_files = []
    
    for fp in files:
        full_path = root_path / fp
        if full_path.exists():
            existing_files.append((fp, full_path))
        else:
            missing_files.append(fp)

    # --- Заголовок ---
    parts.append("=" * 100)
    parts.append("FOCUSED PIPELINE CODE DUMP")
    parts.append(f"Project root:    {project_root}")
    parts.append(f"Generated at:    {datetime.now().isoformat()}")
    parts.append(f"Total files:     {len(files)}")
    parts.append(f"Found files:     {len(existing_files)}")
    parts.append(f"Missing files:   {len(missing_files)}")
    parts.append("=" * 100)
    parts.append("")

    # --- Оглавление ---
    parts.append("TABLE OF CONTENTS:")
    parts.append("-" * 60)
    for i, (rel_path, _) in enumerate(existing_files, 1):
        parts.append(f"  {i:>3}. {rel_path}")
    parts.append("-" * 60)
    
    # --- Отсутствующие файлы ---
    if missing_files:
        parts.append("")
        parts.append("MISSING FILES (not found):")
        parts.append("-" * 60)
        for fp in missing_files:
            parts.append(f"  [!] {fp}")
        parts.append("-" * 60)
    
    parts.append("")
    parts.append("")

    # --- Содержимое каждого файла ---
    for i, (rel_path, full_path) in enumerate(existing_files, 1):
        parts.append("=" * 100)
        parts.append(f">>> FILE_START | index={i} | path={rel_path}")
        parts.append("=" * 100)

        try:
            content = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = full_path.read_text(encoding="latin-1")
            except Exception as e:
                content = f"[ERROR reading file: {e}]"

        parts.append(content)

        if not content.endswith("\n"):
            parts.append("")

        parts.append("=" * 100)
        parts.append(f"<<< FILE_END | index={i} | path={rel_path}")
        parts.append("=" * 100)
        parts.append("")
        parts.append("")

    # --- Финальный маркер ---
    parts.append("=" * 100)
    parts.append("END OF FOCUSED PIPELINE CODE DUMP")
    parts.append("=" * 100)

    return "\n".join(parts)


def main():
    print(f"Проект: {PROJECT_ROOT}")
    print(f"Файлов в списке: {len(FILES)}")
    print()

    output_text = build_output(FILES, PROJECT_ROOT)

    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"Результат записан в: {OUTPUT_FILE}")
    print(f"Размер файла: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()

    