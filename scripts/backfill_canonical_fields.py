#!/usr/bin/env python
"""Backfill script for CheckResult canonical lifecycle fields.

Calculates canonical_content_hash, updates canonical_locale from Run,
and sets content_revision to 1 for all historical check_results.
Operates in batches of 200 to avoid table locks in production.
"""

import asyncio
import os
import sys
import uuid
from typing import Any

# Добавляем src в PYTHONPATH для работы импортов
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.result_presentation_content import build_presentation_source_hash
from db.models.result import CheckResult
from db.models.run import Run

BATCH_SIZE = 200


def get_db_url() -> str:
    """Read DATABASE_URL from environment or fallback to dev."""
    # Загружаем .env если скрипт запущен напрямую
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env")))
    except ImportError:
        pass

    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL not found in env, using dev fallback.")
        url = "postgresql+asyncpg://mas:mas_super_password@127.0.0.1:15432/mas_dd"
    return url


async def main() -> None:
    db_url = get_db_url()
    engine = create_async_engine(db_url, echo=False)
    session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        # 1. Считаем сколько записей нуждаются в заполнении
        count_stmt = select(CheckResult.id).where(
            (CheckResult.canonical_content_hash.is_(None))
            | (CheckResult.canonical_locale.is_(None))
        )
        result = await session.execute(count_stmt)
        pending_ids = [row[0] for row in result.all()]
        total_pending = len(pending_ids)

        if total_pending == 0:
            print("All check_results already have canonical lifecycle fields. No backfill needed.")
            return

        print(f"Found {total_pending} check_results needing backfill.")
        print(f"Processing in batches of {BATCH_SIZE}...")

        processed_count = 0

        # Обрабатываем пачками
        for i in range(0, total_pending, BATCH_SIZE):
            batch_ids = pending_ids[i : i + BATCH_SIZE]

            # Читаем данные записей с их Run.analysis_language
            stmt = (
                select(CheckResult, Run.analysis_language)
                .join(Run, Run.id == CheckResult.run_id)
                .where(CheckResult.id.in_(batch_ids))
            )
            batch_result = await session.execute(stmt)
            rows = batch_result.all()

            for cr, analysis_language in rows:
                # Рассчитываем хэш
                content_hash = build_presentation_source_hash(
                    check_name=cr.check_name,
                    display_text=cr.display_text,
                    review_message=cr.review_message,
                    dd_request_text=None,
                )

                cr.canonical_content_hash = content_hash
                cr.canonical_locale = analysis_language or "ru"  # Сейф-fallback на ru
                cr.content_revision = cr.content_revision or 1

            # Фиксируем изменения для текущей пачки
            await session.commit()
            processed_count += len(rows)
            print(f"  Processed {processed_count}/{total_pending}...")

        print("Backfill completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())


    