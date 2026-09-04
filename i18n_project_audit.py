#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SOURCE_EXTENSIONS = {
    ".py",
    ".ts", ".tsx", ".js", ".jsx",
    ".json",
    ".html", ".htm",
    ".jinja", ".jinja2", ".j2",
    ".md", ".txt",
    ".css", ".scss",
}

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
    "uploads",
    "storage",
    "media",
    "backups",
    "archive",
    "archives",
    # Артефакты обработки договоров, временные результаты,
    # служебные скрипты и тестовые данные не относятся к UI i18n scope.
    "artifacts",
    "output",
    "audit-output",
    "scripts",
    "tests",
    "test",
    "fixtures",
    "mocks",
    "examples",
    "samples",
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

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES_PER_FILE = 500
PROGRESS_EVERY_FILES = 100

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
QUOTED_RU_LINE_RE = re.compile(r"""(?P<quote>["'`])(?P<text>.*?[А-Яа-яЁё].*?)(?P=quote)""")

JSX_VISIBLE_TEXT_LINE_RE = re.compile(
    r""">(?P<text>[^<>{}\n]*[А-Яа-яЁё][^<>{}\n]*)<"""
)

JSX_ATTRIBUTE_LINE_RE = re.compile(
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

UI_OBJECT_LINE_RE = re.compile(
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

HTTP_EXCEPTION_LINE_RE = re.compile(
    r"""HTTPException\s*\(.*?(?:detail|message)\s*=\s*["'](?P<text>.*?[А-Яа-яЁё].*?)["']""",
    re.IGNORECASE,
)

API_RESPONSE_LINE_RE = re.compile(
    r"""(?:detail|message|error|title|description|reason)\s*[:=]\s*["'](?P<text>.*?[А-Яа-яЁё].*?)["']""",
    re.IGNORECASE,
)

LOGGER_LINE_RE = re.compile(
    r"""(?:logger|logging)\.(?:debug|info|warning|warn|error|exception|critical)\s*\(\s*["'](?P<text>.*?[А-Яа-яЁё].*?)["']""",
    re.IGNORECASE,
)

TEST_RE = re.compile(
    r"""(?:^|/)(?:tests?|__tests__|fixtures?|mocks?|samples?|examples?)(?:/|$)|
    (?:_test\.py$|\.spec\.[jt]sx?$|\.test\.[jt]sx?$)""",
    re.IGNORECASE | re.VERBOSE,
)

URL_RE = re.compile(r"^(https?://|www\.|mailto:|tel:|/|#)")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
CODELIKE_RE = re.compile(r"^[A-Z0-9_.:-]+$")
CLASSLIKE_RE = re.compile(r"^[a-z0-9_:/.\-[\]()%]+$", re.IGNORECASE)

EMAIL_WORDS = {
    "email", "emails", "mail", "mailer",
    "notification", "notifications", "template", "templates",
}

EXPORT_WORDS = {
    "export", "exports", "report", "reports",
    "pdf", "docx", "xlsx", "excel", "word",
}


def normalize_text(value: str) -> str:
    value = value.replace("\\n", " ").replace("\\t", " ")
    return re.sub(r"\s+", " ", value).strip()


def is_output_inside_root(root: Path, output_dir: Path) -> bool:
    try:
        output_dir.relative_to(root)
        return True
    except ValueError:
        return False


def is_skipped_path(path: Path, excluded_output_dir: Path | None) -> bool:
    if excluded_output_dir is not None:
        try:
            path.relative_to(excluded_output_dir)
            return True
        except ValueError:
            pass

    if any(part in SKIP_DIRS for part in path.parts):
        return True

    name = path.name.lower()

    if name in SKIP_FILE_NAMES or name.startswith(".env"):
        return True

    return any(name.endswith(suffix) for suffix in SKIP_SUFFIXES)


def iter_source_files(
    root: Path,
    excluded_output_dir: Path | None,
) -> Iterator[Path]:
    for current_root, dir_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current_root)

        dir_names[:] = [
            directory
            for directory in dir_names
            if not is_skipped_path(current_path / directory, excluded_output_dir)
        ]

        for file_name in file_names:
            path = current_path / file_name

            if is_skipped_path(path, excluded_output_dir):
                continue

            if path.suffix.lower() not in SOURCE_EXTENSIONS:
                continue

            try:
                if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue

            yield path


def safe_read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def get_project_area(relative: Path) -> str:
    suffix = relative.suffix.lower()

    if suffix in {".ts", ".tsx", ".js", ".jsx", ".css", ".scss"}:
        return "frontend"

    if suffix in {".py", ".jinja", ".jinja2", ".j2"}:
        return "backend"

    return "shared_or_content"


def get_subsystem(relative: Path) -> str:
    lower = str(relative).lower()
    parts = set(re.split(r"[/_.-]+", lower))

    if TEST_RE.search(lower):
        return "test_or_fixture"

    if parts & EMAIL_WORDS:
        return "email"

    if parts & EXPORT_WORDS:
        return "export"

    if any(value in lower for value in ("celery", "/tasks/", "_task", "worker")):
        return "async_or_celery"

    if any(value in lower for value in ("/api/", "/endpoints/", "/routers/", "endpoint")):
        return "api"

    if any(value in lower for value in ("/components/", "/component/")):
        return "component"

    if any(value in lower for value in ("/pages/", "/screens/", "/views/")):
        return "page"

    return "general"


def probably_technical(text: str, line: str) -> bool:
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
        "re.compile(",
        "re.search(",
        "re.match(",
        "re.fullmatch(",
        "re.findall(",
        "re.finditer(",
    )):
        return True

    return any(marker in lower_line for marker in (
        "data-testid",
        "class=",
        "classname=",
        "import ",
        "from ",
    ))


def classify_line(relative: Path, line: str, text: str) -> tuple[str, str, str]:
    suffix = relative.suffix.lower()
    subsystem = get_subsystem(relative)
    lower = line.lower()

    if subsystem == "test_or_fixture":
        return "content_or_test", "ignore", "test_or_fixture"

    if suffix == ".py":
        if LOGGER_LINE_RE.search(line):
            return "backend_internal", "ignore", "backend_log_internal"

        if probably_technical(text, line):
            return "content_or_test", "ignore", "technical_literal"

        if subsystem == "email":
            return "email_export", "high", "email_visible_text"

        if subsystem == "export":
            return "email_export", "high", "export_visible_text"

        if HTTP_EXCEPTION_LINE_RE.search(line):
            return "backend_user_facing", "high", "api_http_exception"

        if API_RESPONSE_LINE_RE.search(line):
            return "backend_user_facing", "high", "api_or_validation_message"

        if subsystem in {"api", "async_or_celery"}:
            return "backend_user_facing", "medium", "api_or_task_review"

        if probably_technical(text, line):
            return "content_or_test", "ignore", "technical_literal"

        return "backend_internal", "medium", "backend_string_review"

    if suffix in {".html", ".htm", ".jinja", ".jinja2", ".j2"}:
        if subsystem == "email":
            return "email_export", "high", "email_template_visible_text"

        if subsystem == "export":
            return "email_export", "high", "export_template_visible_text"

        return "frontend_ui", "high", "html_template_visible_text"

    if suffix in {".tsx", ".jsx", ".ts", ".js"}:
        if JSX_ATTRIBUTE_LINE_RE.search(line):
            return "frontend_ui", "high", "jsx_accessibility_or_input"

        if JSX_VISIBLE_TEXT_LINE_RE.search(line):
            return "frontend_ui", "high", "jsx_visible_text"

        if UI_OBJECT_LINE_RE.search(line):
            return "frontend_ui", "high", "frontend_ui_object"

        if any(token in lower for token in (
            "toast", "notification", "alert", "dialog",
            "modal", "confirm", "snackbar", "message.",
        )):
            return "frontend_ui", "high", "frontend_notification"

        if probably_technical(text, line):
            return "content_or_test", "ignore", "technical_literal"

        return "frontend_ui", "medium", "frontend_string_review"

    if suffix == ".json":
        if any(token in str(relative).lower() for token in ("locale", "i18n", "translation")):
            return "content_or_test", "ignore", "existing_translation_resource"

        return "content_or_test", "medium", "json_content_needs_review"

    return "content_or_test", "medium", "content_needs_review"


def scan_file(root: Path, path: Path) -> list[dict[str, Any]]:
    content = safe_read(path)

    if content is None or not CYRILLIC_RE.search(content):
        return []

    relative = path.relative_to(root)
    results: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if not CYRILLIC_RE.search(raw_line):
            continue

        line = raw_line.strip()

        patterns: list[re.Pattern[str]] = [QUOTED_RU_LINE_RE]

        if path.suffix.lower() in {".tsx", ".jsx", ".html", ".htm", ".jinja", ".jinja2", ".j2"}:
            patterns.extend([
                JSX_VISIBLE_TEXT_LINE_RE,
                JSX_ATTRIBUTE_LINE_RE,
                UI_OBJECT_LINE_RE,
            ])

        for pattern in patterns:
            for match in pattern.finditer(raw_line):
                text = normalize_text(match.group("text"))

                if not text or not CYRILLIC_RE.search(text):
                    continue

                key = (line_number, text)

                if key in seen:
                    continue

                seen.add(key)

                report_group, priority, category = classify_line(
                    relative,
                    line,
                    text,
                )

                results.append({
                    "report_group": report_group,
                    "priority": priority,
                    "category": category,
                    "project_area": get_project_area(relative),
                    "subsystem": get_subsystem(relative),
                    "file": str(relative),
                    "line": line_number,
                    "extension": path.suffix.lower(),
                    "text": text,
                    "code": line[:700],
                })

                if len(results) >= MAX_CANDIDATES_PER_FILE:
                    return results

    return results


def load_package_json(
    root: Path,
    excluded_output_dir: Path | None,
) -> dict[str, Any]:
    """
    Находит manifest основного frontend-приложения.

    Приоритет намеренный: frontend/package.json должен быть выбран
    раньше scripts/package.json и любых package.json из tooling-папок.
    """
    preferred_paths = [
        root / "frontend" / "package.json",
        root / "client" / "package.json",
        root / "web" / "package.json",
        root / "package.json",
    ]

    checked: set[Path] = set()

    for manifest_path in preferred_paths:
        if not manifest_path.is_file():
            continue

        checked.add(manifest_path.resolve())
        content = safe_read(manifest_path)

        if not content:
            continue

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            print(
                f"[warning] Некорректный JSON в {manifest_path}: {exc}",
                file=sys.stderr,
                flush=True,
            )

    for current_root, dir_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current_root)

        dir_names[:] = [
            directory
            for directory in dir_names
            if not is_skipped_path(
                current_path / directory,
                excluded_output_dir,
            )
        ]

        if "package.json" not in file_names:
            continue

        manifest_path = current_path / "package.json"

        if manifest_path.resolve() in checked:
            continue

        content = safe_read(manifest_path)

        if not content:
            continue

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            print(
                f"[warning] Некорректный JSON в {manifest_path}: {exc}",
                file=sys.stderr,
                flush=True,
            )

    return {}


def detect_technologies(package_json: dict[str, Any]) -> dict[str, list[str]]:
    deps: dict[str, Any] = {}
    deps.update(package_json.get("dependencies", {}))
    deps.update(package_json.get("devDependencies", {}))

    groups = {
        "frontend_framework": ["react", "next", "vite", "vue", "svelte"],
        "frontend_i18n": ["i18next", "react-i18next", "react-intl", "@formatjs/intl"],
        "frontend_routing": ["react-router-dom", "@tanstack/react-router"],
        "frontend_ui": ["@mui/material", "antd", "@chakra-ui/react", "@mantine/core", "tailwindcss"],
        "frontend_tests": ["vitest", "jest", "@playwright/test", "cypress", "@testing-library/react"],
    }

    return {
        group: [package for package in packages if package in deps]
        for group, packages in groups.items()
        if any(package in deps for package in packages)
    }


def make_backlog(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        if row["priority"] != "ignore":
            grouped[(row["report_group"], row["text"])].append(row)

    result = []

    for (group, text), items in grouped.items():
        first = items[0]

        if group == "frontend_ui":
            namespace = "common" if first["subsystem"] in {"component", "general"} else first["subsystem"]
            action = "Создать i18n key и заменить user-facing строку на t('namespace.key')."
            owner = "Frontend + Product"
        elif group == "backend_user_facing":
            namespace = "errors"
            action = "Заменить текст на error_code/event_code + params; локализовать в frontend."
            owner = "Backend + Frontend"
        elif group == "email_export":
            namespace = first["subsystem"]
            action = "Вынести в серверный каталог переводов или template; передавать locale."
            owner = "Backend + Product"
        else:
            namespace = "review"
            action = "Проверить вручную: возможно, это контент, fixture или техническая строка."
            owner = "Product / Engineering"

        key_hint = re.sub(r"[^a-z0-9]+", "_", text.lower().replace("ё", "е")).strip("_")[:70]

        result.append({
            "workstream": group,
            "priority": first["priority"],
            "occurrences": len(items),
            "proposed_namespace": namespace,
            "proposed_key_hint": key_hint,
            "text": text,
            "first_file": first["file"],
            "first_line": first["line"],
            "recommended_action": action,
            "owner": owner,
        })

    rank = {"high": 0, "medium": 1}
    return sorted(
        result,
        key=lambda item: (rank.get(item["priority"], 9), -item["occurrences"], item["workstream"]),
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def write_summary(
    path: Path,
    root: Path,
    output_dir: Path,
    files_scanned: int,
    skipped_large: int,
    candidates: list[dict[str, Any]],
    technologies: dict[str, list[str]],
    backlog: list[dict[str, Any]],
) -> None:
    by_priority = Counter(item["priority"] for item in candidates)
    by_group = Counter(item["report_group"] for item in candidates)

    lines = [
        "# I18n Project Audit",
        "",
        f"Дата: {datetime.now(timezone.utc).isoformat()}",
        f"Корень проекта: `{root}`",
        f"Папка отчётов: `{output_dir}`",
        "",
        "## Масштаб",
        "",
        f"- Просканировано файлов: **{files_scanned}**",
        f"- Пропущено крупных файлов (> {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB): **{skipped_large}**",
        f"- Найдено кандидатов: **{len(candidates)}**",
        f"- Высокий приоритет: **{by_priority.get('high', 0)}**",
        f"- Средний приоритет: **{by_priority.get('medium', 0)}**",
        f"- Исключено как логи, тесты или технические строки: **{by_priority.get('ignore', 0)}**",
        "",
        "## По потокам",
        "",
        f"- Frontend UI: **{by_group.get('frontend_ui', 0)}**",
        f"- Backend user-facing: **{by_group.get('backend_user_facing', 0)}**",
        f"- Email и exports: **{by_group.get('email_export', 0)}**",
        f"- Backend internal: **{by_group.get('backend_internal', 0)}**",
        f"- Контент, fixtures, документация: **{by_group.get('content_or_test', 0)}**",
        "",
        "## Технологии",
        "",
    ]

    if technologies:
        for group, packages in technologies.items():
            lines.append(f"- **{group}:** {', '.join(packages)}")
    else:
        lines.append("- package.json не найден или зависимости не распознаны.")

    lines.extend([
        "",
        "## Ограничения",
        "",
        "- Скрипт не сканирует собственную output-папку.",
        "- Файлы больше 2 MB намеренно пропускаются, чтобы не анализировать generated data, dumps и крупные fixtures.",
        "- На одном файле анализ ограничен 500 кандидатами.",
        "- Многострочные JavaScript/Python literals могут требовать отдельной ручной проверки или AST-аудита.",
        "",
        "## Первые задачи",
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
        description="Быстрый и безопасный статический i18n-аудит frontend + backend."
    )
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--out-dir", default="./i18n-project-audit")
    args = parser.parse_args()

    root = Path(args.project_dir).expanduser().resolve()
    output_dir = Path(args.out_dir).expanduser().resolve()

    if not root.is_dir():
        raise SystemExit(f"Каталог проекта не найден: {root}")

    excluded_output_dir = output_dir if is_output_inside_root(root, output_dir) else None

    candidates: list[dict[str, Any]] = []
    source_files_scanned = 0
    large_files_skipped = 0

    for path in iter_source_files(root, excluded_output_dir):
        try:
            if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                large_files_skipped += 1
                continue
        except OSError:
            continue

        source_files_scanned += 1

        if source_files_scanned % PROGRESS_EVERY_FILES == 0:
            print(
                f"[progress] files={source_files_scanned}, candidates={len(candidates)}",
                file=sys.stderr,
                flush=True,
            )

        candidates.extend(scan_file(root, path))

    priority_order = {"high": 0, "medium": 1, "ignore": 2}
    candidates.sort(
        key=lambda row: (
            priority_order.get(row["priority"], 9),
            row["report_group"],
            row["file"],
            row["line"],
        )
    )

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        groups[row["report_group"]].append(row)

    technologies = detect_technologies(load_package_json(root, excluded_output_dir))
    backlog = make_backlog(candidates)

    output_dir.mkdir(parents=True, exist_ok=True)

    candidate_fields = [
        "report_group",
        "priority",
        "category",
        "project_area",
        "subsystem",
        "file",
        "line",
        "extension",
        "text",
        "code",
    ]
    backlog_fields = [
        "workstream", "priority", "occurrences",
        "proposed_namespace", "proposed_key_hint", "text",
        "first_file", "first_line", "recommended_action", "owner",
    ]

    write_csv(output_dir / "all_candidates.csv", candidates, candidate_fields)
    write_csv(output_dir / "frontend_ui_strings.csv", groups["frontend_ui"], candidate_fields)
    write_csv(output_dir / "backend_user_facing_strings.csv", groups["backend_user_facing"], candidate_fields)
    write_csv(output_dir / "backend_internal_strings.csv", groups["backend_internal"], candidate_fields)
    write_csv(output_dir / "email_export_strings.csv", groups["email_export"], candidate_fields)
    write_csv(output_dir / "content_or_test_strings.csv", groups["content_or_test"], candidate_fields)
    write_csv(output_dir / "i18n_migration_backlog.csv", backlog, backlog_fields)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(root),
        "output_dir": str(output_dir),
        "limits": {
            "max_file_size_bytes": MAX_FILE_SIZE_BYTES,
            "max_candidates_per_file": MAX_CANDIDATES_PER_FILE,
        },
        "summary": {
            "source_files_scanned": source_files_scanned,
            "large_files_skipped": large_files_skipped,
            "total_candidates": len(candidates),
            "by_priority": dict(Counter(row["priority"] for row in candidates)),
            "by_report_group": dict(Counter(row["report_group"] for row in candidates)),
            "by_category": dict(Counter(row["category"] for row in candidates)),
        },
        "technologies": technologies,
        "candidates": candidates,
    }

    (output_dir / "i18n_project_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_summary(
        output_dir / "i18n_project_audit_summary.md",
        root,
        output_dir,
        source_files_scanned,
        large_files_skipped,
        candidates,
        technologies,
        backlog,
    )

    print(f"Готово. Просканировано файлов: {source_files_scanned}")
    print(f"Найдено кандидатов: {len(candidates)}")
    print(f"Отчёты: {output_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    
    