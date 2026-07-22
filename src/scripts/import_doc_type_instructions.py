# src/scripts/import_doc_type_instructions.py
"""
Import script: загружает doc-type instructions из YAMLRegistry в БД.

Сканирует все doc types из YAMLRegistry → создаёт published platform versions
в document_type_instruction_versions.

Правила:
- Idempotent: использует resolve_or_create_from_config() который проверяет
  по (doc_type_code, source_sha256) — если существует → skip.
- Создаёт сразу в статусе 'published' (bootstrap платформенной библиотеки).
- Каждый doc type — отдельная транзакция.

Использование:
    python -m scripts.import_doc_type_instructions
    python -m scripts.import_doc_type_instructions --dry-run
    python -m scripts.import_doc_type_instructions --doc-type spa_agreement
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.logging import get_logger, setup_logging
from db.session import get_session, transactional_session
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from classifiers.yaml_registry import YAMLRegistry

setup_logging()
logger = get_logger(__name__)


async def import_doc_type_instructions(
    *,
    dry_run: bool = False,
    only_doc_type: str | None = None,
) -> dict[str, int]:
    """
    Импортировать все doc-type инструкции из YAMLRegistry в БД.

    Args:
        dry_run:       если True — показать что будет создано, не писать в БД
        only_doc_type: если задан — импортировать только этот doc type

    Returns:
        {"created": N, "skipped": N, "errors": N, "total": N}
    """
    # validate=False чтобы не падать при неполной конфигурации
    registry = YAMLRegistry.get_instance(validate=False)
    all_doc_types = sorted(registry.list_types())

    if not all_doc_types:
        logger.warning("import_doc_type_instructions: no doc types found in registry")
        return {"created": 0, "skipped": 0, "errors": 0, "total": 0}

    # Фильтр по конкретному doc type если задан
    if only_doc_type is not None:
        if only_doc_type not in all_doc_types:
            logger.error(
                "import_doc_type_instructions: specified doc_type not found in registry",
                only_doc_type=only_doc_type,
                available=all_doc_types[:20],
            )
            return {"created": 0, "skipped": 0, "errors": 1, "total": 0}
        doc_types_to_process = [only_doc_type]
    else:
        doc_types_to_process = all_doc_types

    logger.info(
        "import_doc_type_instructions: starting",
        doc_types_count=len(doc_types_to_process),
        only_doc_type=only_doc_type,
        dry_run=dry_run,
    )

    counts: dict[str, int] = {"created": 0, "skipped": 0, "errors": 0}

    for doc_type_code in doc_types_to_process:
        cfg = registry.get_config(doc_type_code)
        if cfg is None:
            logger.warning(
                "import_doc_type_instructions: config not found for doc_type",
                doc_type_code=doc_type_code,
            )
            counts["errors"] += 1
            continue

        if dry_run:
            # Read-only проверка существования
            async with get_session() as session:
                repo = DocumentTypeInstructionVersionRepository(session)
                try:
                    existing = await repo.get_latest_published(
                        doc_type_code,
                        tenant_id=None,
                    )
                    if existing is not None:
                        logger.info(
                            "import_doc_type_instructions: [DRY RUN] already has published version, would skip",
                            doc_type_code=doc_type_code,
                            existing_id=str(existing.id),
                        )
                        counts["skipped"] += 1
                    else:
                        logger.info(
                            "import_doc_type_instructions: [DRY RUN] no published version, would create",
                            doc_type_code=doc_type_code,
                        )
                        counts["created"] += 1
                except Exception as exc:
                    logger.error(
                        "import_doc_type_instructions: [DRY RUN] check failed",
                        doc_type_code=doc_type_code,
                        error=str(exc),
                    )
                    counts["errors"] += 1
            continue

        # Production path — транзакция с auto-commit
        async with transactional_session() as session:
            repo = DocumentTypeInstructionVersionRepository(session)
            try:
                # resolve_or_create_from_config():
                # - проверяет по (doc_type_code, source_sha256)
                # - если нет → создаёт published platform version
                # - если есть → возвращает existing (created=False)
                result = await repo.resolve_or_create_from_config(cfg)

                if result.created:
                    logger.info(
                        "import_doc_type_instructions: created published version",
                        doc_type_code=doc_type_code,
                        version_id=str(result.version.id),
                    )
                    counts["created"] += 1
                    # transactional_session() сам делает commit

                else:
                    logger.debug(
                        "import_doc_type_instructions: already exists, skipping",
                        doc_type_code=doc_type_code,
                        version_id=str(result.version.id),
                        version_status=result.version.version_status,
                    )
                    counts["skipped"] += 1
                    # Rollback не нужен — изменений нет,
                    # transactional_session() сделает commit пустой транзакции

            except Exception as exc:
                # transactional_session() делает rollback автоматически
                logger.exception(
                    "import_doc_type_instructions: failed to process doc_type",
                    doc_type_code=doc_type_code,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                counts["errors"] += 1

    counts["total"] = len(doc_types_to_process)

    logger.info(
        "import_doc_type_instructions: completed",
        created=counts["created"],
        skipped=counts["skipped"],
        errors=counts["errors"],
        total=counts["total"],
        dry_run=dry_run,
    )

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import doc-type instructions from YAMLRegistry into DB as published platform versions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.import_doc_type_instructions
  python -m scripts.import_doc_type_instructions --dry-run
  python -m scripts.import_doc_type_instructions --doc-type spa_agreement
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be created without writing to DB",
    )
    parser.add_argument(
        "--doc-type",
        type=str,
        default=None,
        dest="only_doc_type",
        help="Import only this specific doc type (default: all)",
    )
    args = parser.parse_args()

    result = asyncio.run(
        import_doc_type_instructions(
            dry_run=args.dry_run,
            only_doc_type=args.only_doc_type,
        )
    )

    print("\nImport doc-type instructions result:")
    print(f"  Created:  {result['created']}")
    print(f"  Skipped:  {result['skipped']}")
    print(f"  Errors:   {result['errors']}")
    print(f"  Total:    {result['total']}")

    if result["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()


    