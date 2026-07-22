# src/scripts/import_global_instructions.py
"""
Import script: загружает global checks из файловой системы в БД.

Сканирует playbooks/global_checks/**/*.yaml → создаёт published platform versions
в global_instruction_versions.

Правила:
- Idempotent: если version с таким (instruction_code, source_sha256, owner_scope='platform')
  уже существует → skip (даже если статус archived/draft).
- Создаёт сразу в статусе 'published' (bootstrap платформенной библиотеки).
- НЕ архивирует существующие published versions — только добавляет новые sha256.
- Каждый файл — отдельная транзакция (изолированный rollback при ошибке).

Использование:
    python -m scripts.import_global_instructions
    python -m scripts.import_global_instructions --dry-run
    python -m scripts.import_global_instructions --path playbooks/global_checks
    python -m scripts.import_global_instructions --path playbooks/global_checks --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Добавляем src/ в sys.path для запуска как скрипта
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.logging import get_logger, setup_logging
from db.session import transactional_session
from db.repositories.global_instruction_version_repo import (
    GlobalInstructionVersionRepository,
)
from services.instruction_compiler import InstructionCompiler

setup_logging()
logger = get_logger(__name__)

# Корень проекта — на уровень выше src/
_PROJECT_ROOT = _SRC.parent
_DEFAULT_GLOBAL_CHECKS_PATH = _PROJECT_ROOT / "playbooks" / "global_checks"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _compute_payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _find_yaml_files(base_path: Path) -> list[Path]:
    """Рекурсивно найти все .yaml/.yml файлы, отсортированные по пути."""
    files: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        files.extend(base_path.rglob(ext))
    return sorted(files)


def _parse_yaml_file(path: Path) -> tuple[dict, str] | None:
    """
    Прочитать и распарсить YAML файл.

    Returns:
        (parsed_dict, raw_content) или None если файл невалидный.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw)
        if not isinstance(parsed, dict):
            logger.warning(
                "import_global_instructions: skipping non-dict YAML",
                path=str(path),
                got_type=type(parsed).__name__,
            )
            return None
        return parsed, raw
    except yaml.YAMLError as exc:
        logger.error(
            "import_global_instructions: YAML parse error",
            path=str(path),
            error=str(exc),
        )
        return None
    except OSError as exc:
        logger.error(
            "import_global_instructions: file read error",
            path=str(path),
            error=str(exc),
        )
        return None


def _extract_instruction_code(parsed: dict, path: Path) -> str | None:
    """
    Извлечь instruction_code из YAML.

    Проверяем поля в порядке приоритета: 'id', 'instruction_code', 'check_id'.
    """
    for field in ("id", "instruction_code", "check_id"):
        value = parsed.get(field)
        if value and isinstance(value, str) and value.strip():
            return value.strip()

    logger.warning(
        "import_global_instructions: no instruction code field found, skipping",
        path=str(path),
        available_keys=list(parsed.keys())[:10],
        tried_fields=["id", "instruction_code", "check_id"],
    )
    return None


def _extract_name(parsed: dict, instruction_code: str) -> str:
    """Извлечь человекочитаемое название инструкции."""
    for field in ("name", "title", "label"):
        value = parsed.get(field)
        if value and isinstance(value, str) and value.strip():
            return value.strip()[:300]
    return instruction_code


def _extract_group(parsed: dict) -> str | None:
    """Извлечь группу/категорию инструкции."""
    for field in ("group", "category", "topic_code", "topic"):
        value = parsed.get(field)
        if value and isinstance(value, str) and value.strip():
            return value.strip()[:100]
    return None


# ── Core import logic ─────────────────────────────────────────────────────────


async def _import_single_file(
    *,
    path: Path,
    compiler: InstructionCompiler,
    dry_run: bool,
) -> str:
    """
    Обработать один YAML файл в изолированной транзакции.

    Returns:
        'created' | 'skipped' | 'error'
    """
    parse_result = _parse_yaml_file(path)
    if parse_result is None:
        return "error"

    parsed, raw_content = parse_result

    instruction_code = _extract_instruction_code(parsed, path)
    if instruction_code is None:
        return "error"

    source_sha256 = _compute_sha256(raw_content)

    # Компилируем до открытия транзакции — чистая CPU операция
    compiled_payload: dict | None = None
    validation_report: dict | None = None
    compile_error: str | None = None

    try:
        compile_result = compiler.compile_global_instruction(
            instruction_code=instruction_code,
            source=parsed,
        )
        compiled_payload = compile_result.compiled_payload
        validation_report = compile_result.validation_report
    except Exception as exc:
        compile_error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "import_global_instructions: compile failed, will store without compiled_payload",
            instruction_code=instruction_code,
            path=str(path),
            error=compile_error,
        )
        validation_report = {
            "errors": [compile_error],
            "warnings": [],
            "compile_failed": True,
        }

    if dry_run:
        # В dry-run используем read-only сессию без транзакции
        from db.session import get_session
        async with get_session() as session:
            repo = GlobalInstructionVersionRepository(session)
            existing = await repo.get_by_instruction_code_and_sha256(
                instruction_code=instruction_code,
                source_sha256=source_sha256,
                owner_scope="platform",
            )
            if existing is not None:
                logger.info(
                    "import_global_instructions: [DRY RUN] already exists, would skip",
                    instruction_code=instruction_code,
                    existing_id=str(existing.id),
                    existing_status=existing.version_status,
                )
                return "skipped"
            else:
                logger.info(
                    "import_global_instructions: [DRY RUN] would create published version",
                    instruction_code=instruction_code,
                    path=str(path),
                    has_compiled_payload=compiled_payload is not None,
                    compile_error=compile_error,
                )
                return "created"

    # Production path — транзакция с auto-commit при успехе
    async with transactional_session() as session:
        repo = GlobalInstructionVersionRepository(session)

        # Проверяем существование по partial unique index:
        # uix_global_instruction_versions_platform_source_sha256
        # (instruction_code, source_sha256) WHERE owner_scope = 'platform'
        existing = await repo.get_by_instruction_code_and_sha256(
            instruction_code=instruction_code,
            source_sha256=source_sha256,
            owner_scope="platform",
        )

        if existing is not None:
            logger.debug(
                "import_global_instructions: already exists, skipping",
                instruction_code=instruction_code,
                source_sha256=source_sha256[:16],
                existing_id=str(existing.id),
                existing_status=existing.version_status,
            )
            return "skipped"

        # Вычисляем immutable_content_hash:
        # из compiled_payload если есть, иначе из source_sha256
        if compiled_payload is not None:
            immutable_hash = _compute_payload_hash(compiled_payload)
        else:
            immutable_hash = source_sha256

        # Относительный путь от корня проекта для source_path
        try:
            relative_path = str(path.relative_to(_PROJECT_ROOT))
        except ValueError:
            relative_path = str(path)

        version = await repo.create_version(
            instruction_code=instruction_code,
            name=_extract_name(parsed, instruction_code),
            group=_extract_group(parsed),
            source_format="yaml",
            source_yaml=raw_content,
            source_sha256=source_sha256,
            source_path=relative_path,
            compiled_payload=compiled_payload,
            version_status="published",
            immutable_content_hash=immutable_hash,
            validation_report=validation_report,
            published_at=datetime.now(timezone.utc),
            change_summary=f"Initial import from {path.name}",
            owner_scope="platform",
            tenant_id=None,
        )
        # transactional_session() делает commit автоматически при выходе

    logger.info(
        "import_global_instructions: created published version",
        instruction_code=instruction_code,
        version_id=str(version.id),
        path=relative_path,
        has_compiled_payload=compiled_payload is not None,
        compile_error=compile_error,
    )
    return "created"


# ── Public API ────────────────────────────────────────────────────────────────


async def import_global_instructions(
    *,
    base_path: Path = _DEFAULT_GLOBAL_CHECKS_PATH,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Импортировать все global checks из файловой системы в БД.

    Args:
        base_path: директория с YAML файлами (рекурсивный поиск)
        dry_run:   если True — показать что будет создано, не писать в БД

    Returns:
        {"created": N, "skipped": N, "errors": N, "total": N}
    """
    if not base_path.exists():
        logger.error(
            "import_global_instructions: path does not exist",
            path=str(base_path),
        )
        return {"created": 0, "skipped": 0, "errors": 1, "total": 0}

    if not base_path.is_dir():
        logger.error(
            "import_global_instructions: path is not a directory",
            path=str(base_path),
        )
        return {"created": 0, "skipped": 0, "errors": 1, "total": 0}

    yaml_files = _find_yaml_files(base_path)

    if not yaml_files:
        logger.warning(
            "import_global_instructions: no YAML files found",
            path=str(base_path),
        )
        return {"created": 0, "skipped": 0, "errors": 0, "total": 0}

    logger.info(
        "import_global_instructions: starting",
        path=str(base_path),
        files_count=len(yaml_files),
        dry_run=dry_run,
    )

    compiler = InstructionCompiler()
    counts: dict[str, int] = {"created": 0, "skipped": 0, "errors": 0}

    for yaml_path in yaml_files:
        try:
            result = await _import_single_file(
                path=yaml_path,
                compiler=compiler,
                dry_run=dry_run,
            )
            counts[result] = counts.get(result, 0) + 1
        except Exception as exc:
            # Неожиданная ошибка вне транзакции (например сетевая)
            logger.exception(
                "import_global_instructions: unexpected error processing file",
                path=str(yaml_path),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            counts["errors"] += 1

    counts["total"] = len(yaml_files)

    logger.info(
        "import_global_instructions: completed",
        created=counts["created"],
        skipped=counts["skipped"],
        errors=counts["errors"],
        total=counts["total"],
        dry_run=dry_run,
    )

    return counts


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import global checks from filesystem into DB as published platform versions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.import_global_instructions
  python -m scripts.import_global_instructions --dry-run
  python -m scripts.import_global_instructions --path /custom/path/global_checks
        """,
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=_DEFAULT_GLOBAL_CHECKS_PATH,
        help=f"Path to global_checks directory (default: {_DEFAULT_GLOBAL_CHECKS_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be created without writing to DB",
    )
    args = parser.parse_args()

    result = asyncio.run(
        import_global_instructions(
            base_path=args.path,
            dry_run=args.dry_run,
        )
    )

    print("\nImport global instructions result:")
    print(f"  Created:  {result['created']}")
    print(f"  Skipped:  {result['skipped']}")
    print(f"  Errors:   {result['errors']}")
    print(f"  Total:    {result['total']}")

    if result["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()


    