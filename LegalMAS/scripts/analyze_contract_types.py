#!/usr/bin/env python3
"""
Анализ структуры папок с типами контрактов.
Сканирует директорию и создаёт сводку с названиями контрактов из YAML.
"""

import os
import re
from pathlib import Path
from collections import defaultdict
import json


def extract_contract_name(file_path: str) -> str | None:
    """
    Извлекает название контракта из поля name (строка 2) YAML файла.
    Ищет паттерн: name: "Название" или name: 'Название' или name: Название
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # Ищем в первых 10 строках (на случай если есть комментарии в начале)
        for line in lines[:10]:
            # Паттерн: name: "..." или name: '...' или name: ...
            match = re.match(r'^name:\s*["\']?([^"\']+)["\']?\s*$', line.strip())
            if match:
                return match.group(1).strip()
                
    except Exception as e:
        return f"[ошибка чтения: {e}]"
    
    return None


def analyze_directory(base_path: str) -> dict:
    """
    Рекурсивно сканирует директорию и собирает информацию о файлах.
    Для YAML файлов извлекает название контракта.
    """
    base = Path(base_path)
    
    if not base.exists():
        raise FileNotFoundError(f"Папка не найдена: {base_path}")
    
    result = {
        'base_path': str(base.absolute()),
        'total_folders': 0,
        'total_files': 0,
        'yaml_files': 0,
        'by_extension': defaultdict(int),
        'folders': {}
    }
    
    for root, dirs, files in os.walk(base):
        rel_path = Path(root).relative_to(base)
        
        if rel_path == Path('.'):
            if files:
                folder_data = process_files(root, files, base)
                result['folders']['[корневая папка]'] = folder_data
                result['total_files'] += folder_data['file_count']
                result['yaml_files'] += folder_data['yaml_count']
                for ext, count in folder_data['extensions'].items():
                    result['by_extension'][ext] += count
            continue
        
        folder_name = str(rel_path)
        result['total_folders'] += 1
        
        folder_data = process_files(root, files, base)
        result['folders'][folder_name] = folder_data
        result['total_files'] += folder_data['file_count']
        result['yaml_files'] += folder_data['yaml_count']
        
        for ext, count in folder_data['extensions'].items():
            result['by_extension'][ext] += count
    
    result['by_extension'] = dict(result['by_extension'])
    return result


def process_files(root: str, files: list, base: Path) -> dict:
    """Обрабатывает список файлов и извлекает метаданные."""
    folder_data = {
        'path': str(Path(root).absolute()),
        'file_count': len(files),
        'yaml_count': 0,
        'files': [],
        'extensions': defaultdict(int),
        'subfolders': []
    }
    
    # Получаем подпапки
    rel_path = Path(root).relative_to(base)
    try:
        folder_data['subfolders'] = [d for d in Path(root).iterdir() if d.is_dir()]
        folder_data['subfolders'] = [d.name for d in folder_data['subfolders']]
    except:
        pass
    
    for f in sorted(files):
        file_path = Path(root) / f
        ext = Path(f).suffix.lower() or '[без расширения]'
        folder_data['extensions'][ext] += 1
        
        file_info = {
            'name': f,
            'extension': ext,
            'contract_name': None
        }
        
        # Для YAML файлов извлекаем название контракта
        if ext in ['.yaml', '.yml']:
            folder_data['yaml_count'] += 1
            contract_name = extract_contract_name(str(file_path))
            if contract_name:
                file_info['contract_name'] = contract_name
        
        folder_data['files'].append(file_info)
    
    return folder_data


def print_summary(data: dict):
    """Красивый вывод сводки в консоль."""
    print("=" * 80)
    print("СВОДКА ПО СТРУКТУРЕ ПАПОК")
    print("=" * 80)
    print(f"\n📂 Базовый путь: {data['base_path']}")
    print(f"📁 Всего подпапок: {data['total_folders']}")
    print(f"📄 Всего файлов: {data['total_files']}")
    print(f"🔧 YAML файлов: {data['yaml_files']}")
    
    print("\n" + "-" * 80)
    print("РАСПРЕДЕЛЕНИЕ ПО ТИПАМ ФАЙЛОВ:")
    print("-" * 80)
    for ext, count in sorted(data['by_extension'].items()):
        icon = "📄"
        if ext in ['.yaml', '.yml']:
            icon = "🔧"
        elif ext == '.json':
            icon = "📋"
        elif ext == '.md':
            icon = "📝"
        print(f"  {icon} {ext:20} : {count:3} файл(ов)")
    
    print("\n" + "=" * 80)
    print("СОДЕРЖИМОЕ ПО ПАПКАМ:")
    print("=" * 80)
    
    for folder_name in sorted(data['folders'].keys()):
        info = data['folders'][folder_name]
        print(f"\n📁 {folder_name}")
        print(f"   📍 Путь: {info['path']}")
        print(f"   📄 Файлов: {info['file_count']}")
        
        if info['subfolders']:
            print(f"   📂 Подпапки: {', '.join(info['subfolders'])}")
        
        if info['files']:
            print("   Содержимое:")
            for f in info['files']:
                ext = f['extension']
                icon = "📄"
                if ext in ['.yaml', '.yml']:
                    icon = "🔧"
                    contract = f.get('contract_name')
                    if contract:
                        print(f"      {icon} {f['name']:<30} - \"{contract}\"")
                    else:
                        print(f"      {icon} {f['name']:<30} - [название не найдено]")
                elif ext == '.json':
                    icon = "📋"
                    print(f"      {icon} {f['name']}")
                elif ext == '.md':
                    icon = "📝"
                    print(f"      {icon} {f['name']}")
                else:
                    print(f"      {icon} {f['name']}")
        else:
            print("   [пустая папка]")


def save_json(data: dict, output_path: str = "contract_types_summary.json"):
    """Сохраняет сводку в JSON."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON сохранён: {output_path}")


def save_markdown(data: dict, output_path: str = "contract_types_summary.md"):
    """Сохраняет сводку в Markdown."""
    lines = [
        "# Сводка по типам контрактов\n",
        f"**Базовый путь:** `{data['base_path']}`\n",
        f"**Всего подпапок:** {data['total_folders']}\n",
        f"**Всего файлов:** {data['total_files']}\n",
        f"**YAML файлов:** {data['yaml_files']}\n",
        "## Распределение по типам файлов\n",
        "| Расширение | Количество |",
        "|------------|-----------|"
    ]
    
    for ext, count in sorted(data['by_extension'].items()):
        lines.append(f"| {ext} | {count} |")
    
    lines.extend(["\n## Структура по папкам\n"])
    
    for folder_name in sorted(data['folders'].keys()):
        info = data['folders'][folder_name]
        lines.append(f"### {folder_name}\n")
        lines.append(f"- **Путь:** `{info['path']}`")
        lines.append(f"- **Файлов:** {info['file_count']}")
        
        if info['subfolders']:
            lines.append(f"- **Подпапки:** {', '.join(info['subfolders'])}")
        
        if info['files']:
            lines.append("- **Файлы:**")
            for f in info['files']:
                ext = f['extension']
                if ext in ['.yaml', '.yml'] and f.get('contract_name'):
                    lines.append(f"  - `{f['name']}` - \"{f['contract_name']}\"")
                else:
                    lines.append(f"  - `{f['name']}`")
        else:
            lines.append("- *[пустая папка]*")
        
        lines.append("")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"📝 Markdown сохранён: {output_path}")


def main():
    target_path = r"C:\LegalMAS\___ описание идеи ___\проекты yaml инструкций\contract_types"
    
    print(f"🔍 Анализируем: {target_path}\n")
    
    try:
        data = analyze_directory(target_path)
        print_summary(data)
        save_json(data)
        save_markdown(data)
        
        print("\n" + "=" * 80)
        print("✅ Анализ завершён!")
        print("=" * 80)
        
    except FileNotFoundError as e:
        print(f"❌ Ошибка: {e}")
        print("\nПроверьте, существует ли указанный путь.")
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()