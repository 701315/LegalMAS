#!/usr/bin/env python3
"""
Скрипт для сбора всех frontend-файлов (JS, TS, Vue, React, CSS, HTML и др.)
из указанной директории в один текстовый файл с чёткими разделителями.
"""

import os
from pathlib import Path
from datetime import datetime

# ============ НАСТРОЙКИ ============
SOURCE_DIR = "/home/vladi/projects/LegalMAS/frontend"
OUTPUT_FILE = "/home/vladi/projects/LegalMAS/all_frontend_code.txt"

# Расширения файлов для сбора
FRONTEND_EXTENSIONS = {
    # JavaScript / TypeScript
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    # Vue
    ".vue",
    # Стили
    ".css", ".scss", ".sass", ".less", ".styl",
    # Разметка
    ".html", ".htm",
    # Конфиги (опционально)
    ".json", ".yaml", ".yml",
    # Другое
    ".svelte", ".astro",
}

# Папки, которые нужно игнорировать
IGNORE_DIRS = {
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".output",
    "coverage",
    ".git",
    "__pycache__",
    ".vite",
    ".turbo",
}

# Файлы, которые нужно игнорировать (по имени)
IGNORE_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
}
# ===================================


def should_ignore_path(path: Path) -> bool:
    """Проверяет, нужно ли игнорировать путь."""
    # Проверяем, есть ли игнорируемые директории в пути
    for part in path.parts:
        if part in IGNORE_DIRS:
            return True
    
    # Проверяем имя файла
    if path.name in IGNORE_FILES:
        return True
    
    return False


def collect_frontend_files(source_dir: str) -> list[Path]:
    """Рекурсивно собирает все frontend-файлы из директории."""
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"Директория не найдена: {source_dir}")
    
    all_files = []
    
    for ext in FRONTEND_EXTENSIONS:
        files = source_path.rglob(f"*{ext}")
        for f in files:
            if not should_ignore_path(f):
                all_files.append(f)
    
    # Сортируем для консистентности
    return sorted(set(all_files))


def get_file_type(path: Path) -> str:
    """Возвращает тип файла для отображения."""
    ext_map = {
        ".js": "JavaScript",
        ".jsx": "React JSX",
        ".ts": "TypeScript",
        ".tsx": "React TSX",
        ".vue": "Vue Component",
        ".css": "CSS",
        ".scss": "SCSS",
        ".sass": "Sass",
        ".less": "Less",
        ".html": "HTML",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".svelte": "Svelte",
        ".astro": "Astro",
    }
    return ext_map.get(path.suffix.lower(), path.suffix.upper())


def build_output(files: list[Path], source_dir: str) -> str:
    """Формирует итоговый текст с разделителями."""
    source_path = Path(source_dir)
    parts = []

    # --- Заголовок ---
    parts.append("=" * 80)
    parts.append("FRONTEND CODE DUMP")
    parts.append(f"Source directory: {source_dir}")
    parts.append(f"Generated at:     {datetime.now().isoformat()}")
    parts.append(f"Total files:      {len(files)}")
    parts.append("=" * 80)
    parts.append("")

    # --- Статистика по типам файлов ---
    ext_count = {}
    for f in files:
        ext = f.suffix.lower()
        ext_count[ext] = ext_count.get(ext, 0) + 1
    
    parts.append("FILE STATISTICS:")
    parts.append("-" * 40)
    for ext, count in sorted(ext_count.items(), key=lambda x: -x[1]):
        parts.append(f"  {ext:>8}: {count} files")
    parts.append("-" * 40)
    parts.append("")

    # --- Оглавление ---
    parts.append("TABLE OF CONTENTS:")
    parts.append("-" * 40)
    for i, fpath in enumerate(files, 1):
        relative = fpath.relative_to(source_path)
        file_type = get_file_type(fpath)
        parts.append(f"  {i:>3}. [{file_type:>12}] {relative}")
    parts.append("-" * 40)
    parts.append("")
    parts.append("")

    # --- Содержимое каждого файла ---
    for i, fpath in enumerate(files, 1):
        relative = fpath.relative_to(source_path)
        file_type = get_file_type(fpath)

        parts.append("=" * 80)
        parts.append(f">>> FILE_START | index={i} | type={file_type} | path={relative}")
        parts.append("=" * 80)

        try:
            content = fpath.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = fpath.read_text(encoding="latin-1")
            except Exception as e:
                content = f"[ERROR READING FILE: {e}]"

        parts.append(content)

        # Гарантируем перевод строки перед маркером конца
        if not content.endswith("\n"):
            parts.append("")

        parts.append("=" * 80)
        parts.append(f"<<< FILE_END | index={i} | path={relative}")
        parts.append("=" * 80)
        parts.append("")
        parts.append("")

    # --- Финальный маркер ---
    parts.append("=" * 80)
    parts.append("END OF FRONTEND CODE DUMP")
    parts.append("=" * 80)

    return "\n".join(parts)


def main():
    print(f"🔍 Сканирую директорию: {SOURCE_DIR}")
    print(f"📁 Игнорируемые папки: {', '.join(sorted(IGNORE_DIRS))}")
    print()
    
    files = collect_frontend_files(SOURCE_DIR)
    print(f"📄 Найдено frontend-файлов: {len(files)}")

    if not files:
        print("❌ Нет файлов для обработки.")
        return

    # Показываем превью найденных файлов
    print("\nПревью файлов (первые 10):")
    for f in files[:10]:
        print(f"   - {f.relative_to(SOURCE_DIR)}")
    if len(files) > 10:
        print(f"   ... и ещё {len(files) - 10} файлов")
    print()

    output_text = build_output(files, SOURCE_DIR)

    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"✅ Результат записан в: {OUTPUT_FILE}")
    print(f"📊 Размер файла: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()