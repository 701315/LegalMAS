#!/usr/bin/env python3
"""
Скрипт для анализа Python-файлов в проекте LegalMAS.
Проверяет:
1. Длину файлов (выделяет >500 строк)
2. Длину отдельных строк (>120 символов)
3. Смешение ответственностей в файлах
4. Сложность функций/методов
5. Количество классов и функций в одном файле
"""

import os
import ast
import sys
from datetime import datetime
from collections import defaultdict
from pathlib import Path

SRC_DIR = "/home/vladi/projects/LegalMAS/src"
OUTPUT_DIR = "/home/vladi/projects/LegalMAS/scripts"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "результаты проверки.txt")

# Пороговые значения
MAX_FILE_LINES = 500
MAX_LINE_LENGTH = 120
MAX_FUNCTION_LINES = 50
MAX_METHOD_LINES = 40
MAX_CLASSES_PER_FILE = 3
MAX_TOP_LEVEL_FUNCTIONS_PER_FILE = 10
MAX_METHODS_PER_CLASS = 15
MAX_PARAMS_PER_FUNCTION = 7
MAX_CYCLOMATIC_COMPLEXITY_APPROX = 10  # приблизительная цикломатическая сложность


# ─────────────────────────────────────────────────────────────────────
# Категории ответственностей для обнаружения смешения
# ─────────────────────────────────────────────────────────────────────
RESPONSIBILITY_KEYWORDS = {
    "Работа с БД / ORM": [
        "session", "query", "commit", "rollback", "execute", "cursor",
        "database", "db_", "sqlalchemy", "create_engine", "Base.metadata",
        "Table(", "Column(", "ForeignKey", "relationship(",
        "AsyncSession", "sessionmaker", "select(", "insert(", "update(",
        "delete(", ".filter(", ".filter_by(",
    ],
    "HTTP / API / Роутинг": [
        "FastAPI", "APIRouter", "app.get", "app.post", "app.put", "app.delete",
        "@router", "Request", "Response", "HTTPException", "status_code",
        "JSONResponse", "Depends(", "Query(", "Body(", "Path(",
        "flask", "Blueprint", "route(",
    ],
    "Бизнес-логика / Сервисы": [
        "Service", "service", "process_", "calculate_", "validate_",
        "analyze_", "generate_", "transform_",
    ],
    "Модели / Схемы данных": [
        "BaseModel", "Field(", "validator", "Schema", "Pydantic",
        "dataclass", "@dataclass", "NamedTuple",
    ],
    "Утилиты / Хелперы": [
        "utils", "helper", "format_", "parse_", "convert_",
        "serialize", "deserialize",
    ],
    "Логирование": [
        "logging", "logger", "getLogger", "log.info", "log.error",
        "log.warning", "log.debug",
    ],
    "Конфигурация": [
        "config", "settings", "Config", "Settings", "env",
        "load_config", "get_settings",
    ],
    "AI / ML / LLM": [
        "openai", "llm", "langchain", "embedding", "vector",
        "ChatOpenAI", "LLM", "prompt", "chain", "agent",
        "CrewAI", "autogen", "transformers",
    ],
    "Файловая система / IO": [
        "open(", "read_file", "write_file", "os.path", "pathlib",
        "shutil", "glob", "json.load", "json.dump", "yaml",
        "csv", "pickle",
    ],
    "Тесты": [
        "unittest", "pytest", "test_", "assert", "mock", "patch",
        "fixture", "TestCase",
    ],
}


def count_lines(filepath):
    """Считает количество строк в файле."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return lines, len(lines)
    except Exception as e:
        return [], 0


def check_line_lengths(lines):
    """Проверяет длину каждой строки."""
    long_lines = []
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip("\n\r")
        if len(stripped) > MAX_LINE_LENGTH:
            long_lines.append((i, len(stripped), stripped[:150]))
    return long_lines


def analyze_ast(filepath):
    """Анализирует AST файла для получения метрик."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return None
    except Exception:
        return None

    result = {
        "classes": [],
        "top_level_functions": [],
        "imports": [],
        "long_functions": [],
        "complex_functions": [],
        "too_many_params": [],
    }

    for node in ast.walk(tree):
        # Собираем импорты
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    result["imports"].append(alias.name)
            else:
                if node.module:
                    result["imports"].append(node.module)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_lines = _get_node_lines(item)
                    params_count = _count_params(item)
                    complexity = _estimate_complexity(item)
                    method_info = {
                        "name": item.name,
                        "lines": func_lines,
                        "start_line": item.lineno,
                        "params": params_count,
                        "complexity": complexity,
                    }
                    methods.append(method_info)

                    if func_lines > MAX_METHOD_LINES:
                        result["long_functions"].append({
                            "name": f"{node.name}.{item.name}",
                            "lines": func_lines,
                            "start_line": item.lineno,
                            "type": "метод",
                        })
                    if params_count > MAX_PARAMS_PER_FUNCTION:
                        result["too_many_params"].append({
                            "name": f"{node.name}.{item.name}",
                            "params": params_count,
                            "start_line": item.lineno,
                        })
                    if complexity > MAX_CYCLOMATIC_COMPLEXITY_APPROX:
                        result["complex_functions"].append({
                            "name": f"{node.name}.{item.name}",
                            "complexity": complexity,
                            "start_line": item.lineno,
                        })

            class_info = {
                "name": node.name,
                "methods": methods,
                "method_count": len(methods),
                "start_line": node.lineno,
                "lines": _get_node_lines(node),
            }
            result["classes"].append(class_info)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_lines = _get_node_lines(node)
            params_count = _count_params(node)
            complexity = _estimate_complexity(node)
            func_info = {
                "name": node.name,
                "lines": func_lines,
                "start_line": node.lineno,
                "params": params_count,
                "complexity": complexity,
            }
            result["top_level_functions"].append(func_info)

            if func_lines > MAX_FUNCTION_LINES:
                result["long_functions"].append({
                    "name": node.name,
                    "lines": func_lines,
                    "start_line": node.lineno,
                    "type": "функция",
                })
            if params_count > MAX_PARAMS_PER_FUNCTION:
                result["too_many_params"].append({
                    "name": node.name,
                    "params": params_count,
                    "start_line": node.lineno,
                })
            if complexity > MAX_CYCLOMATIC_COMPLEXITY_APPROX:
                result["complex_functions"].append({
                    "name": node.name,
                    "complexity": complexity,
                    "start_line": node.lineno,
                })

    return result


def _get_node_lines(node):
    """Вычисляет количество строк в узле AST."""
    if hasattr(node, "end_lineno") and node.end_lineno:
        return node.end_lineno - node.lineno + 1
    return 0


def _count_params(func_node):
    """Считает количество параметров функции (исключая self/cls)."""
    args = func_node.args
    count = len(args.args) + len(args.posonlyargs) + len(args.kwonlyargs)
    if args.vararg:
        count += 1
    if args.kwarg:
        count += 1
    # Исключаем self/cls
    if args.args and args.args[0].arg in ("self", "cls"):
        count -= 1
    return count


def _estimate_complexity(node):
    """
    Приблизительная оценка цикломатической сложности.
    Считает ветвления: if, elif, for, while, except, with, and, or, assert.
    """
    complexity = 1  # базовая сложность
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp)):
            complexity += 1
        elif isinstance(child, (ast.For, ast.AsyncFor)):
            complexity += 1
        elif isinstance(child, (ast.While,)):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, (ast.With, ast.AsyncWith)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            # and/or добавляют по 1 за каждый операнд после первого
            complexity += len(child.values) - 1
        elif isinstance(child, ast.Assert):
            complexity += 1
        elif isinstance(child, ast.comprehension):
            complexity += 1
            complexity += len(child.ifs)
    return complexity


def detect_mixed_responsibilities(filepath, lines, ast_info):
    """
    Определяет смешение ответственностей в файле.
    Ищет ключевые слова из разных категорий.
    """
    content = "".join(lines)
    detected = {}

    for category, keywords in RESPONSIBILITY_KEYWORDS.items():
        matched_keywords = []
        for kw in keywords:
            if kw in content:
                matched_keywords.append(kw)
        if matched_keywords:
            detected[category] = matched_keywords

    return detected


def assess_srp_violation(detected_responsibilities, ast_info):
    """
    Оценивает нарушение принципа единой ответственности (SRP).
    Возвращает уровень нарушения и описание.
    """
    issues = []

    # Исключаем «легковесные» категории, которые могут быть в любом файле
    lightweight = {"Логирование", "Конфигурация"}
    significant = {k: v for k, v in detected_responsibilities.items() if k not in lightweight}

    if len(significant) >= 3:
        cats = ", ".join(significant.keys())
        issues.append(
            f"⚠️  ВЫСОКОЕ смешение ответственностей: обнаружено {len(significant)} "
            f"различных категорий: [{cats}]"
        )
    elif len(significant) == 2:
        cats = ", ".join(significant.keys())
        # Некоторые комбинации допустимы
        keys_set = set(significant.keys())
        bad_combos = [
            {"Работа с БД / ORM", "HTTP / API / Роутинг"},
            {"Работа с БД / ORM", "AI / ML / LLM"},
            {"HTTP / API / Роутинг", "AI / ML / LLM"},
            {"Тесты", "Бизнес-логика / Сервисы"},
        ]
        if keys_set in bad_combos:
            issues.append(
                f"⚠️  Смешение ответственностей: [{cats}] — рекомендуется разделить"
            )
        else:
            issues.append(
                f"ℹ️  Замечание: обнаружены категории [{cats}] — проверьте, "
                f"оправдано ли их совмещение"
            )

    if ast_info:
        # Много классов в одном файле
        if len(ast_info["classes"]) > MAX_CLASSES_PER_FILE:
            issues.append(
                f"⚠️  Слишком много классов в одном файле: "
                f"{len(ast_info['classes'])} (рекомендуется ≤ {MAX_CLASSES_PER_FILE})"
            )

        # Много top-level функций
        if len(ast_info["top_level_functions"]) > MAX_TOP_LEVEL_FUNCTIONS_PER_FILE:
            issues.append(
                f"⚠️  Слишком много функций верхнего уровня: "
                f"{len(ast_info['top_level_functions'])} "
                f"(рекомендуется ≤ {MAX_TOP_LEVEL_FUNCTIONS_PER_FILE})"
            )

        # Классы с большим количеством методов
        for cls in ast_info["classes"]:
            if cls["method_count"] > MAX_METHODS_PER_CLASS:
                issues.append(
                    f"⚠️  Класс '{cls['name']}' имеет {cls['method_count']} методов "
                    f"(рекомендуется ≤ {MAX_METHODS_PER_CLASS})"
                )

    return issues


def generate_refactoring_suggestions(file_data):
    """Генерирует рекомендации по рефакторингу."""
    suggestions = []

    if file_data["line_count"] > 800:
        suggestions.append(
            "🔴 КРИТИЧНО: Файл чрезвычайно длинный (>800 строк). "
            "Необходимо срочно разбить на несколько модулей."
        )
    elif file_data["line_count"] > MAX_FILE_LINES:
        suggestions.append(
            "🟡 Файл превышает 500 строк. Рекомендуется разбить на несколько модулей."
        )

    if file_data["long_functions"]:
        for func in file_data["long_functions"]:
            suggestions.append(
                f"🟡 {func['type'].capitalize()} '{func['name']}' слишком длинная "
                f"({func['lines']} строк, строка {func['start_line']}). "
                f"Разбейте на более мелкие функции."
            )

    if file_data["complex_functions"]:
        for func in file_data["complex_functions"]:
            suggestions.append(
                f"🟡 '{func['name']}' имеет высокую сложность "
                f"(≈{func['complexity']}, строка {func['start_line']}). "
                f"Упростите логику или разбейте на части."
            )

    if file_data["too_many_params"]:
        for func in file_data["too_many_params"]:
            suggestions.append(
                f"🟡 '{func['name']}' принимает слишком много параметров "
                f"({func['params']}, строка {func['start_line']}). "
                f"Используйте dataclass/DTO для группировки."
            )

    if file_data["long_lines_count"] > 20:
        suggestions.append(
            f"🟡 {file_data['long_lines_count']} строк превышают {MAX_LINE_LENGTH} символов. "
            f"Используйте переносы строк."
        )
    elif file_data["long_lines_count"] > 5:
        suggestions.append(
            f"ℹ️  {file_data['long_lines_count']} строк превышают {MAX_LINE_LENGTH} символов."
        )

    return suggestions


def scan_directory(src_dir):
    """Сканирует директорию и возвращает список .py файлов."""
    py_files = []
    for root, dirs, files in os.walk(src_dir):
        # Исключаем __pycache__, .git, venv и т.д.
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "venv", ".venv", "env", "node_modules")]
        for f in sorted(files):
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    return sorted(py_files)


def analyze_file(filepath, src_dir):
    """Полный анализ одного файла."""
    rel_path = os.path.relpath(filepath, src_dir)
    lines, line_count = count_lines(filepath)
    long_lines = check_line_lengths(lines)
    ast_info = analyze_ast(filepath)
    responsibilities = detect_mixed_responsibilities(filepath, lines, ast_info)
    srp_issues = assess_srp_violation(responsibilities, ast_info)

    file_data = {
        "path": filepath,
        "rel_path": rel_path,
        "line_count": line_count,
        "long_lines": long_lines,
        "long_lines_count": len(long_lines),
        "ast_info": ast_info,
        "responsibilities": responsibilities,
        "srp_issues": srp_issues,
        "long_functions": ast_info["long_functions"] if ast_info else [],
        "complex_functions": ast_info["complex_functions"] if ast_info else [],
        "too_many_params": ast_info["too_many_params"] if ast_info else [],
    }

    file_data["suggestions"] = generate_refactoring_suggestions(file_data)

    # Определяем, требует ли файл рефакторинга
    needs_refactoring = bool(
        file_data["suggestions"]
        or file_data["srp_issues"]
    )
    file_data["needs_refactoring"] = needs_refactoring

    # Определяем уровень серьёзности
    severity = "✅ OK"
    if line_count > 800 or any("КРИТИЧНО" in s for s in file_data["suggestions"]):
        severity = "🔴 КРИТИЧНО"
    elif (line_count > MAX_FILE_LINES
          or file_data["long_functions"]
          or file_data["complex_functions"]
          or any("ВЫСОКОЕ" in s for s in file_data["srp_issues"])):
        severity = "🟡 ТРЕБУЕТ ВНИМАНИЯ"
    elif needs_refactoring:
        severity = "🔵 РЕКОМЕНДАЦИИ"

    file_data["severity"] = severity

    return file_data


def format_report(all_data, src_dir):
    """Форматирует итоговый отчёт."""
    report = []
    sep = "=" * 100
    sep2 = "-" * 80

    report.append(sep)
    report.append("  РЕЗУЛЬТАТЫ ПРОВЕРКИ PYTHON-ФАЙЛОВ ПРОЕКТА LegalMAS")
    report.append(sep)
    report.append(f"  Дата проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"  Директория: {src_dir}")
    report.append(f"  Всего файлов проанализировано: {len(all_data)}")
    report.append("")

    # ─── Сводная статистика ───
    total_lines = sum(d["line_count"] for d in all_data)
    files_over_500 = [d for d in all_data if d["line_count"] > MAX_FILE_LINES]
    files_needing_refactoring = [d for d in all_data if d["needs_refactoring"]]
    critical = [d for d in all_data if d["severity"] == "🔴 КРИТИЧНО"]
    warnings = [d for d in all_data if d["severity"] == "🟡 ТРЕБУЕТ ВНИМАНИЯ"]
    info = [d for d in all_data if d["severity"] == "🔵 РЕКОМЕНДАЦИИ"]
    ok = [d for d in all_data if d["severity"] == "✅ OK"]

    report.append("  СВОДНАЯ СТАТИСТИКА")
    report.append(sep2)
    report.append(f"  Общее количество строк кода:         {total_lines}")
    report.append(f"  Файлов > {MAX_FILE_LINES} строк:                     {len(files_over_500)}")
    report.append(f"  Файлов, требующих рефакторинга:      {len(files_needing_refactoring)}")
    report.append(f"")
    report.append(f"  🔴 Критично:                          {len(critical)}")
    report.append(f"  🟡 Требует внимания:                  {len(warnings)}")
    report.append(f"  🔵 Рекомендации:                      {len(info)}")
    report.append(f"  ✅ OK:                                 {len(ok)}")
    report.append("")

    # ─── Таблица всех файлов ───
    report.append(sep)
    report.append("  ОБЗОР ВСЕХ ФАЙЛОВ (отсортированы по количеству строк)")
    report.append(sep)
    report.append("")
    report.append(f"  {'Файл':<60} {'Строк':>7}  {'Длинных':>8}  {'Статус'}")
    report.append(f"  {'-'*60} {'-'*7}  {'-'*8}  {'-'*20}")

    sorted_by_lines = sorted(all_data, key=lambda x: x["line_count"], reverse=True)
    for d in sorted_by_lines:
        report.append(
            f"  {d['rel_path']:<60} {d['line_count']:>7}  {d['long_lines_count']:>8}  {d['severity']}"
        )
    report.append("")

    # ─── Файлы > 500 строк ───
    if files_over_500:
        report.append(sep)
        report.append(f"  ФАЙЛЫ, ПРЕВЫШАЮЩИЕ {MAX_FILE_LINES} СТРОК")
        report.append(sep)
        report.append("")
        for d in sorted(files_over_500, key=lambda x: x["line_count"], reverse=True):
            report.append(f"  📄 {d['rel_path']}")
            report.append(f"     Строк: {d['line_count']}  |  Превышение: +{d['line_count'] - MAX_FILE_LINES}")
            if d["ast_info"]:
                classes = [c["name"] for c in d["ast_info"]["classes"]]
                funcs = [f["name"] for f in d["ast_info"]["top_level_functions"]]
                if classes:
                    report.append(f"     Классы: {', '.join(classes)}")
                if funcs:
                    report.append(f"     Функции верхнего уровня: {', '.join(funcs)}")
            report.append("")
    else:
        report.append(sep)
        report.append(f"  ✅ Нет файлов, превышающих {MAX_FILE_LINES} строк!")
        report.append(sep)
        report.append("")

    # ─── Детальный анализ файлов с проблемами ───
    problem_files = [d for d in all_data if d["needs_refactoring"]]
    if problem_files:
        report.append(sep)
        report.append("  ДЕТАЛЬНЫЙ АНАЛИЗ ФАЙЛОВ, ТРЕБУЮЩИХ РЕФАКТОРИНГА")
        report.append(sep)
        report.append("")

        for d in sorted(problem_files, key=lambda x: (
            0 if x["severity"] == "🔴 КРИТИЧНО" else
            1 if x["severity"] == "🟡 ТРЕБУЕТ ВНИМАНИЯ" else 2,
            -x["line_count"]
        )):
            report.append(sep2)
            report.append(f"  📄 {d['rel_path']}  [{d['severity']}]")
            report.append(f"     Строк: {d['line_count']}")
            report.append(sep2)

            # Структура файла
            if d["ast_info"]:
                ast_info = d["ast_info"]
                report.append("")
                report.append("     📋 Структура файла:")
                if ast_info["classes"]:
                    for cls in ast_info["classes"]:
                        report.append(
                            f"        Класс: {cls['name']} "
                            f"({cls['lines']} строк, {cls['method_count']} методов, "
                            f"строка {cls['start_line']})"
                        )
                        for method in cls["methods"]:
                            marker = " ⚠️" if method["lines"] > MAX_METHOD_LINES else ""
                            report.append(
                                f"          - {method['name']}() "
                                f"[{method['lines']} строк, "
                                f"{method['params']} парам., "
                                f"сложн. ≈{method['complexity']}]{marker}"
                            )
                if ast_info["top_level_functions"]:
                    report.append("        Функции верхнего уровня:")
                    for func in ast_info["top_level_functions"]:
                        marker = " ⚠️" if func["lines"] > MAX_FUNCTION_LINES else ""
                        report.append(
                            f"          - {func['name']}() "
                            f"[{func['lines']} строк, "
                            f"{func['params']} парам., "
                            f"сложн. ≈{func['complexity']}]{marker}"
                        )

            # Ответственности
            if d["responsibilities"]:
                report.append("")
                report.append("     🔍 Обнаруженные категории ответственностей:")
                for cat, keywords in d["responsibilities"].items():
                    kw_str = ", ".join(keywords[:5])
                    if len(keywords) > 5:
                        kw_str += f" ... (+{len(keywords)-5})"
                    report.append(f"        • {cat}: [{kw_str}]")

            # SRP нарушения
            if d["srp_issues"]:
                report.append("")
                report.append("     🏗️  Нарушения принципов проектирования:")
                for issue in d["srp_issues"]:
                    report.append(f"        {issue}")

            # Рекомендации
            if d["suggestions"]:
                report.append("")
                report.append("     💡 Рекомендации по рефакторингу:")
                for s in d["suggestions"]:
                    report.append(f"        {s}")

            # Примеры длинных строк (если есть)
            if d["long_lines"] and d["long_lines_count"] <= 10:
                report.append("")
                report.append(f"     📏 Строки длиннее {MAX_LINE_LENGTH} символов:")
                for line_no, length, preview in d["long_lines"]:
                    report.append(f"        Строка {line_no} ({length} симв.): {preview}...")
            elif d["long_lines_count"] > 10:
                report.append("")
                report.append(
                    f"     📏 {d['long_lines_count']} строк длиннее {MAX_LINE_LENGTH} символов "
                    f"(показаны первые 5):"
                )
                for line_no, length, preview in d["long_lines"][:5]:
                    report.append(f"        Строка {line_no} ({length} симв.): {preview}...")

            report.append("")

    # ─── Общие рекомендации ───
    report.append(sep)
    report.append("  ОБЩИЕ РЕКОМЕНДАЦИИ")
    report.append(sep)
    report.append("")

    if critical:
        report.append("  🔴 СРОЧНЫЙ РЕФАКТОРИНГ (критичные файлы):")
        for d in critical:
            report.append(f"     • {d['rel_path']} ({d['line_count']} строк)")
        report.append("")

    if warnings:
        report.append("  🟡 ПЛАНОВЫЙ РЕФАКТОРИНГ (требуют внимания):")
        for d in warnings:
            report.append(f"     • {d['rel_path']} ({d['line_count']} строк)")
        report.append("")

    report.append("  📚 ЛУЧШИЕ ПРАКТИКИ:")
    report.append(f"     • Максимальная длина файла: {MAX_FILE_LINES} строк")
    report.append(f"     • Максимальная длина строки: {MAX_LINE_LENGTH} символов")
    report.append(f"     • Максимальная длина функции: {MAX_FUNCTION_LINES} строк")
    report.append(f"     • Максимальная длина метода: {MAX_METHOD_LINES} строк")
    report.append(f"     • Максимум классов в файле: {MAX_CLASSES_PER_FILE}")
    report.append(f"     • Максимум функций верхнего уровня: {MAX_TOP_LEVEL_FUNCTIONS_PER_FILE}")
    report.append(f"     • Максимум методов в классе: {MAX_METHODS_PER_CLASS}")
    report.append(f"     • Максимум параметров функции: {MAX_PARAMS_PER_FUNCTION}")
    report.append(f"     • Принцип единой ответственности (SRP): один файл = одна обязанность")
    report.append("")
    report.append(sep)
    report.append(f"  Отчёт создан: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(sep)

    return "\n".join(report)


def main():
    print(f"🔍 Сканирование директории: {SRC_DIR}")
    print()

    if not os.path.isdir(SRC_DIR):
        print(f"❌ Директория не найдена: {SRC_DIR}")
        sys.exit(1)

    # Создаём директорию для вывода, если не существует
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Сканируем файлы
    py_files = scan_directory(SRC_DIR)
    if not py_files:
        print(f"❌ Python-файлы не найдены в {SRC_DIR}")
        sys.exit(1)

    print(f"📁 Найдено {len(py_files)} Python-файлов")
    print()

    # Анализируем каждый файл
    all_data = []
    for filepath in py_files:
        rel = os.path.relpath(filepath, SRC_DIR)
        print(f"  Анализ: {rel}")
        data = analyze_file(filepath, SRC_DIR)
        all_data.append(data)

    print()
    print("📊 Формирование отчёта...")

    # Генерируем отчёт
    report = format_report(all_data, SRC_DIR)

    # Записываем в файл
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"✅ Отчёт сохранён: {OUTPUT_FILE}")
    print()

    # Краткая сводка в консоль
    files_over = [d for d in all_data if d["line_count"] > MAX_FILE_LINES]
    files_refactor = [d for d in all_data if d["needs_refactoring"]]

    print(f"  Всего файлов:                    {len(all_data)}")
    print(f"  Файлов > {MAX_FILE_LINES} строк:              {len(files_over)}")
    print(f"  Файлов, требующих рефакторинга:  {len(files_refactor)}")
    print(f"  Общее количество строк:          {sum(d['line_count'] for d in all_data)}")


if __name__ == "__main__":
    main()

    