"""
Seed script for built-in platform-wide static localizations (Sprint 4.3).

Populates enum labels and system UI labels for all supported locales.
Idempotent: creates missing records, updates changed labels in-place.

Adding a new language:
  1. Add entries with the new locale to built-in-localizations-v1.json
  2. Re-run this script
  No code changes required.

Run: python -m scripts.seed_instruction_localizations
"""

import asyncio
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

from sqlalchemy import select, and_

from src.core.logging import setup_logging, get_logger
from src.db.session import get_session
from src.db.models.instruction_presentation_localization import (
    InstructionPresentationLocalization,
)
from src.services.instruction_localization_keys import LocalizationKeyBuilder

logger = get_logger(__name__)

LOCALIZATIONS_JSON_PATH = os.path.join(
    project_root,
    "src",
    "engine",
    "localization",
    "translations",
    "built-in-localizations-v1.json",
)


async def seed_instruction_localizations() -> None:
    setup_logging()
    logger.info("Starting built-in instruction localizations seeding...")

    if not os.path.exists(LOCALIZATIONS_JSON_PATH):
        logger.error("Source JSON not found at %s", LOCALIZATIONS_JSON_PATH)
        sys.exit(1)

    with open(LOCALIZATIONS_JSON_PATH, "r", encoding="utf-8") as f:
        loc_data = json.load(f)

    logger.info("Loaded %d localization records from JSON.", len(loc_data))

    # ── Validate all keys before touching the database ──────────
    invalid_keys = [
        item["instruction_key"]
        for item in loc_data
        if not LocalizationKeyBuilder.is_valid_key(item["instruction_key"])
    ]
    if invalid_keys:
        logger.error("CRITICAL: Invalid keys in seed payload: %s", invalid_keys)
        sys.exit(1)

    async with get_session() as session:
        # Single query: all active platform-wide entries
        stmt = select(InstructionPresentationLocalization).where(
            and_(
                InstructionPresentationLocalization.tenant_id.is_(None),
                InstructionPresentationLocalization.is_active.is_(True),
            )
        )
        result = await session.execute(stmt)
        existing_map = {
            (r.instruction_key, r.locale): r
            for r in result.scalars().all()
        }

        created = 0
        updated = 0

        for item in loc_data:
            key = (item["instruction_key"], item["locale"])
            label = item["label"]
            desc = item.get("description")

            if key in existing_map:
                record = existing_map[key]
                changed = False
                if record.label != label:
                    record.label = label
                    changed = True
                if record.description != desc:
                    record.description = desc
                    changed = True
                if changed:
                    updated += 1
            else:
                session.add(
                    InstructionPresentationLocalization(
                        tenant_id=None,
                        instruction_key=item["instruction_key"],
                        locale=item["locale"],
                        label=label,
                        description=desc,
                        is_active=True,
                    )
                )
                created += 1

        await session.commit()

    logger.info(
        "Seed complete.",
        created=created,
        updated=updated,
        total=len(loc_data),
    )


if __name__ == "__main__":
    asyncio.run(seed_instruction_localizations())


    