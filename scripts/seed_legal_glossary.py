"""
Seed script to populate default platform-wide RU↔EN legal glossary (Sprint 3.3).
Failsafe, idempotent, and updates existing records in-place without duplicates.

Run: python -m scripts.seed_legal_glossary
"""

import asyncio
import json
import os
import sys

# Add project root and src directory to sys.path to resolve all import styles
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "src"))

from src.core.logging import setup_logging, get_logger
from src.db.session import get_session
from src.db.models.legal_glossary import LegalGlossary
from sqlalchemy import select, and_

logger = get_logger(__name__)

GLOSSARY_JSON_PATH = os.path.join(
    project_root, "src", "engine", "localization", "glossaries", "ru-en-legal-v1.json"
)


async def seed_legal_glossary() -> None:
    setup_logging()
    logger.info("Starting legal glossary seeding...")

    if not os.path.exists(GLOSSARY_JSON_PATH):
        logger.error(f"Glossary source JSON not found at {GLOSSARY_JSON_PATH}")
        sys.exit(1)

    with open(GLOSSARY_JSON_PATH, "r", encoding="utf-8") as f:
        terms_data = json.load(f)

    logger.info(f"Loaded {len(terms_data)} terms from JSON schema.")

    async with get_session() as session:
        # 1. Fetch all existing active platform-wide terms for comparison
        stmt = select(LegalGlossary).where(
            and_(
                LegalGlossary.tenant_id.is_(None),
                LegalGlossary.is_active == True,
            )
        )
        res = await session.execute(stmt)
        existing_list = list(res.scalars().all())

        # Map by key: (source_locale, target_locale, source_term) -> LegalGlossary
        existing_map = {
            (t.source_locale, t.target_locale, t.source_term): t
            for t in existing_list
        }

        created_count = 0
        updated_count = 0

        # 2. Iterate and upsert
        for item in terms_data:
            src_loc = item["source_locale"]
            tgt_loc = item["target_locale"]
            src_term = item["source_term"]
            tgt_term = item["target_term"]
            category = item.get("term_category")
            note = item.get("context_note")

            key = (src_loc, tgt_loc, src_term)

            if key in existing_map:
                # Update existing if values differ
                existing_record = existing_map[key]
                changed = False

                if existing_record.target_term != tgt_term:
                    existing_record.target_term = tgt_term
                    changed = True
                if existing_record.term_category != category:
                    existing_record.term_category = category
                    changed = True
                if existing_record.context_note != note:
                    existing_record.context_note = note
                    changed = True

                if changed:
                    updated_count += 1
            else:
                # Create brand new platform-wide record
                new_term = LegalGlossary(
                    tenant_id=None,
                    source_locale=src_loc,
                    target_locale=tgt_loc,
                    source_term=src_term,
                    target_term=tgt_term,
                    term_category=category,
                    context_note=note,
                    is_active=True,
                )
                session.add(new_term)
                created_count += 1

        await session.commit()

        logger.info(
            "Legal glossary seed finished successfully!",
            created=created_count,
            updated=updated_count,
            total_active=len(terms_data)
        )


if __name__ == "__main__":
    asyncio.run(seed_legal_glossary())
