# src/services/global_checks_db_loader.py

"""
DB-backed loader для global checks.

Заменяет file-based load_global_checks() из core/playbooks/compiler.py.
Используется runtime (planner, playbook_runs) когда USE_DB_GLOBAL_CHECKS=true.

Возвращает dict[str, GlobalCheckConfig] — тот же контракт что и file-based loader.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.playbooks.compiler import GlobalCheckConfig, load_global_checks
from db.repositories.global_instruction_version_repo import (
    GlobalInstructionVersionRepository,
)

logger = get_logger(__name__)

_USE_DB = os.getenv("USE_DB_GLOBAL_CHECKS", "false").lower() in ("1", "true", "yes")


async def load_global_checks_from_db(
    session: AsyncSession,
) -> dict[str, GlobalCheckConfig]:
    """
    Load published platform global instructions from DB.

    Falls back to file-based loader if USE_DB_GLOBAL_CHECKS=false.
    Same return contract as load_global_checks().
    """
    if not _USE_DB:
        logger.debug(
            "USE_DB_GLOBAL_CHECKS=false — falling back to file-based loader"
        )
        return load_global_checks()

    repo = GlobalInstructionVersionRepository(session)
    versions = await repo.list_all_published_platform()

    checks: dict[str, GlobalCheckConfig] = {}
    for version in versions:
        payload = version.compiled_payload
        if not isinstance(payload, dict):
            logger.warning(
                "GlobalInstructionVersion %s has non-dict compiled_payload, skipping",
                version.instruction_code,
            )
            continue

        try:
            cfg = GlobalCheckConfig(**payload)
        except Exception as exc:
            logger.error(
                "Failed to build GlobalCheckConfig from version %s (%s): %s",
                version.id,
                version.instruction_code,
                exc,
            )
            continue

        if cfg.id in checks:
            logger.warning(
                "Duplicate global check id='%s' from DB version %s, skipping",
                cfg.id,
                version.id,
            )
            continue

        checks[cfg.id] = cfg

    logger.info(
        "Loaded %d global checks from DB",
        len(checks),
    )
    return checks



