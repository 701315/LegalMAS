"""
Bootstrap import for platform doc-type instructions.

Что делает:
- читает все doc types из YAMLRegistry;
- гарантирует, что для каждого типа существует published platform version;
- если resolve_or_create_from_config() создаёт/возвращает draft,
  скрипт публикует его в рамках bootstrap.

Использование:
    python src/scripts/import_doc_type_instructions.py
    python src/scripts/import_doc_type_instructions.py --dry-run
    python src/scripts/import_doc_type_instructions.py --doc-type contract_7.4_nda
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]  # .../src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from classifiers.yaml_registry import YAMLRegistry
from core.logging import get_logger, setup_logging
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from db.session import get_session, transactional_session

setup_logging()
logger = get_logger(__name__)


def _compute_payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


async def import_doc_type_instructions(
    *,
    dry_run: bool = False,
    only_doc_type: str | None = None,
) -> dict[str, int]:
    registry = YAMLRegistry.get_instance(validate=False)
    all_doc_types = sorted(registry.list_types())

    if not all_doc_types:
        logger.warning("import_doc_type_instructions: no doc types found in registry")
        return {
            "created": 0,
            "promoted": 0,
            "skipped": 0,
            "errors": 0,
            "total": 0,
        }

    if only_doc_type is not None:
        if only_doc_type not in all_doc_types:
            logger.error(
                "import_doc_type_instructions: specified doc_type not found in registry",
                only_doc_type=only_doc_type,
            )
            return {
                "created": 0,
                "promoted": 0,
                "skipped": 0,
                "errors": 1,
                "total": 0,
            }
        doc_types_to_process = [only_doc_type]
    else:
        doc_types_to_process = all_doc_types

    logger.info(
        "import_doc_type_instructions: starting",
        doc_types_count=len(doc_types_to_process),
        only_doc_type=only_doc_type,
        dry_run=dry_run,
    )

    counts: dict[str, int] = {
        "created": 0,
        "promoted": 0,
        "skipped": 0,
        "errors": 0,
    }

    for doc_type_code in doc_types_to_process:
        cfg = registry.get_config(doc_type_code)
        if cfg is None:
            logger.error(
                "import_doc_type_instructions: config not found for doc_type",
                doc_type_code=doc_type_code,
            )
            counts["errors"] += 1
            continue

        if dry_run:
            async with get_session() as session:
                repo = DocumentTypeInstructionVersionRepository(session)
                try:
                    existing_published = await repo.get_latest_published(
                        doc_type_code,
                        tenant_id=None,
                    )
                    if existing_published is not None:
                        logger.info(
                            "import_doc_type_instructions: [DRY RUN] already published, would skip",
                            doc_type_code=doc_type_code,
                            version_id=str(existing_published.id),
                        )
                        counts["skipped"] += 1
                    else:
                        logger.info(
                            "import_doc_type_instructions: [DRY RUN] no published version, would create/promote",
                            doc_type_code=doc_type_code,
                        )
                        counts["created"] += 1
                except Exception as exc:
                    logger.error(
                        "import_doc_type_instructions: [DRY RUN] failed",
                        doc_type_code=doc_type_code,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    counts["errors"] += 1
            continue

        try:
            async with transactional_session() as session:
                repo = DocumentTypeInstructionVersionRepository(session)

                existing_published = await repo.get_latest_published(
                    doc_type_code,
                    tenant_id=None,
                )
                if existing_published is not None:
                    logger.debug(
                        "import_doc_type_instructions: already published, skipping",
                        doc_type_code=doc_type_code,
                        version_id=str(existing_published.id),
                    )
                    counts["skipped"] += 1
                    continue

                result = await repo.resolve_or_create_from_config(cfg)
                version = result.version

                was_created = bool(result.created)
                was_promoted = False

                if getattr(version, "version_status", None) != "published":
                    version.version_status = "published"
                    version.published_at = datetime.now(timezone.utc)
                    was_promoted = True

                if not getattr(version, "immutable_content_hash", None):
                    compiled_payload = getattr(version, "compiled_payload", None)
                    if isinstance(compiled_payload, dict):
                        version.immutable_content_hash = _compute_payload_hash(compiled_payload)
                    else:
                        version.immutable_content_hash = (
                            getattr(version, "source_sha256", None)
                            or getattr(cfg, "source_sha256", None)
                        )

                if was_created:
                    logger.info(
                        "import_doc_type_instructions: created published version",
                        doc_type_code=doc_type_code,
                        version_id=str(version.id),
                    )
                    counts["created"] += 1
                elif was_promoted:
                    logger.info(
                        "import_doc_type_instructions: promoted existing draft to published",
                        doc_type_code=doc_type_code,
                        version_id=str(version.id),
                    )
                    counts["promoted"] += 1
                else:
                    counts["skipped"] += 1

        except Exception as exc:
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
        promoted=counts["promoted"],
        skipped=counts["skipped"],
        errors=counts["errors"],
        total=counts["total"],
        dry_run=dry_run,
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap import platform doc-type instructions into DB",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview actions without writing to DB",
    )
    parser.add_argument(
        "--doc-type",
        type=str,
        default=None,
        dest="only_doc_type",
        help="Import only this specific doc_type",
    )
    args = parser.parse_args()

    result = asyncio.run(
        import_doc_type_instructions(
            dry_run=args.dry_run,
            only_doc_type=args.only_doc_type,
        )
    )

    print("\nImport doc-type instructions result:")
    print(f"  Created:   {result['created']}")
    print(f"  Promoted:  {result['promoted']}")
    print(f"  Skipped:   {result['skipped']}")
    print(f"  Errors:    {result['errors']}")
    print(f"  Total:     {result['total']}")

    if result["errors"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


    