#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


# =========================
# Конфигурация
# =========================

SOURCE_EXTENSIONS = {
    ".py",
    ".ts", ".tsx", ".js", ".jsx",
    ".json",
    ".html", ".htm",
    ".jinja", ".jinja2", ".j2",
    ".md", ".txt",
}

FRONTEND_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}
TEMPLATE_EXTENSIONS = {".html", ".htm", ".jinja", ".jinja2", ".j2"}

SKIP_DIRS = {
    ".git",
    ".github",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".vite",
    ".cache",
    ".turbo",
    "coverage",
    "storybook-static",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "site-packages",
    "vendor",
    "migrations",
    "alembic",
}

SKIP_FILE_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "poetry.lock",
    "uv.lock",
}

SKIP_SUFFIXES = {
    ".min.js",
    ".min.css",
    ".map",
    ".pyc",
}

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
QUOTED_RU_RE = re.compile(
    r"""(?P<quote>["'`])(?P<text>(?:\\.|(?!\1).)*?[А-Яа-яЁё](?:\\.|(?!\1))*?)(?P=quote)"""
)

JSX_VISIBLE_TEXT_RE = re.compile(
    r""">(?P<text>[^<>{}\n]*[А-Яа-яЁё][^<>{}\n]*)<"""
)

JSX_ATTRIBUTE_RE = re.compile(
    r"""(?P<attribute>
        aria-label|aria-description|aria-valuetext|
        alt|title|placeholder|label|helperText|
        description|tooltip|emptyText|noOptionsText|
        loadingText|confirmText|cancelText|submitText|
        content
    )
    \s*=\s*
    (?P<quote>["'`])
    (?P<text>.*?[А-Яа-яЁё].*?)
    (?P=quote)""",
    re.IGNORECASE | re.VERBOSE,
)

UI_OBJECT_RE = re.compile(
    r"""(?P<key>
        label|title|description|message|text|name|
        hint|error|success|warning|caption|
        placeholder|tooltip|empty_text
    )
    \s*[:=]\s*
    (?P<quote>["'`])
    (?P<text>.*?[А-Яа-яЁё].*?)
    (?P=quote)""",
    re.IGNORECASE | re.VERBOSE,
)

URL_RE = re.compile(r"^(https?://|www\.|mailto:|tel:|/|#)")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
CODELIKE_RE = re.compile(r"^[A-Z0-9_.:-]+$")
CLASSLIKE_RE = re.compile(r"^[a-z0-9_:/.\-[\]()%]+$", re.IGNORECASE)

TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|fixtures?|mocks?|samples?|examples?)(/|$)|"
    r"(_test\.py$|\.test\.[jt]sx?$|\.spec\.[jt]sx?$)",
    re.IGNORECASE,
)

EMAIL_WORDS = {
    "email", "emails", "mail", "mailer",
    "notification", "notifications",
}

EXPORT_WORDS = {
    "export", "exports", "report", "reports",
    "pdf", "docx", "xlsx", "excel", "word",
}


# =========================
# Модель результата
# =========================

@dataclass
class Candidate:
    report_group: str
    priority: str
    category: str
    project_area: str
    subsystem: str
    file: str
    line: int
    text: str
    code: str
    suggested_action: str


# =========================
# Общие функции
# =========================

def normalize_text(value: str) -> str:
    value = value.replace("\\n", " ").replace("\\t", " ")
    return re.sub(r"\s+", " ", value).strip()


def read_utf8(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def is_skipped(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return True

    name = path.name.lower()

    if name in SKIP_FILE_NAMES:
        return True

    if name.startswith(".env"):
        return True

    return any(name.endswith(suffix) for suffix in SKIP_SUFFIXES)


def line_at(source: str, line_number: int) -> str:
    lines = source.splitlines()
    if 1 <= line_number <= len(lines):
        return lines[line_number - 1].strip()
    return ""


def line_number_at(source: str, position: int) -> int:
    return source.count("\n", 0, position) + 1


def path_has_any_word(relative: Path, words: set[str]) -> bool:
    path_words = set(re.split(r"[/_.\-]+", str(relative).lower()))
    return bool(path_words & words)


def classify_area(relative: Path) -> str:
    lower = str(relative).lower()
    suffix = relative.suffix.lower()

    if suffix in FRONTEND_EXTENSIONS:
        if any(word in lower for word in (
            "frontend", "client", "components", "pages",
            "screens", "views", "hooks",
        )):
            return "frontend"
        return "frontend"

    if suffix in {".py", ".jinja", ".jinja2", ".j2"}:
        return "backend"

    return "shared_or_content"


def classify_subsystem(relative: Path) -> str:
    lower = str(relative).lower()

    if TEST_PATH_RE.search(lower):
        return "test_or_fixture"

    if path_has_any_word(relative, EMAIL_WORDS):
        return "email"

    if path_has_any_word(relative, EXPORT_WORDS):
        return "export"

    if any(word in lower for word in ("celery", "tasks/", "_task", "worker")):
        return "async_or_celery"

    if any(word in lower for word in (
        "api/", "endpoints/", "routers/", "router",
        "controller", "views/",
    )):
        return "api"

    if any(word in lower for word in ("components/", "component/")):
        return "component"

    if any(word in lower for word in ("pages/", "screens/", "views/")):
        return "page"

    return "general"


def is_probably_technical(text: str, line: str) -> bool:
    text = normalize_text(text)
    lower_line = line.lower()

    if not text:
        return True

    if URL_RE.match(text) or UUID_RE.match(text):
        return True

    if CODELIKE_RE.match(text):
        return True

    if CLASSLIKE_RE.match(text) and " " not in text:
        return True

    if any(marker in lower_line for marker in (
        "data-testid",
        "class=",
        "classname=",
        "import ",
        "from ",
    )):
        return True

    return False


def add_candidate(
    result: list[Candidate],
    seen: set[tuple[str, int, str]],
    candidate: Candidate,
) -> None:
    key = (candidate.file, candidate.line, candidate.text)

    if key not in seen:
        seen.add(key)
        result.append(candidate)


# =========================
# Frontend и шаблоны
# =========================

def frontend_action(category: str) -> str:
    if category in {
        "jsx_visible_text",
        "jsx_attribute",
        "frontend_ui_object",
        "frontend_notification",
        "frontend_visible_logic",
    }:
        return "Вынести текст в i18n key и заменить отображение на t('namespace.key')."

    return "Проверить вручную: если строка видна пользователю, вынести в i18n key."


def scan_frontend_or_template(root: Path, path: Path, source: str) -> list[Candidate]:
    relative = path.relative_to(root)
    subsystem = classify_subsystem(relative)
    area = classify_area(relative)

    result: list[Candidate] = []
    seen: set[tuple[str, int, str]] = set()

    if subsystem == "test_or_fixture":
        report_group = "content_or_test"
        priority = "ignore"
    elif subsystem == "email":
        report_group = "email_export"
        priority = "high"
    elif subsystem == "export":
        report_group = "email_export"
        priority = "high"
    else:
        report_group = "frontend_ui"
        priority = "high"

    patterns: list[tuple[re.Pattern[str], str]] = []

    if path.suffix.lower() in {".tsx", ".jsx"} | TEMPLATE_EXTENSIONS:
        patterns.extend([
            (JSX_VISIBLE_TEXT_RE, "jsx_visible_text"),
            (JSX_ATTRIBUTE_RE, "jsx_attribute"),
        ])

    patterns.extend([
        (UI_OBJECT_RE, "frontend_ui_object"),
        (QUOTED_RU_RE, "frontend_visible_logic"),
    ])

    for pattern, category in patterns:
        for match in pattern.finditer(source):
            text = normalize_text(match.group("text"))

            if not text or not CYRILLIC_RE.search(text):
                continue

            line_number = line_number_at(source, match.start())
            line = line_at(source, line_number)

            if is_probably_technical(text, line):
                continue

            current_category = category
            current_priority = priority
            current_group = report_group

            lower_line = line.lower()

            if any(token in lower_line for token in (
                "toast", "notification", "snackbar",
                "alert", "dialog", "modal", "confirm",
            )):
                current_category = "frontend_notification"

            if subsystem == "test_or_fixture":
                current_group = "content_or_test"
                current_priority = "ignore"
                current_category = "test_or_fixture"

            add_candidate(
                result,
                seen,
                Candidate(
                    report_group=current_group,
                    priority=current_priority,
                    category=current_category,
                    project_area=area,
                    subsystem=subsystem,
                    file=str(relative),
                    line=line_number,
                    text=text,
                    code=line[:700],
                    suggested_action=frontend_action(current_category),
                ),
            )

    return result


# =========================
# Python AST: backend
# =========================

def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr

    return ""


def constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def keyword_string(call: ast.Call, names: set[str]) -> tuple[str, ast.AST] | None:
    for keyword in call.keywords:
        if keyword.arg in names:
            value = constant_string(keyword.value)
            if value is not None:
                return value, keyword.value
    return None


def context_contains_export_or_email(relative: Path, function_name: str) -> str | None:
    value = f"{relative} {function_name}".lower()

    if any(word in value for word in EMAIL_WORDS):
        return "email"

    if any(word in value for word in EXPORT_WORDS):
        return "export"

    return None


class PythonI18nVisitor(ast.NodeVisitor):
    def __init__(self, root: Path, path: Path, source: str) -> None:
        self.root = root
        self.path = path
        self.source = source
        self.relative = path.relative_to(root)
        self.subsystem = classify_subsystem(self.relative)
        self.area = "backend"
        self.function_stack: list[str] = []
        self.results: list[Candidate] = []
        self.seen: set[tuple[str, int, str]] = set()

    def current_function(self) -> str:
        return self.function_stack[-1] if self.function_stack else ""

    def add(
        self,
        node: ast.AST,
        text: str,
        report_group: str,
        priority: str,
        category: str,
        action: str,
    ) -> None:
        text = normalize_text(text)

        if not text or not CYRILLIC_RE.search(text):
            return

        line_number = getattr(node, "lineno", 1)
        line = line_at(self.source, line_number)

        add_candidate(
            self.results,
            self.seen,
            Candidate(
                report_group=report_group,
                priority=priority,
                category=category,
                project_area=self.area,
                subsystem=self.subsystem,
                file=str(self.relative),
                line=line_number,
                text=text,
                code=line[:700],
                suggested_action=action,
            ),
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> Any:
        name = dotted_name(node.func).lower()
        function_name = self.current_function()
        special_context = context_contains_export_or_email(
            self.relative,
            function_name,
        )

        # logger.info/error/warning/... — внутренний текст
        if any(name.endswith(f".{level}") for level in (
            "debug", "info", "warning", "warn",
            "error", "exception", "critical",
        )):
            if node.args:
                text = constant_string(node.args[0])
                if text:
                    self.add(
                        node,
                        text,
                        "backend_internal",
                        "ignore",
                        "backend_log_internal",
                        "Не переводить: внутренний лог. При необходимости стандартизировать язык логов отдельно.",
                    )

        # HTTPException(detail="...")
        if name.endswith("httpexception") or name == "httpexception":
            found = keyword_string(node, {"detail", "message"})
            if found:
                text, value_node = found
                self.add(
                    value_node,
                    text,
                    "backend_user_facing",
                    "high",
                    "api_http_exception",
                    "Заменить русский detail на error_code + params; frontend локализует текст по коду.",
                )

        # JSONResponse / response с message/detail/error
        if any(part in name for part in (
            "jsonresponse", "response", "apiresponse",
        )):
            found = keyword_string(node, {"content", "data"})
            if found and isinstance(found[1], ast.Dict):
                self.scan_response_dict(found[1])

        # Celery update_state(meta={...})
        if name.endswith("update_state"):
            found = keyword_string(node, {"meta"})
            if found and isinstance(found[1], ast.Dict):
                self.scan_task_meta(found[1])

        # Email и export: строковые аргументы в специальных функциях
        if special_context:
            for arg in node.args:
                text = constant_string(arg)
                if text:
                    category = (
                        "email_visible_text"
                        if special_context == "email"
                        else "export_visible_text"
                    )
                    self.add(
                        arg,
                        text,
                        "email_export",
                        "high",
                        category,
                        "Вынести в серверный шаблон/каталог переводов и выбирать по user.ui_locale или export_locale.",
                    )

        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> Any:
        if isinstance(node.exc, ast.Call):
            name = dotted_name(node.exc.func).lower()

            if any(token in name for token in (
                "valueerror", "validationerror",
                "businesserror", "domainerror",
                "apierror", "userfacingerror",
            )):
                for arg in node.exc.args:
                    text = constant_string(arg)
                    if text:
                        self.add(
                            arg,
                            text,
                            "backend_user_facing",
                            "high",
                            "backend_raised_user_message",
                            "Проверить, уходит ли исключение в API. Если да — заменить на error_code + params.",
                        )

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        export_or_email = context_contains_export_or_email(
            self.relative,
            self.current_function(),
        )

        if export_or_email:
            text = constant_string(node.value)
            if text:
                category = (
                    "email_visible_text"
                    if export_or_email == "email"
                    else "export_visible_text"
                )
                self.add(
                    node.value,
                    text,
                    "email_export",
                    "high",
                    category,
                    "Вынести в локализуемый серверный шаблон; язык брать из user/workspace/export locale.",
                )

        self.generic_visit(node)

    def scan_response_dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            key_text = constant_string(key) if key else None
            value_text = constant_string(value)

            if key_text in {"detail", "message", "error", "title", "description"} and value_text:
                self.add(
                    value,
                    value_text,
                    "backend_user_facing",
                    "high",
                    "api_response_message",
                    "Заменить текстовый response field на стабильный code + params; текст локализовать в UI.",
                )

    def scan_task_meta(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            key_text = constant_string(key) if key else None
            value_text = constant_string(value)

            if key_text in {"message", "detail", "error", "status_text"} and value_text:
                self.add(
                    value,
                    value_text,
                    "backend_user_facing",
                    "high",
                    "celery_task_status_message",
                    "Заменить пользовательский текст задачи на event_code/status_code + params.",
                )

    def visit_Constant(self, node: ast.Constant) -> Any:
        if not isinstance(node.value, str):
            return

        text = node.value

        if not CYRILLIC_RE.search(text):
            return

        if self.subsystem == "test_or_fixture":
            self.add(
                node,
                text,
                "content_or_test",
                "ignore",
                "test_or_fixture",
                "Не переводить как продуктовый UI; оставить в test fixture или sample data.",
            )
            return

        # Не создаём generic кандидат, если он уже распознан более точным вызовом.
        self.generic_visit(node)


def scan_python(root: Path, path: Path, source: str) -> list[Candidate]:
    relative = path.relative_to(root)

    try:
        tree = ast.parse(source, filename=str(relative))
    except SyntaxError:
        return []

    visitor = PythonI18nVisitor(root, path, source)
    visitor.visit(tree)

    # Дополнительный fallback для кириллицы в Python:
    # охватывает словари, константы и строки, которые AST-контекст
    # не смог уверенно классифицировать.
    known = {(item.line, item.text) for item in visitor.results}

    if classify_subsystem(relative) != "test_or_fixture":
        for match in QUOTED_RU_RE.finditer(source):
            text = normalize_text(match.group("text"))
            line_number = line_number_at(source, match.start())
            line = line_at(source, line_number)

            if (line_number, text) in known:
                continue

            if is_probably_technical(text, line):
                continue

            lower_line = line.lower()

            if "logger." in lower_line or "logging." in lower_line:
                group = "backend_internal"
                priority = "ignore"
                category = "backend_log_internal"
                action = "Не переводить: внутренний лог."
            elif any(token in lower_line for token in (
                "detail", "message", "error", "status",
                "response", "result", "progress",
            )):
                group = "backend_user_facing"
                priority = "medium"
                category = "backend_string_needs_flow_review"
                action = "Проверить API/Celery flow. Если текст уходит пользователю — заменить на code + params."
            else:
                group = "backend_internal"
                priority = "medium"
                category = "backend_string_needs_review"
                action = "Проверить вручную: лог, документация, доменные данные или будущий user-facing текст."

            visitor.add(
                type("Node", (), {"lineno": line_number})(),
                text,
                group,
                priority,
                category,
                action,
            )

    return visitor.results


# =========================
# Сканирование проекта
# =========================

def iter_source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if is_skipped(path):
            continue

        if path.suffix.lower() in SOURCE_EXTENSIONS:
            yield path


def scan_project(root: Path) -> tuple[list[Candidate], int]:
    candidates: list[Candidate] = []
    source_file_count = 0

    for path in sorted(iter_source_files(root)):
        source = read_utf8(path)

        if source is None:
            continue

        source_file_count += 1

        if not CYRILLIC_RE.search(source):
            continue

        suffix = path.suffix.lower()

        if suffix == ".py":
            candidates.extend(scan_python(root, path, source))
        else:
            candidates.extend(scan_frontend_or_template(root, path, source))

    priority_order = {"high": 0, "medium": 1, "ignore": 2}

    candidates.sort(
        key=lambda item: (
            priority_order.get(item.priority, 9),
            item.report_group,
            item.file,
            item.line,
        )
    )

    return candidates, source_file_count


# =========================
# Архитектурный обзор
# =========================

def load_package_json(root: Path) -> dict[str, Any]:
    paths = [root / "package.json"] + list(root.glob("*/package.json"))

    for path in paths:
        source = read_utf8(path)

        if not source:
            continue

        try:
            return json.loads(source)
        except json.JSONDecodeError:
            continue

    return {}


def detect_frontend_technologies(package_json: dict[str, Any]) -> dict[str, list[str]]:
    deps: dict[str, Any] = {}
    deps.update(package_json.get("dependencies", {}))
    deps.update(package_json.get("devDependencies", {}))

    groups = {
        "framework": ["react", "next", "vite"],
        "i18n": ["i18next", "react-i18next", "react-intl", "@lingui/core"],
        "routing": ["react-router-dom", "@tanstack/react-router"],
        "ui": ["@mui/material", "antd", "@chakra-ui/react", "@mantine/core", "tailwindcss"],
        "testing": ["vitest", "jest", "@playwright/test", "cypress", "@testing-library/react"],
    }

    return {
        group: [package for package in packages if package in deps]
        for group, packages in groups.items()
        if any(package in deps for package in packages)
    }


def find_architecture_markers(root: Path) -> dict[str, list[str]]:
    markers: dict[str, list[str]] = {
        "frontend_i18n_or_locale_files": [],
        "fastapi_or_api_files": [],
        "celery_or_task_files": [],
        "email_files": [],
        "export_files": [],
        "template_files": [],
    }

    for path in root.rglob("*"):
        if not path.is_file() or is_skipped(path):
            continue

        relative = path.relative_to(root)
        lower = str(relative).lower()
        suffix = path.suffix.lower()

        if any(word in lower for word in ("i18n", "locale", "translation", "intl")):
            markers["frontend_i18n_or_locale_files"].append(str(relative))

        if suffix == ".py":
            source = read_utf8(path) or ""
            source_lower = source.lower()

            if "fastapi" in source_lower or "apirouter" in source_lower:
                markers["fastapi_or_api_files"].append(str(relative))

            if "celery" in source_lower or "shared_task" in source_lower:
                markers["celery_or_task_files"].append(str(relative))

        if path_has_any_word(relative, EMAIL_WORDS):
            markers["email_files"].append(str(relative))

        if path_has_any_word(relative, EXPORT_WORDS):
            markers["export_files"].append(str(relative))

        if suffix in TEMPLATE_EXTENSIONS:
            markers["template_files"].append(str(relative))

    return {
        key: sorted(set(value))[:100]
        for key, value in markers.items()
    }


# =========================
# Отчёты
# =========================

def write_csv(path: Path, rows: list[Candidate]) -> None:
    fields = [
        "priority",
        "category",
        "project_area",
        "subsystem",
        "file",
        "line",
        "text",
        "code",
        "suggested_action",
    ]

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for row in rows:
            writer.writerow(asdict(row))


def make_backlog(rows: list[Candidate]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Candidate]] = defaultdict(list)

    for row in rows:
        if row.priority != "ignore":
            grouped[(row.report_group, row.text)].append(row)

    result: list[dict[str, Any]] = []

    for (group, text), items in grouped.items():
        first = items[0]
        occurrences = len(items)

        if group == "frontend_ui":
            namespace = (
                "common"
                if first.subsystem in {"general", "component"}
                else first.subsystem
            )
            target = "Frontend locale JSON"
        elif group == "backend_user_facing":
            namespace = "errors"
            target = "API code + frontend locale JSON"
        elif group == "email_export":
            namespace = first.subsystem
            target = "Backend templates/catalog by locale"
        else:
            namespace = "review"
            target = "Manual product decision"

        key_hint = re.sub(
            r"[^a-z0-9]+",
            "_",
            text.lower().replace("ё", "е"),
        ).strip("_")[:70]

        result.append({
            "workstream": group,
            "priority": first.priority,
            "occurrences": occurrences,
            "target": target,
            "suggested_namespace": namespace,
            "suggested_key_hint": key_hint,
            "text": text,
            "first_file": first.file,
            "first_line": first.line,
            "recommended_action": first.suggested_action,
        })

    priority_order = {"high": 0, "medium": 1}

    return sorted(
        result,
        key=lambda item: (
            priority_order.get(item["priority"], 9),
            -item["occurrences"],
            item["workstream"],
        ),
    )


def write_backlog(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "workstream",
        "priority",
        "occurrences",
        "target",
        "suggested_namespace",
        "suggested_key_hint",
        "text",
        "first_file",
        "first_line",
        "recommended_action",
    ]

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(
    path: Path,
    root: Path,
    source_files: int,
    candidates: list[Candidate],
    technologies: dict[str, list[str]],
    markers: dict[str, list[str]],
    backlog: list[dict[str, Any]],
) -> None:
    by_priority = Counter(item.priority for item in candidates)
    by_group = Counter(item.report_group for item in candidates)
    by_subsystem = Counter(item.subsystem for item in candidates)

    lines = [
        "# I18n Project Audit",
        "",
        f"Дата создания: {datetime.now(timezone.utc).isoformat()}",
        f"Корень проекта: `{root}`",
        "",
        "## Масштаб",
        "",
        f"- Исследовано файлов: **{source_files}**",
        f"- Всего найдено русскоязычных кандидатов: **{len(candidates)}**",
        f"- Высокий приоритет: **{by_priority.get('high', 0)}**",
        f"- Средний приоритет, нужен triage: **{by_priority.get('medium', 0)}**",
        f"- Исключено как логи, тесты или технические строки: **{by_priority.get('ignore', 0)}**",
        "",
        "## По потокам работ",
        "",
        f"- Frontend UI: **{by_group.get('frontend_ui', 0)}**",
        f"- Backend user-facing / API / Celery: **{by_group.get('backend_user_facing', 0)}**",
        f"- Email и exports: **{by_group.get('email_export', 0)}**",
        f"- Backend internal: **{by_group.get('backend_internal', 0)}**",
        f"- Контент, тесты и ручная классификация: **{by_group.get('content_or_test', 0)}**",
        "",
        "## По подсистемам",
        "",
    ]

    for subsystem, count in by_subsystem.most_common():
        lines.append(f"- `{subsystem}`: {count}")

    lines.extend([
        "",
        "## Обнаруженные frontend-технологии",
        "",
    ])

    if technologies:
        for group, packages in technologies.items():
            lines.append(f"- **{group}:** {', '.join(packages)}")
    else:
        lines.append("- package.json не найден либо технологии не определены.")

    lines.extend([
        "",
        "## Архитектурные маркеры",
        "",
    ])

    for marker, files in markers.items():
        lines.append(f"- **{marker}:** {len(files)} файлов")

    lines.extend([
        "",
        "## План внедрения",
        "",
        "1. Провести triage `i18n_migration_backlog.csv`: присвоить каждой строке статус `translate`, `error_code`, `keep_internal`, `document_content` или `test_fixture`.",
        "2. Внедрить `i18next + react-i18next`, базовый `en`, fallback `en`, затем перенести app shell, auth, navigation и общие UI-компоненты.",
        "3. Для FastAPI/Celery закрепить API-контракт: `code`, `params`, `trace_id`; не возвращать русские user-facing строки в `detail` и task meta.",
        "4. Добавить `user.ui_locale` и `workspace.default_locale`; язык интерфейса не связывать с `document_language` и `analysis_language`.",
        "5. Для email и экспортов передавать `locale` в задачу/рендерер, чтобы результат создавался в нужной локали и был воспроизводим.",
        "6. После миграции включить ESLint-правило против новых JSX literal strings и проверку полноты locale-файлов в CI.",
        "",
        "## Файлы отчёта",
        "",
        "- `frontend_ui_strings.csv` — фронтенд-кандидаты для переноса в translation keys.",
        "- `backend_user_facing_strings.csv` — API/FastAPI/Celery-кандидаты для перехода на `code + params`.",
        "- `backend_internal_strings.csv` — внутренние логи и строки, обычно не требующие перевода.",
        "- `email_export_strings.csv` — письма и экспортируемые документы.",
        "- `content_or_test_strings.csv` — fixtures, документация и строки, требующие ручного решения.",
        "- `i18n_migration_backlog.csv` — дедуплицированный рабочий backlog.",
        "",
        "## Ограничение аудита",
        "",
        "Статический анализ показывает вероятный scope, но не может гарантировать, что каждая backend-строка реально доходит до пользователя. Все строки среднего приоритета нужно проверить по API-flow, task result и UI-обработчикам.",
        "",
        "## Первые 30 задач",
        "",
    ])

    for item in backlog[:30]:
        lines.append(
            f"- **{item['occurrences']}x**, `{item['workstream']}`, "
            f"`{item['first_file']}:{item['first_line']}` — «{item['text']}»"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Статический i18n-аудит frontend + backend проекта."
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Корень проекта; по умолчанию текущая папка.",
    )
    parser.add_argument(
        "--out-dir",
        default="./i18n-project-audit",
        help="Папка для итоговых отчётов.",
    )
    args = parser.parse_args()

    root = Path(args.project_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()

    if not root.is_dir():
        raise SystemExit(f"Не найден каталог проекта: {root}")

    candidates, source_files = scan_project(root)
    groups: dict[str, list[Candidate]] = defaultdict(list)

    for candidate in candidates:
        groups[candidate.report_group].append(candidate)

    package_json = load_package_json(root)
    technologies = detect_frontend_technologies(package_json)
    markers = find_architecture_markers(root)
    backlog = make_backlog(candidates)

    out_dir.mkdir(parents=True, exist_ok=True)

    write_csv(out_dir / "all_candidates.csv", candidates)
    write_csv(out_dir / "frontend_ui_strings.csv", groups["frontend_ui"])
    write_csv(
        out_dir / "backend_user_facing_strings.csv",
        groups["backend_user_facing"],
    )
    write_csv(
        out_dir / "backend_internal_strings.csv",
        groups["backend_internal"],
    )
    write_csv(out_dir / "email_export_strings.csv", groups["email_export"])
    write_csv(
        out_dir / "content_or_test_strings.csv",
        groups["content_or_test"],
    )
    write_backlog(out_dir / "i18n_migration_backlog.csv", backlog)

    full_report = {
        "project_root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files_scanned": source_files,
        "technologies": technologies,
        "architecture_markers": markers,
        "summary": {
            "total_candidates": len(candidates),
            "by_priority": dict(Counter(item.priority for item in candidates)),
            "by_group": dict(Counter(item.report_group for item in candidates)),
            "by_category": dict(Counter(item.category for item in candidates)),
            "by_subsystem": dict(Counter(item.subsystem for item in candidates)),
        },
        "candidates": [asdict(item) for item in candidates],
    }

    (out_dir / "i18n_project_audit.json").write_text(
        json.dumps(full_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_summary(
        out_dir / "i18n_project_audit_summary.md",
        root,
        source_files,
        candidates,
        technologies,
        markers,
        backlog,
    )

    print(f"Готово. Проверено исходных файлов: {source_files}")
    print(f"Найдено кандидатов: {len(candidates)}")
    print(f"Отчёты созданы в: {out_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())



    