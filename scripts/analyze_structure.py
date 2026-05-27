#!/usr/bin/env python3
"""
Скрипт для анализа структуры проекта LegalMAS.
Проходит по всем папкам и файлам, создаёт дерево и описания.
"""

import os
import ast
import json
import re
from pathlib import Path
from datetime import datetime


def analyze_python_file(filepath):
    """Анализирует Python файл: классы, методы, функции, return типы."""
    result = {
        "type": "python",
        "description": "",
        "classes": [],
        "functions": [],
        "imports": [],
        "global_variables": []
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            source = f.read()
        
        tree = ast.parse(source)
        
        # Получаем docstring модуля
        module_docstring = ast.get_docstring(tree)
        if module_docstring:
            result["description"] = module_docstring.strip().split('\n')[0]
        
        for node in ast.iter_child_nodes(tree):
            # Импорты
            if isinstance(node, ast.Import):
                for alias in node.names:
                    result["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    result["imports"].append(f"{module}.{alias.name}")
            
            # Функции верхнего уровня
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                func_info = _analyze_function(node)
                result["functions"].append(func_info)
            
            # Классы
            elif isinstance(node, ast.ClassDef):
                class_info = _analyze_class(node)
                result["classes"].append(class_info)
            
            # Глобальные переменные (присваивания на верхнем уровне)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        result["global_variables"].append(target.id)
        
        # Если нет docstring, пытаемся понять назначение по содержимому
        if not result["description"]:
            result["description"] = _guess_file_purpose(filepath, result)
    
    except SyntaxError as e:
        result["description"] = f"[Ошибка парсинга: {e}]"
    except Exception as e:
        result["description"] = f"[Ошибка: {e}]"
    
    return result


def _analyze_function(node):
    """Анализирует функцию/метод."""
    func_info = {
        "name": node.name,
        "async": isinstance(node, ast.AsyncFunctionDef),
        "args": [],
        "return_annotation": None,
        "docstring": None,
        "decorators": [],
        "return_types": []
    }
    
    # Аргументы
    for arg in node.args.args:
        arg_name = arg.arg
        arg_annotation = None
        if arg.annotation:
            arg_annotation = _get_annotation_str(arg.annotation)
        func_info["args"].append({"name": arg_name, "type": arg_annotation})
    
    # Return annotation
    if node.returns:
        func_info["return_annotation"] = _get_annotation_str(node.returns)
    
    # Docstring
    docstring = ast.get_docstring(node)
    if docstring:
        func_info["docstring"] = docstring.strip().split('\n')[0]
    
    # Декораторы
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name):
            func_info["decorators"].append(decorator.id)
        elif isinstance(decorator, ast.Attribute):
            func_info["decorators"].append(_get_attribute_str(decorator))
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                func_info["decorators"].append(decorator.func.id)
            elif isinstance(decorator.func, ast.Attribute):
                func_info["decorators"].append(_get_attribute_str(decorator.func))
    
    # Анализ return statements
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value:
            ret_type = _guess_return_type(child.value)
            if ret_type and ret_type not in func_info["return_types"]:
                func_info["return_types"].append(ret_type)
    
    return func_info


def _analyze_class(node):
    """Анализирует класс."""
    class_info = {
        "name": node.name,
        "bases": [],
        "docstring": None,
        "methods": [],
        "class_variables": [],
        "decorators": []
    }
    
    # Базовые классы
    for base in node.bases:
        if isinstance(base, ast.Name):
            class_info["bases"].append(base.id)
        elif isinstance(base, ast.Attribute):
            class_info["bases"].append(_get_attribute_str(base))
    
    # Docstring
    docstring = ast.get_docstring(node)
    if docstring:
        class_info["docstring"] = docstring.strip().split('\n')[0]
    
    # Декораторы класса
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name):
            class_info["decorators"].append(decorator.id)
        elif isinstance(decorator, ast.Attribute):
            class_info["decorators"].append(_get_attribute_str(decorator))
    
    # Методы и переменные класса
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_info = _analyze_function(item)
            class_info["methods"].append(method_info)
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    class_info["class_variables"].append(target.id)
        elif isinstance(item, ast.AnnAssign):
            if isinstance(item.target, ast.Name):
                ann = _get_annotation_str(item.annotation) if item.annotation else "?"
                class_info["class_variables"].append(f"{item.target.id}: {ann}")
    
    return class_info


def _get_annotation_str(node):
    """Преобразует AST аннотацию в строку."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        return repr(node.value)
    elif isinstance(node, ast.Attribute):
        return _get_attribute_str(node)
    elif isinstance(node, ast.Subscript):
        base = _get_annotation_str(node.value)
        if isinstance(node.slice, ast.Tuple):
            slices = ", ".join(_get_annotation_str(el) for el in node.slice.elts)
        else:
            slices = _get_annotation_str(node.slice)
        return f"{base}[{slices}]"
    elif isinstance(node, ast.Tuple):
        return ", ".join(_get_annotation_str(el) for el in node.elts)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _get_annotation_str(node.left)
        right = _get_annotation_str(node.right)
        return f"{left} | {right}"
    elif isinstance(node, ast.List):
        return "[" + ", ".join(_get_annotation_str(el) for el in node.elts) + "]"
    return "..."


def _get_attribute_str(node):
    """Получает строковое представление атрибута (a.b.c)."""
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _guess_return_type(node):
    """Пытается угадать тип возвращаемого значения."""
    if isinstance(node, ast.Constant):
        return type(node.value).__name__
    elif isinstance(node, ast.Dict):
        return "dict"
    elif isinstance(node, ast.List):
        return "list"
    elif isinstance(node, ast.Tuple):
        return "tuple"
    elif isinstance(node, ast.Set):
        return "set"
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return _get_attribute_str(node.func)
    elif isinstance(node, ast.Name):
        if node.id in ('True', 'False'):
            return "bool"
        return node.id
    elif isinstance(node, ast.JoinedStr):
        return "str (f-string)"
    elif isinstance(node, ast.BoolOp):
        return "bool"
    elif isinstance(node, ast.Compare):
        return "bool"
    elif isinstance(node, ast.IfExp):
        return "conditional"
    elif isinstance(node, ast.Await):
        return "awaited"
    return None


def _guess_file_purpose(filepath, analysis):
    """Пытается угадать назначение файла по его содержимому."""
    filename = os.path.basename(filepath)
    
    if filename == "__init__.py":
        if analysis["imports"] or analysis["global_variables"]:
            return "Инициализация пакета, экспорт модулей"
        return "Инициализация пакета (пустой)"
    
    if filename == "conftest.py":
        return "Конфигурация pytest, фикстуры"
    
    if filename.startswith("test_"):
        return "Тесты"
    
    # Угадываем по классам
    if analysis["classes"]:
        class_names = [c["name"] for c in analysis["classes"]]
        bases = []
        for c in analysis["classes"]:
            bases.extend(c["bases"])
        
        if any("Agent" in name for name in class_names + bases):
            return f"Определение агента: {', '.join(class_names)}"
        if any("Model" in name or "Schema" in name or "Base" in name for name in class_names + bases):
            return f"Модели данных: {', '.join(class_names)}"
        if any("Service" in name for name in class_names):
            return f"Сервис: {', '.join(class_names)}"
        if any("Config" in name or "Settings" in name for name in class_names):
            return f"Конфигурация: {', '.join(class_names)}"
    
    return f"Модуль {Path(filepath).stem}"


def analyze_yaml_file(filepath):
    """Анализирует YAML файл."""
    result = {
        "type": "yaml",
        "description": "",
        "keys": [],
        "size_lines": 0
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            lines = content.split('\n')
            result["size_lines"] = len(lines)
        
        # Извлекаем ключи верхнего уровня
        top_keys = []
        for line in lines:
            if line and not line.startswith(' ') and not line.startswith('#') and ':' in line:
                key = line.split(':')[0].strip()
                if key and not key.startswith('-'):
                    top_keys.append(key)
        result["keys"] = top_keys[:15]  # Ограничиваем
        
        # Первый комментарий как описание
        for line in lines:
            if line.strip().startswith('#'):
                desc = line.strip().lstrip('#').strip()
                if desc:
                    result["description"] = desc
                    break
        
        if not result["description"]:
            result["description"] = f"YAML конфигурация ({len(lines)} строк)"
            if top_keys:
                result["description"] += f", ключи: {', '.join(top_keys[:5])}"
    
    except Exception as e:
        result["description"] = f"[Ошибка: {e}]"
    
    return result


def analyze_json_file(filepath):
    """Анализирует JSON файл."""
    result = {
        "type": "json",
        "description": "",
        "keys": []
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            data = json.load(f)
        
        if isinstance(data, dict):
            result["keys"] = list(data.keys())[:15]
            result["description"] = f"JSON объект, ключи: {', '.join(result['keys'][:5])}"
        elif isinstance(data, list):
            result["description"] = f"JSON массив, {len(data)} элементов"
        else:
            result["description"] = f"JSON значение: {type(data).__name__}"
    
    except Exception as e:
        result["description"] = f"[Ошибка: {e}]"
    
    return result


def analyze_markdown_file(filepath):
    """Анализирует Markdown файл."""
    result = {
        "type": "markdown",
        "description": "",
        "headers": []
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        for line in lines:
            if line.startswith('#'):
                header = line.strip()
                result["headers"].append(header)
        
        # Первый заголовок как описание
        if result["headers"]:
            result["description"] = result["headers"][0].lstrip('#').strip()
        else:
            result["description"] = f"Markdown документ ({len(lines)} строк)"
    
    except Exception as e:
        result["description"] = f"[Ошибка: {e}]"
    
    return result


def analyze_text_file(filepath):
    """Анализирует текстовый файл (txt, prompt, и т.д.)."""
    result = {
        "type": "text",
        "description": "",
        "size_lines": 0
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        result["size_lines"] = len(lines)
        
        # Первая непустая строка как описание
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                result["description"] = stripped[:100]
                if len(stripped) > 100:
                    result["description"] += "..."
                break
        
        if not result["description"]:
            result["description"] = f"Текстовый файл ({len(lines)} строк)"
    
    except Exception as e:
        result["description"] = f"[Ошибка: {e}]"
    
    return result


def analyze_file(filepath):
    """Определяет тип файла и вызывает соответствующий анализатор."""
    ext = Path(filepath).suffix.lower()
    name = Path(filepath).name.lower()
    
    if ext in ('.py',):
        return analyze_python_file(filepath)
    elif ext in ('.yaml', '.yml'):
        return analyze_yaml_file(filepath)
    elif ext in ('.json',):
        return analyze_json_file(filepath)
    elif ext in ('.md', '.rst'):
        return analyze_markdown_file(filepath)
    elif ext in ('.txt', '.prompt', '.j2', '.jinja2', '.jinja', '.template', '.tmpl'):
        return analyze_text_file(filepath)
    elif ext in ('.toml',):
        return analyze_text_file(filepath)
    elif ext in ('.cfg', '.ini', '.conf', '.env'):
        return analyze_text_file(filepath)
    elif ext in ('.sh', '.bash'):
        return analyze_text_file(filepath)
    elif name in ('makefile', 'dockerfile', '.gitignore', '.dockerignore', 'requirements.txt', 'pyproject.toml'):
        return analyze_text_file(filepath)
    else:
        # Пытаемся как текст
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                f.read(512)
            return analyze_text_file(filepath)
        except:
            return {"type": "binary", "description": f"Бинарный файл ({ext})"}


def get_file_size_str(filepath):
    """Возвращает размер файла в читаемом формате."""
    size = os.path.getsize(filepath)
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


def build_tree(directories, output_file):
    """Строит дерево проекта и записывает в файл."""
    
    # Игнорируемые директории и файлы
    ignore_dirs = {
        '__pycache__', '.git', '.venv', 'venv', 'env', '.env',
        'node_modules', '.idea', '.vscode', '.mypy_cache',
        '.pytest_cache', '.tox', 'dist', 'build', '*.egg-info',
        '.eggs', '.hypothesis'
    }
    
    ignore_files = {
        '.DS_Store', 'Thumbs.db', '.gitkeep'
    }
    
    ignore_extensions = {
        '.pyc', '.pyo', '.pyd', '.so', '.dylib',
        '.egg', '.whl'
    }
    
    lines = []
    lines.append("=" * 80)
    lines.append(f"  СТРУКТУРА ПРОЕКТА LegalMAS")
    lines.append(f"  Дата генерации: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  Анализируемые директории:")
    for d in directories:
        lines.append(f"    - {d}")
    lines.append("=" * 80)
    lines.append("")
    
    all_analyses = {}
    
    for root_dir in directories:
        if not os.path.exists(root_dir):
            lines.append(f"⚠️  Директория не найдена: {root_dir}")
            lines.append("")
            continue
        
        root_path = Path(root_dir)
        root_name = root_path.name
        parent_path = root_path.parent
        
        lines.append(f"📁 {root_dir}")
        lines.append("─" * 60)
        
        for dirpath, dirnames, filenames in os.walk(root_dir, topdown=True):
            # Фильтруем игнорируемые директории
            dirnames[:] = sorted([
                d for d in dirnames
                if d not in ignore_dirs and not d.endswith('.egg-info')
            ])
            
            # Фильтруем файлы
            filenames = sorted([
                f for f in filenames
                if f not in ignore_files and Path(f).suffix not in ignore_extensions
            ])
            
            # Вычисляем уровень вложенности
            rel_path = os.path.relpath(dirpath, root_dir)
            if rel_path == '.':
                level = 0
            else:
                level = len(rel_path.split(os.sep))
            
            indent = "│   " * level
            
            # Печатаем директорию (кроме корневой, которую уже напечатали)
            if level > 0:
                dir_name = os.path.basename(dirpath)
                lines.append(f"{indent}📂 {dir_name}/")
            
            # Печатаем файлы
            file_indent = "│   " * (level + 1) if level >= 0 else "│   "
            if level == 0:
                file_indent = "│   "
            
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                file_size = get_file_size_str(filepath)
                
                # Анализируем файл
                analysis = analyze_file(filepath)
                rel_file_path = os.path.relpath(filepath, parent_path)
                all_analyses[rel_file_path] = analysis
                
                ext = Path(filename).suffix.lower()
                
                # Иконка по типу файла
                icon = "📄"
                if ext == '.py':
                    icon = "🐍"
                elif ext in ('.yaml', '.yml'):
                    icon = "⚙️"
                elif ext == '.json':
                    icon = "📋"
                elif ext in ('.md', '.rst'):
                    icon = "📝"
                elif ext in ('.txt',):
                    icon = "📃"
                elif ext in ('.sh', '.bash'):
                    icon = "🔧"
                elif ext in ('.j2', '.jinja2', '.jinja', '.template'):
                    icon = "📐"
                
                lines.append(f"{file_indent}{icon} {filename} ({file_size})")
        
        lines.append("")
    
    # =====================================================================
    # ДЕТАЛЬНОЕ ОПИСАНИЕ ФАЙЛОВ
    # =====================================================================
    lines.append("")
    lines.append("=" * 80)
    lines.append("  ДЕТАЛЬНОЕ ОПИСАНИЕ ФАЙЛОВ")
    lines.append("=" * 80)
    
    for filepath, analysis in sorted(all_analyses.items()):
        lines.append("")
        lines.append("─" * 70)
        lines.append(f"📄 {filepath}")
        lines.append(f"   Тип: {analysis.get('type', 'unknown')}")
        
        desc = analysis.get('description', '')
        if desc:
            lines.append(f"   Описание: {desc}")
        
        # Python-специфичная информация
        if analysis.get('type') == 'python':
            # Импорты
            imports = analysis.get('imports', [])
            if imports:
                lines.append(f"   Импорты: {', '.join(imports[:10])}")
                if len(imports) > 10:
                    lines.append(f"            ... и ещё {len(imports) - 10}")
            
            # Глобальные переменные
            gvars = analysis.get('global_variables', [])
            if gvars:
                lines.append(f"   Глобальные переменные: {', '.join(gvars[:10])}")
            
            # Функции верхнего уровня
            functions = analysis.get('functions', [])
            if functions:
                lines.append(f"   Функции ({len(functions)}):")
                for func in functions:
                    _format_function(func, lines, indent="      ")
            
            # Классы
            classes = analysis.get('classes', [])
            if classes:
                lines.append(f"   Классы ({len(classes)}):")
                for cls in classes:
                    _format_class(cls, lines, indent="      ")
        
        # YAML
        elif analysis.get('type') == 'yaml':
            keys = analysis.get('keys', [])
            if keys:
                lines.append(f"   Ключи верхнего уровня: {', '.join(keys)}")
            size = analysis.get('size_lines', 0)
            if size:
                lines.append(f"   Строк: {size}")
        
        # JSON
        elif analysis.get('type') == 'json':
            keys = analysis.get('keys', [])
            if keys:
                lines.append(f"   Ключи: {', '.join(keys)}")
        
        # Markdown
        elif analysis.get('type') == 'markdown':
            headers = analysis.get('headers', [])
            if headers:
                lines.append(f"   Заголовки:")
                for h in headers[:10]:
                    lines.append(f"      {h}")
                if len(headers) > 10:
                    lines.append(f"      ... и ещё {len(headers) - 10}")
        
        # Текст
        elif analysis.get('type') == 'text':
            size = analysis.get('size_lines', 0)
            if size:
                lines.append(f"   Строк: {size}")
    
    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  Всего файлов проанализировано: {len(all_analyses)}")
    
    # Статистика по типам
    type_counts = {}
    for a in all_analyses.values():
        t = a.get('type', 'unknown')
        type_counts[t] = type_counts.get(t, 0) + 1
    
    lines.append("  Статистика по типам:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"    {t}: {c}")
    
    lines.append("=" * 80)
    
    # Записываем в файл
    output = "\n".join(lines)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(output)
    print(f"\n\n✅ Результат сохранён в: {output_file}")
    
    return output


def _format_function(func, lines, indent=""):
    """Форматирует информацию о функции."""
    async_prefix = "async " if func.get("async") else ""
    
    # Формируем сигнатуру
    args_str = []
    for arg in func.get("args", []):
        if arg["name"] == "self" or arg["name"] == "cls":
            args_str.append(arg["name"])
        elif arg["type"]:
            args_str.append(f"{arg['name']}: {arg['type']}")
        else:
            args_str.append(arg["name"])
    
    ret = func.get("return_annotation", "")
    ret_str = f" -> {ret}" if ret else ""
    
    decorators = func.get("decorators", [])
    dec_str = ""
    if decorators:
        dec_str = f" [{', '.join('@' + d for d in decorators)}]"
    
    sig = f"{indent}{async_prefix}def {func['name']}({', '.join(args_str)}){ret_str}{dec_str}"
    lines.append(sig)
    
    # Docstring
    if func.get("docstring"):
        lines.append(f"{indent}  📖 {func['docstring']}")
    
    # Return types (если нет аннотации)
    if not ret and func.get("return_types"):
        lines.append(f"{indent}  ↩️  Возвращает: {', '.join(func['return_types'])}")


def _format_class(cls, lines, indent=""):
    """Форматирует информацию о классе."""
    bases_str = f"({', '.join(cls['bases'])})" if cls.get("bases") else ""
    
    decorators = cls.get("decorators", [])
    dec_str = ""
    if decorators:
        dec_str = f" [{', '.join('@' + d for d in decorators)}]"
    
    lines.append(f"{indent}class {cls['name']}{bases_str}{dec_str}")
    
    if cls.get("docstring"):
        lines.append(f"{indent}  📖 {cls['docstring']}")
    
    # Переменные класса
    cvars = cls.get("class_variables", [])
    if cvars:
        lines.append(f"{indent}  Атрибуты класса: {', '.join(cvars[:10])}")
        if len(cvars) > 10:
            lines.append(f"{indent}                   ... и ещё {len(cvars) - 10}")
    
    # Методы
    methods = cls.get("methods", [])
    if methods:
        lines.append(f"{indent}  Методы ({len(methods)}):")
        for method in methods:
            _format_function(method, lines, indent=indent + "    ")


def main():
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent  # .../LegalMAS

    directories = [
        str(project_root / "src"),
        str(project_root / "prompts"),
        str(project_root / "playbooks"),
    ]

    output_file = str(project_root / "PROJECT_STRUCTURE.txt")

    build_tree(directories, output_file)


if __name__ == "__main__":
    main()

