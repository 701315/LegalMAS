# src/scripts/rebuild_base_playbooks.py
"""
Пересобрать базовые platform PlaybookVersion с актуальными global instruction refs.

Что делает:
  1. Берёт все published platform PlaybookVersion (tenant_id IS NULL).
  2. Для каждой версии проверяет, изменились ли global_instruction_refs
     (сравнивает refs в compiled_checks.meta с текущими published global versions).
  3. Если refs устарели — создаёт новую draft PlaybookVersion:
       - с тем же playbook_id, model_config_id, source_payload, owner_scope, tenant_id=None
       - пересобирает compiled_checks через build_compiled_checks() с актуальными refs
       - публикует её через PlaybookPublishingService.publish()
  4. Если refs актуальны — SKIP.

Инварианты:
  - Не трогает tenant-owned PlaybookVersions.
  - Не трогает уже выполненные клиентские Runs.
  - Не меняет Deal.playbook_version_id у существующих сделок.
  - Старые published platform versions НЕ архивируются автоматически
    (это сделано намеренно: исторические версии должны оставаться для
    воспроизводимости audit trail).
  - Идемпотентен при совпадении refs.

Использование (из /srv/steloom-dev):
  python src/scripts/rebuild_base_playbooks.py --all --dry-run
  python src/scripts/rebuild_base_playbooks.py --all --publish
  python src/scripts/rebuild_base_playbooks.py --playbook-version-id <uuid> --publish
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid as uuid_mod
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.constants import PlaybookStatus
from core.logging import get_logger, setup_logging
from db.session import get_session, transactional_session

setup_logging()
logger = get_logger(__name__)


# ── Результаты ────────────────────────────────────────────────────────────────

SKIP = "SKIP"
REBUILT = "REBUILT"
ERROR = "ERROR"


# ══════════════════════════════════════════════════════════════════════════════
#  Core logic
# ══════════════════════════════════════════════════════════════════════════════

def _extract_current_ref_map(compiled_checks: dict | None) -> dict[str, str]:
    """
    Извлечь {instruction_code: version_id} из compiled_checks.meta.global_instruction_refs.
    Если поле отсутствует — вернуть пустой dict (версия без ref-tracking, требует rebuild).
    """
    if not isinstance(compiled_checks, dict):
        return {}
    meta = compiled_checks.get("meta") or {}
    refs = meta.get("global_instruction_refs") or {}
    if not isinstance(refs, dict):
        return {}
    return {k: str(v) for k, v in refs.items()}


def _extract_check_ids_from_compiled(compiled_checks: dict | None) -> list[str]:
    """
    Извлечь список check_ids из compiled_checks.meta.check_ids.
    Это те instruction_codes, которые реально входят в данный playbook.
    """
    if not isinstance(compiled_checks, dict):
        return []
    meta = compiled_checks.get("meta") or {}
    return list(meta.get("check_ids") or [])


def _refs_are_stale(
    current_refs: dict[str, str],
    fresh_refs: dict[str, str],
    check_ids: list[str],
) -> bool:
    """
    Проверить, устарели ли global refs конкретно для проверок, которые входят в playbook.

    current_refs: {instruction_code: version_id} из compiled_checks.meta
    fresh_refs:   {instruction_code: version_id} из БД (текущие published global versions)
    check_ids:    instruction_codes, реально используемые в playbook
    """
    if not check_ids:
        # Нет check_ids в meta — считаем, что refs требуют rebuild
        return True

    for code in check_ids:
        current = current_refs.get(code)
        fresh = fresh_refs.get(code)
        if current != fresh:
            logger.debug(
                "rebuild: stale ref detected",
                instruction_code=code,
                current_version_id=current,
                fresh_version_id=fresh,
            )
            return True

    return False


async def _rebuild_one_version(
    *,
    version_id: uuid_mod.UUID,
    dry_run: bool,
) -> str:
    """Пересобрать одну platform PlaybookVersion."""

    from db.models.playbook import PlaybookVersion
    from db.repositories.playbook_repo import PlaybookRepository, compute_source_payload_hash
    from services.global_checks_db_loader import load_global_checks_with_refs_from_db
    from services.playbooks.publishing import PlaybookPublishingService
    from core.playbooks.compiler import build_compiled_checks
    from sqlalchemy import select

    # Dry-run: читаем состояние, ничего не пишем
    if dry_run:
        async with get_session() as session:
            repo = PlaybookRepository(session)
            pv = await repo.get_by_id(version_id)
            if pv is None:
                logger.error(
                    "rebuild: version not found",
                    version_id=str(version_id),
                )
                return ERROR

            if pv.tenant_id is not None:
                logger.warning(
                    "rebuild: skipping tenant-owned version",
                    version_id=str(version_id),
                    tenant_id=str(pv.tenant_id),
                )
                return SKIP

            if pv.status != PlaybookStatus.PUBLISHED.value:
                logger.debug(
                    "rebuild: skipping non-published version",
                    version_id=str(version_id),
                    status=pv.status,
                )
                return SKIP

            all_checks, fresh_refs = await load_global_checks_with_refs_from_db(session)
            current_refs = _extract_current_ref_map(pv.compiled_checks)
            check_ids = _extract_check_ids_from_compiled(pv.compiled_checks)

            if not _refs_are_stale(current_refs, fresh_refs, check_ids):
                logger.info(
                    "rebuild: [DRY RUN] SKIP (refs up to date)",
                    version_id=str(version_id),
                    name=pv.name,
                )
                return SKIP

            logger.info(
                "rebuild: [DRY RUN] would REBUILD",
                version_id=str(version_id),
                name=pv.name,
                stale_codes=[
                    c for c in check_ids
                    if current_refs.get(c) != fresh_refs.get(c)
                ],
            )
            return REBUILT

    # Реальная операция
    async with transactional_session() as session:
        repo = PlaybookRepository(session)
        pv = await repo.get_by_id(version_id)
        if pv is None:
            logger.error(
                "rebuild: version not found",
                version_id=str(version_id),
            )
            return ERROR

        # Пересобираем только platform-owned published versions
        if pv.tenant_id is not None:
            logger.warning(
                "rebuild: skipping tenant-owned version",
                version_id=str(version_id),
                tenant_id=str(pv.tenant_id),
            )
            return SKIP

        if pv.status != PlaybookStatus.PUBLISHED.value:
            logger.debug(
                "rebuild: skipping non-published version",
                version_id=str(version_id),
                status=pv.status,
            )
            return SKIP

        # Загружаем актуальные global checks и refs из БД
        all_checks, fresh_refs = await load_global_checks_with_refs_from_db(session)

        if not all_checks:
            logger.error(
                "rebuild: no published global checks in DB, cannot rebuild",
                version_id=str(version_id),
            )
            return ERROR

        current_refs = _extract_current_ref_map(pv.compiled_checks)
        check_ids = _extract_check_ids_from_compiled(pv.compiled_checks)

        if not _refs_are_stale(current_refs, fresh_refs, check_ids):
            logger.info(
                "rebuild: SKIP (refs up to date)",
                version_id=str(version_id),
                name=pv.name,
            )
            return SKIP

        # Получаем source_payload для пересборки
        source_payload = pv.source_payload or {}
        bundles = source_payload.get("bundles") or []
        include_ids = source_payload.get("include_ids") or []
        exclude_ids = source_payload.get("exclude_ids") or []
        profile = source_payload.get("profile")
        primary_bundle_id = bundles[0] if bundles else None

        # Проверяем, что у нас есть хоть что-то для сборки
        if not bundles and not include_ids:
            # Пробуем взять check_ids из скомпилированного плейбука как include_ids
            if check_ids:
                include_ids = check_ids
                logger.warning(
                    "rebuild: source_payload empty, falling back to compiled check_ids",
                    version_id=str(version_id),
                    check_ids_count=len(include_ids),
                )
            else:
                logger.error(
                    "rebuild: cannot determine checks to include, skipping",
                    version_id=str(version_id),
                )
                return ERROR

        # Пересобираем compiled_checks с актуальными refs
        try:
            new_compiled = build_compiled_checks(
                all_checks=all_checks,
                bundles=bundles,
                include_ids=include_ids,
                exclude_ids=exclude_ids,
                profile=profile,
                primary_bundle_id=primary_bundle_id,
                global_instruction_refs=fresh_refs,
            )
        except Exception as exc:
            logger.exception(
                "rebuild: build_compiled_checks failed",
                version_id=str(version_id),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return ERROR

        # Создаём новую draft версию на основе текущей published
        new_pv = PlaybookVersion(
            playbook_id=pv.playbook_id,
            name=pv.name,
            semver=pv.semver,
            model_config_id=pv.model_config_id,
            compiled_checks=new_compiled,
            source_payload=source_payload,
            source_payload_sha256=compute_source_payload_hash(source_payload),
            status=PlaybookStatus.DRAFT.value,
            tenant_id=None,           # platform-owned
            owner_scope="platform",
            parent_version_id=pv.id,  # lineage audit trail
            is_default=False,
        )
        session.add(new_pv)
        await session.flush()

        # Публикуем новую версию
        publishing_svc = PlaybookPublishingService(session)
        try:
            published_pv = await publishing_svc.publish(new_pv)
        except Exception as exc:
            logger.exception(
                "rebuild: publish failed",
                new_version_id=str(new_pv.id),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return ERROR

        logger.info(
            "rebuild: REBUILT and published",
            old_version_id=str(pv.id),
            new_version_id=str(published_pv.id),
            name=pv.name,
            stale_codes=[
                c for c in check_ids
                if current_refs.get(c) != fresh_refs.get(c)
            ],
        )
        return REBUILT


async def rebuild_all_platform_playbooks(*, dry_run: bool = False) -> dict[str, int]:
    """
    Пересобрать все published platform PlaybookVersions с устаревшими global refs.
    """
    from db.models.playbook import PlaybookVersion
    from sqlalchemy import select

    # Получаем IDs всех published platform versions
    async with get_session() as session:
        result = await session.execute(
            select(PlaybookVersion.id).where(
                PlaybookVersion.status == PlaybookStatus.PUBLISHED.value,
                PlaybookVersion.tenant_id.is_(None),
                PlaybookVersion.owner_scope == "platform",
            )
        )
        version_ids = [row[0] for row in result.all()]

    if not version_ids:
        logger.info("rebuild_all: no published platform versions found")
        return {SKIP: 0, REBUILT: 0, ERROR: 0}

    logger.info(
        "rebuild_all: found published platform versions",
        count=len(version_ids),
        dry_run=dry_run,
    )

    counts: dict[str, int] = {SKIP: 0, REBUILT: 0, ERROR: 0}
    for vid in version_ids:
        try:
            result = await _rebuild_one_version(version_id=vid, dry_run=dry_run)
        except Exception as exc:
            logger.exception(
                "rebuild_all: unexpected error",
                version_id=str(vid),
                error=str(exc),
            )
            result = ERROR
        counts[result] = counts.get(result, 0) + 1

    return counts


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

def _print_summary(counts: dict[str, int]) -> None:
    total = sum(counts.values())
    print(f"\n{'─' * 52}")
    print(f"  Rebuild Base Playbooks")
    print(f"  SKIP   : {counts.get(SKIP, 0)}")
    print(f"  REBUILT: {counts.get(REBUILT, 0)}")
    print(f"  ERROR  : {counts.get(ERROR, 0)}")
    print(f"  Total  : {total}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Пересобрать базовые platform PlaybookVersions с актуальными global refs.\n"
            "Запускать из /srv/steloom-dev:\n"
            "  python src/scripts/rebuild_base_playbooks.py --all --publish"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--all",
        dest="rebuild_all",
        action="store_true",
        default=False,
        help="Пересобрать все published platform versions",
    )
    parser.add_argument(
        "--playbook-version-id",
        type=str,
        default=None,
        dest="version_id",
        help="Пересобрать конкретную PlaybookVersion по ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Только показать, что было бы сделано, без записи в БД",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        default=False,
        help="Реально записать в БД (без флага форсируется dry-run)",
    )
    args = parser.parse_args()

    dry_run = args.dry_run or not args.publish

    if dry_run and not args.dry_run:
        print("\n[INFO] --publish не указан, работаем в dry-run режиме.\n")

    if not args.rebuild_all and not args.version_id:
        parser.error("Укажите --all или --playbook-version-id <uuid>")

    if args.rebuild_all and args.version_id:
        parser.error("Нельзя использовать --all и --playbook-version-id одновременно")

    print(
        f"\n{'=' * 52}\n"
        f"  Rebuild Base Playbooks\n"
        f"  {'all platform published versions' if args.rebuild_all else ('version_id=' + args.version_id)}\n"
        f"  mode={'DRY RUN' if dry_run else 'PUBLISH'}\n"
        f"{'=' * 52}"
    )

    if args.rebuild_all:
        counts = asyncio.run(rebuild_all_platform_playbooks(dry_run=dry_run))
        _print_summary(counts)
        has_error = counts.get(ERROR, 0) > 0
    else:
        try:
            vid = uuid_mod.UUID(args.version_id)
        except ValueError:
            print(f"\n[ERROR] Невалидный UUID: {args.version_id}")
            raise SystemExit(1)

        result = asyncio.run(_rebuild_one_version(version_id=vid, dry_run=dry_run))
        counts = {result: 1}
        _print_summary(counts)
        has_error = result == ERROR

    print()
    if has_error:
        print("  [WARN] Завершено с ошибками. Проверьте лог выше.")
        raise SystemExit(1)
    else:
        print("  [OK] Завершено успешно.")


if __name__ == "__main__":
    main()


    