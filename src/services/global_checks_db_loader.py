# src/services/global_checks_db_loader.py

"""
DB-backed loader для global checks.

DB-first strategy:
- сначала читаем published platform global instructions из БД;
- если БД пуста, безопасно fallback на file-based load_global_checks();
- возвращаем тот же контракт: dict[str, GlobalCheckConfig].
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.playbooks.compiler import GlobalCheckConfig, load_global_checks
from db.repositories.global_instruction_version_repo import (
    GlobalInstructionVersionRepository,
)

logger = get_logger(__name__)


async def load_global_checks_from_db(
    session: AsyncSession,
) -> dict[str, GlobalCheckConfig]:
    checks, _refs = await load_global_checks_with_refs_from_db(session)
    return checks


async def load_global_checks_with_refs_from_db(
    session: AsyncSession,
) -> tuple[dict[str, GlobalCheckConfig], dict[str, str]]:
    """
    Load published platform global instructions from DB together with version refs.

    Returns:
        (
            {instruction_code: GlobalCheckConfig},
            {instruction_code: version_id_str},
        )

    Fallback:
    - если published global instructions в БД отсутствуют → fallback на файлы;
    - в fallback режиме refs пустые, потому что file-based source не имеет DB version ids.
    """
    repo = GlobalInstructionVersionRepository(session)
    versions = await repo.list_all_published_platform()

    if not versions:
        logger.warning(
            "No published platform global instructions in DB — falling back to file-based loader"
        )
        return load_global_checks(), {}

    checks: dict[str, GlobalCheckConfig] = {}
    refs: dict[str, str] = {}

    for version in versions:
        payload = version.compiled_payload

        if not isinstance(payload, dict):
            logger.warning(
                "Published global instruction has non-dict compiled_payload, skipping",
                instruction_code=version.instruction_code,
                version_id=str(version.id),
            )
            continue

        try:
            cfg = GlobalCheckConfig(**payload)
        except Exception as exc:
            logger.error(
                "Failed to build GlobalCheckConfig from DB row, skipping",
                instruction_code=version.instruction_code,
                version_id=str(version.id),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            continue

        if cfg.id in checks:
            logger.warning(
                "Duplicate global check id from DB, skipping later row",
                check_id=cfg.id,
                instruction_code=version.instruction_code,
                version_id=str(version.id),
            )
            continue

        checks[cfg.id] = cfg
        refs[cfg.id] = str(version.id)

    logger.info(
        "Loaded global checks with refs from DB",
        count=len(checks),
        refs_count=len(refs),
        source="database",
    )
    return checks, refs



