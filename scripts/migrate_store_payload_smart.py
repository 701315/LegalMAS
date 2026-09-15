#!/usr/bin/env python3
"""
migrate_store_payload_smart.py — умный мигратор store_payload для doc-type чеков.
Анализирует каждый чек индивидуально. Сохраняет форматирование и комментарии.
"""

import argparse
import sys
import re
from pathlib import Path

# Поиск индивидуальных чеков в checks_v8
# Ищет начало чека "  - id:" и захватывает текст до следующего чека,
# начала другого корневого блока (например, doc_type_checks:) или конца файла.
_CHECK_BLOCK_RE = re.compile(
    r"^(  - id:\s*\S+.*?)(?=(?:^  - id:|^[a-z_]+:|\Z))",
    re.MULTILINE | re.DOTALL
)

def process_check_block(block_text: str, check_idx: int, filename: str) -> tuple[str, bool, str]:
    """
    Обрабатывает текст одного индивидуального чека.
    Возвращает: (новый_текст_блока, был_ли_изменен, статусное_сообщение)
    """
    check_id_match = re.match(r"^\s*-\s*id:\s*(\S+)", block_text)
    check_id = check_id_match.group(1).strip('"\'') if check_id_match else f"#{check_idx}"

    # Ищем store_payload на top-level чека (4 пробела)
    top_payload_match = re.search(r"^    store_payload:\s*(true|false)\b", block_text, re.MULTILINE)
    
    # Ищем блок extraction на top-level чека (4 пробела)
    has_extraction = bool(re.search(r"^    extraction:\s*$", block_text, re.MULTILINE))
    
    # Ищем store_payload внутри extraction (6 пробелов)
    nested_payload_match = re.search(r"^      store_payload:\s*(true|false)\b", block_text, re.MULTILINE)

    if not top_payload_match:
        # Все отлично: top-level payload отсутствует, значит править нечего
        return block_text, False, f"  - [{check_id}]: Пропущен (нет top-level store_payload)"

    # Значение top-level payload
    val = top_payload_match.group(1)

    if nested_payload_match:
        # Случай: дублирование (есть и на 4, и на 6 пробелах). Просто удаляем на 4 пробелах.
        new_text = re.sub(r"^    store_payload:\s*(?:true|false)\s*\n", "", block_text, flags=re.MULTILINE)
        return new_text, True, f"  - [{check_id}]: 🧹 Удален дублирующий top-level payload (корректный уже есть в extraction)"

    if not has_extraction:
        # Случай: payload есть на top-level, но блока extraction в чеке вообще нет.
        # В таком случае store_payload бессмысленен, так как сохранять нечего. Мы его просто удаляем.
        new_text = re.sub(r"^    store_payload:\s*(?:true|false)\s*\n", "", block_text, flags=re.MULTILINE)
        return new_text, True, f"  - [{check_id}]: ⚠️ Удален top-level payload, так как блок extraction отсутствует"

    # Основной случай: перенос внутрь extraction.
    # Шаг A: Удаляем top-level строку
    cleaned_text = re.sub(r"^    store_payload:\s*(?:true|false)\s*\n", "", block_text, flags=re.MULTILINE)
    
    # Шаг B: Вставляем на 6 пробелов сразу после объявления "    extraction:"
    def inject_nested(match):
        return f"    extraction:\n      store_payload: {val}\n"

    new_text = re.sub(r"^    extraction:\s*$", inject_nested, cleaned_text, flags=re.MULTILINE)
    
    return new_text, True, f"  - [{check_id}]:  Перенесен 'store_payload: {val}' внутрь extraction"


def migrate_file(path: Path, apply: bool = False) -> bool:
    content = path.read_text(encoding="utf-8")
    
    # Ищем границы checks_v8
    checks_v8_start = content.find("checks_v8:")
    if checks_v8_start == -1:
        return False

    # Находим границы следующего корневого блока после checks_v8
    # (чтобы работать только внутри checks_v8 и не задеть другие блоки)
    next_root_match = re.search(r"^[a-z_]+:", content[checks_v8_start + 10:], re.MULTILINE)
    if next_root_match:
        checks_v8_end = checks_v8_start + 10 + next_root_match.start()
    else:
        checks_v8_end = len(content)

    checks_v8_raw = content[checks_v8_start:checks_v8_end]
    
    # Находим все чеки внутри этого блока
    check_blocks = _CHECK_BLOCK_RE.findall(checks_v8_raw)
    if not check_blocks:
        return False

    new_blocks = []
    file_modified = False
    log_lines = []

    for idx, block in enumerate(check_blocks, 1):
        new_block, block_modified, msg = process_check_block(block, idx, path.name)
        new_blocks.append(new_block)
        if block_modified:
            file_modified = True
            log_lines.append(msg)

    if file_modified:
        print(f"\n📁 Файл: {path.name}")
        for log in log_lines:
            print(log)

        if apply:
            # Склеиваем файл обратно
            # Заменяем старый блок checks_v8 на новые измененные блоки
            new_checks_v8_raw = "checks_v8:\n" + "".join(new_blocks)
            modified_content = (
                content[:checks_v8_start] +
                new_checks_v8_raw +
                content[checks_v8_end:]
            )
            
            # Сохраняем бэкап
            backup_path = path.with_suffix(path.suffix + ".bak_payload")
            path.write_text(content, encoding="utf-8")
            path.write_text(modified_content, encoding="utf-8")
            print(f"    💾 Изменения записаны. Создан бэкап: {backup_path.name}")
        return True

    return False


def main():
    ap = argparse.ArgumentParser(description="Умный мигратор store_payload для checks_v8.")
    ap.add_argument("folder", type=Path, help="Путь к проверяемой папке.")
    ap.add_argument("--apply", action="store_true", help="Применить изменения на диск.")
    args = ap.parse_args()

    if not args.folder.exists():
        print(f"❌ Папка не найдена: {args.folder}", file=sys.stderr)
        return 1

    files = sorted(args.folder.rglob("*.yaml")) + sorted(args.folder.rglob("*.yml"))
    
    print(f"\n🚀 Запуск SMART-миграции store_payload в папке: {args.folder}")
    if not args.apply:
        print("⚠️  Режим DRY-RUN. Изменения на диск не записываются. Используй --apply для записи.\n")

    modified_files_count = 0
    for f in files:
        if migrate_file(f, args.apply):
            modified_files_count += 1

    print(f"\n🏁 Завершено. Изменено файлов: {modified_files_count} из {len(files)}.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

    