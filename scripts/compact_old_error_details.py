#!/usr/bin/env python3
# scripts/compact_old_error_details.py

"""
Компактификация старых error_details в PostgreSQL.

Назначение:
- для Document.processing_error_details и Run.error_details старше N дней
  заменить полный JSON payload на компактную summary-версию;
- уменьшить долгосрочный рост PostgreSQL из-за traceback и больших error blobs.

По умолчанию запускается в dry-run режиме.

Примеры:
    python scripts/compact_old_error_details.py
    python scripts/compact_old_error_details.py --execute
    python scripts/compact_old_error_details.py --days 365 --execute
    python scripts/compact_old_error_details.py --batch-size 100 --execute
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

PROJECT_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
if PROJECT_SRC not in sys.path:
    sys.path.insert(0, PROJECT_SRC)

from sqlalchemy import or_, select, update

from db.models.document import Document
from db.models.run import Run
from db.session import AsyncSessionLocal, engine

DEFAULT_OLDER_THAN_DAYS = 730
DEFAULT_BATCH_SIZE = 500
MAX_COMPACT_MESSAGE_LENGTH = 500


def _already_compacted(details: Any) -> bool:
    if not isinstance(details, dict):
        return False
    return bool(details.get("compacted") is True)


def _make_compact_summary(details: Any, compacted_at: str) -> dict[str, Any]:
    if isinstance(details, dict):
        error_type = details.get("type")
        message = details.get("message")
        original_keys = sorted(str(k) for k in details.keys())
    else:
        error_type = None
        message = details
        original_keys = []

    message_text = str(message or "").strip()[:MAX_COMPACT_MESSAGE_LENGTH] or None

    return {
        "compacted": True,
        "compacted_at": compacted_at,
        "type": error_type,
        "message": message_text,
        "original_keys": original_keys,
    }


async def compact_documents_batch(
    *,
    cutoff_dt: datetime,
    batch_size: int,
    dry_run: bool,
) -> int:
    compacted_at = datetime.now(UTC).isoformat()

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Document.id, Document.processing_error_details)
            .where(
                Document.updated_at < cutoff_dt,
                Document.processing_error_details.isnot(None),
                or_(
                    Document.processing_error_details["compacted"].astext.is_(None),
                    Document.processing_error_details["compacted"].astext != "true",
                ),
            )
            .order_by(Document.updated_at.asc(), Document.id.asc())
            .limit(batch_size)
        )

        if not dry_run:
            stmt = stmt.with_for_update(skip_locked=True)

        result = await session.execute(stmt)
        rows = list(result.all())

        if not rows:
            return 0

        for doc_id, details in rows:
            summary = _make_compact_summary(details, compacted_at)

            if dry_run:
                print(
                    f"[DRY-RUN] document {doc_id} -> compact summary "
                    f"(original_type={type(details).__name__})"
                )
            else:
                await session.execute(
                    update(Document)
                    .where(Document.id == doc_id)
                    .values(processing_error_details=summary)
                )

        if not dry_run:
            await session.commit()

        return len(rows)


async def compact_runs_batch(
    *,
    cutoff_dt: datetime,
    batch_size: int,
    dry_run: bool,
) -> int:
    compacted_at = datetime.now(UTC).isoformat()

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Run.id, Run.error_details)
            .where(
                Run.created_at < cutoff_dt,
                Run.error_details.isnot(None),
                or_(
                    Run.error_details["compacted"].astext.is_(None),
                    Run.error_details["compacted"].astext != "true",
                ),
            )
            .order_by(Run.created_at.asc(), Run.id.asc())
            .limit(batch_size)
        )

        if not dry_run:
            stmt = stmt.with_for_update(skip_locked=True)

        result = await session.execute(stmt)
        rows = list(result.all())

        if not rows:
            return 0

        for run_id, details in rows:
            summary = _make_compact_summary(details, compacted_at)

            if dry_run:
                print(
                    f"[DRY-RUN] run {run_id} -> compact summary "
                    f"(original_type={type(details).__name__})"
                )
            else:
                await session.execute(
                    update(Run)
                    .where(Run.id == run_id)
                    .values(error_details=summary)
                )

        if not dry_run:
            await session.commit()

        return len(rows)


async def _run_all_document_batches(
    *,
    cutoff_dt: datetime,
    batch_size: int,
    dry_run: bool,
) -> int:
    total = 0

    while True:
        batch_count = await compact_documents_batch(
            cutoff_dt=cutoff_dt,
            batch_size=batch_size,
            dry_run=dry_run,
        )
        total += batch_count

        if dry_run or batch_count == 0:
            break

    return total


async def _run_all_run_batches(
    *,
    cutoff_dt: datetime,
    batch_size: int,
    dry_run: bool,
) -> int:
    total = 0

    while True:
        batch_count = await compact_runs_batch(
            cutoff_dt=cutoff_dt,
            batch_size=batch_size,
            dry_run=dry_run,
        )
        total += batch_count

        if dry_run or batch_count == 0:
            break

    return total


async def run(
    *,
    older_than_days: int,
    batch_size: int,
    dry_run: bool,
) -> None:
    cutoff_dt = datetime.now(UTC) - timedelta(days=older_than_days)

    print(f"Compacting error details older than {older_than_days} days")
    print(f"Cutoff datetime: {cutoff_dt.isoformat()}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"Batch size: {batch_size}")
    print()

    documents_total = await _run_all_document_batches(
        cutoff_dt=cutoff_dt,
        batch_size=batch_size,
        dry_run=dry_run,
    )
    print(f"Documents processed: {documents_total}")

    runs_total = await _run_all_run_batches(
        cutoff_dt=cutoff_dt,
        batch_size=batch_size,
        dry_run=dry_run,
    )
    print(f"Runs processed: {runs_total}")

    print()
    print(f"Total processed: {documents_total + runs_total}")

    if dry_run:
        print("Dry-run finished. Re-run with --execute to apply changes.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compact old error_details / processing_error_details in PostgreSQL"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_OLDER_THAN_DAYS,
        help=f"Process records older than N days (default: {DEFAULT_OLDER_THAN_DAYS})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes. Without this flag script runs in dry-run mode.",
    )
    args = parser.parse_args()

    try:
        asyncio.run(
            run(
                older_than_days=args.days,
                batch_size=args.batch_size,
                dry_run=not args.execute,
            )
        )
    finally:
        try:
            asyncio.run(engine.dispose())
        except Exception:
            pass


if __name__ == "__main__":
    main()


    