# src/scripts/sync_base_instructions.py
"""
Sync базовых platform instructions из YAML-файлов в БД.

Поддерживает:
  - document_type instructions  (playbooks/document_types/ через YAMLRegistry)
  - global check instructions   (playbooks/global_checks/**/*.yaml)

Алгоритм для каждого YAML:
  1. Загрузить + скомпилировать через соответствующий InstructionCompiler.
  2. Найти latest published platform version в БД (tenant_id IS NULL).
  3. Сравнить source_sha256 файла с SHA в БД.
     - Совпадает  → SKIP (нет изменений, ничего не делаем).
     - Нет record → CREATE_PUBLISH (создать draft + publish).
     - Отличается → UPDATE_PUBLISH (создать новый draft + publish,
                    старая published версия архивируется сервисом автоматически).

Ограничения:
  - Не трогает tenant-owned versions.
  - Не трогает документы клиентов.
  - Не запускает reclassify/rerun.
  - Идемпотентен: можно запускать сколько угодно раз.

Использование (из /srv/steloom-dev):
  python src/scripts/sync_base_instructions.py --kind all   --all     --dry-run
  python src/scripts/sync_base_instructions.py --kind all   --all     --publish
  python src/scripts/sync_base_instructions.py --kind doc_type --code contract_1.6_real_estate --publish
  python src/scripts/sync_base_instructions.py --kind global   --code confidentiality_clause   --publish
  python src/scripts/sync_base_instructions.py --kind doc_type --all  --publish --change-summary "Патч: anti-construction exclusions"
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml as yaml_lib

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.logging import get_logger, setup_logging
from db.session import get_session, transactional_session

setup_logging()
logger = get_logger(__name__)

_PROJECT_ROOT = _SRC.parent
_DOC_TYPES_PATH = _PROJECT_ROOT / "playbooks" / "document_types"
_GLOBAL_CHECKS_PATH = _PROJECT_ROOT / "playbooks" / "global_checks"


# ── Результаты для счётчиков ───────────────────────────────────────────────────

SKIP = "SKIP"
CREATE_PUBLISH = "CREATE_PUBLISH"
UPDATE_PUBLISH = "UPDATE_PUBLISH"
ERROR = "ERROR"


# ── Утилиты ───────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
#  DOC TYPE SYNC
# ══════════════════════════════════════════════════════════════════════════════

async def _sync_one_doc_type(
    *,
    doc_type_code: str,
    dry_run: bool,
    change_summary: str | None,
) -> str:
    """Синхронизировать одну doc-type инструкцию."""

    from classifiers.yaml_registry import YAMLRegistry
    from services.instruction_publishing_service import (
        DuplicateInstructionContentError,
        InstructionPublishingService,
    )
    from db.repositories.document_type_instruction_version_repo import (
        DocumentTypeInstructionVersionRepository,
    )

    # Получаем конфиг из registry
    registry = YAMLRegistry.get_instance(validate=False)
    cfg = registry.get_config(doc_type_code)
    if cfg is None:
        logger.error(
            "sync_doc_type: not found in registry",
            doc_type_code=doc_type_code,
        )
        return ERROR

    # Определяем путь к YAML-файлу
    source_path: str | None = getattr(cfg, "source_path", None)
    if not source_path:
        logger.error(
            "sync_doc_type: source_path missing in cfg",
            doc_type_code=doc_type_code,
        )
        return ERROR

    yaml_file = _PROJECT_ROOT / source_path
    if not yaml_file.exists():
        logger.error(
            "sync_doc_type: YAML file not found",
            doc_type_code=doc_type_code,
            path=str(yaml_file),
        )
        return ERROR

    raw_yaml = yaml_file.read_text(encoding="utf-8")

    # ВАЖНО: в БД source_sha256 хранится не от сырого файла,
    # а от canonical source после компиляции InstructionCompiler.
    from services.instruction_compiler import InstructionCompiler

    compiler = InstructionCompiler()
    compiled = compiler.compile_doc_type_instruction(
        doc_type_code=doc_type_code,
        source=raw_yaml,
    )

    canonical_sha = compiled.source_sha256
    raw_file_sha = _sha256(raw_yaml)

    # Dry-run: только проверяем состояние БД, ничего не пишем
    if dry_run:
        async with get_session() as session:
            repo = DocumentTypeInstructionVersionRepository(session)
            published = await repo.get_latest_published(doc_type_code, tenant_id=None)
            if published and published.source_sha256 == canonical_sha:
                action = SKIP
            elif not published:
                action = CREATE_PUBLISH
            else:
                action = UPDATE_PUBLISH

            logger.info(
                "sync_doc_type: [DRY RUN]",
                doc_type_code=doc_type_code,
                action=action,
                canonical_sha=canonical_sha[:12],
                raw_file_sha=raw_file_sha[:12],
                db_sha=(published.source_sha256[:12] if published else None),
            )
            return action

    # Реальная операция
    async with transactional_session() as session:
        repo = DocumentTypeInstructionVersionRepository(session)
        svc = InstructionPublishingService(session)

        published = await repo.get_latest_published(doc_type_code, tenant_id=None)

        if published and published.source_sha256 == canonical_sha:
            logger.info(
                "sync_doc_type: SKIP (no changes)",
                doc_type_code=doc_type_code,
            )
            return SKIP

        action = CREATE_PUBLISH if not published else UPDATE_PUBLISH

        try:
            draft = await svc.create_platform_draft(
                doc_type_code=doc_type_code,
                source=raw_yaml,
                source_path=str(yaml_file.relative_to(_PROJECT_ROOT)),
                change_summary=(
                    change_summary
                    or f"sync_base_instructions: {action.lower().replace('_', ' ')}"
                ),
                parent_version_id=(published.id if published else None),
            )
            result_version = await svc.publish_platform_draft(version_id=draft.id)
            logger.info(
                "sync_doc_type: published",
                doc_type_code=doc_type_code,
                action=action,
                new_version_id=str(result_version.id),
                archived_previous=bool(published),
            )
            return action

        except DuplicateInstructionContentError:
            # Уже существует версия с таким SHA — значит де-факто уже актуальна
            logger.warning(
                "sync_doc_type: duplicate content, treating as SKIP",
                doc_type_code=doc_type_code,
            )
            return SKIP

        except Exception as exc:
            logger.exception(
                "sync_doc_type: error",
                doc_type_code=doc_type_code,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return ERROR


async def sync_doc_types(
    *,
    only_code: str | None = None,
    dry_run: bool = False,
    change_summary: str | None = None,
) -> dict[str, int]:
    """Синхронизировать все doc-type инструкции (или одну по коду)."""

    from classifiers.yaml_registry import YAMLRegistry

    registry = YAMLRegistry.get_instance(validate=False)
    all_codes = sorted(registry.list_types())

    if not all_codes:
        logger.warning("sync_doc_types: no doc types found in registry")
        return {SKIP: 0, CREATE_PUBLISH: 0, UPDATE_PUBLISH: 0, ERROR: 0}

    if only_code:
        if only_code not in all_codes:
            logger.error(
                "sync_doc_types: code not found in registry",
                code=only_code,
            )
            return {SKIP: 0, CREATE_PUBLISH: 0, UPDATE_PUBLISH: 0, ERROR: 1}
        codes = [only_code]
    else:
        codes = all_codes

    counts: dict[str, int] = {SKIP: 0, CREATE_PUBLISH: 0, UPDATE_PUBLISH: 0, ERROR: 0}
    for code in codes:
        try:
            result = await _sync_one_doc_type(
                doc_type_code=code,
                dry_run=dry_run,
                change_summary=change_summary,
            )
        except Exception as exc:
            logger.exception(
                "sync_doc_types: unexpected error",
                code=code,
                error=str(exc),
            )
            result = ERROR
        counts[result] = counts.get(result, 0) + 1

    return counts


# ══════════════════════════════════════════════════════════════════════════════
#  GLOBAL CHECKS SYNC
# ══════════════════════════════════════════════════════════════════════════════

def _extract_instruction_code(parsed: dict, path: Path) -> str | None:
    """Извлечь instruction_code из YAML-файла глобальной проверки."""
    for field in ("id", "instruction_code", "check_id"):
        v = parsed.get(field)
        if v and isinstance(v, str) and v.strip():
            return v.strip()
    logger.warning(
        "sync_global: no instruction_code found",
        path=str(path),
        available_keys=list(parsed.keys())[:10],
    )
    return None


async def _sync_one_global(
    *,
    yaml_file: Path,
    dry_run: bool,
    change_summary: str | None,
    only_code: str | None = None,
) -> str:
    """Синхронизировать один global check YAML-файл."""

    from services.global_instruction_publishing_service import (
        GlobalInstructionDuplicateContentError,
        GlobalInstructionPublishingService,
    )
    from db.repositories.global_instruction_version_repo import (
        GlobalInstructionVersionRepository,
    )

    # Парсим YAML
    try:
        raw_yaml = yaml_file.read_text(encoding="utf-8")
        parsed = yaml_lib.safe_load(raw_yaml)
    except Exception as exc:
        logger.error(
            "sync_global: failed to read/parse YAML",
            path=str(yaml_file),
            error=str(exc),
        )
        return ERROR

    if not isinstance(parsed, dict):
        logger.warning(
            "sync_global: YAML is not a dict, skipping",
            path=str(yaml_file),
        )
        return SKIP

    instruction_code = _extract_instruction_code(parsed, yaml_file)
    if not instruction_code:
        return ERROR

    # Фильтр по коду если задан
    if only_code and instruction_code != only_code:
        return SKIP

    # ВАЖНО: в БД source_sha256 хранится canonical source после компиляции,
    # а не SHA сырого YAML-файла.
    from services.instruction_compiler import InstructionCompiler

    compiler = InstructionCompiler()
    compiled = compiler.compile_global_instruction(
        instruction_code=instruction_code,
        source=raw_yaml,
    )

    canonical_sha = compiled.source_sha256
    raw_file_sha = _sha256(raw_yaml)

    try:
        relative_path = str(yaml_file.relative_to(_PROJECT_ROOT))
    except ValueError:
        relative_path = str(yaml_file)

    # Dry-run
    if dry_run:
        async with get_session() as session:
            repo = GlobalInstructionVersionRepository(session)
            published = await repo.get_latest_published(instruction_code)
            if published and published.source_sha256 == canonical_sha:
                action = SKIP
            elif not published:
                action = CREATE_PUBLISH
            else:
                action = UPDATE_PUBLISH

            logger.info(
                "sync_global: [DRY RUN]",
                instruction_code=instruction_code,
                action=action,
                canonical_sha=canonical_sha[:12],
                raw_file_sha=raw_file_sha[:12],
                db_sha=(published.source_sha256[:12] if published else None),
            )
            return action

    # Реальная операция
    async with transactional_session() as session:
        repo = GlobalInstructionVersionRepository(session)
        svc = GlobalInstructionPublishingService(session)

        published = await repo.get_latest_published(instruction_code)

        if published and published.source_sha256 == canonical_sha:
            logger.info(
                "sync_global: SKIP (no changes)",
                instruction_code=instruction_code,
            )
            return SKIP

        action = CREATE_PUBLISH if not published else UPDATE_PUBLISH

        try:
            draft = await svc.create_draft(
                instruction_code=instruction_code,
                source=raw_yaml,
                source_path=relative_path,
                change_summary=(
                    change_summary
                    or f"sync_base_instructions: {action.lower().replace('_', ' ')}"
                ),
                parent_version_id=(published.id if published else None),
                owner_scope="platform",
                tenant_id=None,
            )
            result_version = await svc.publish_draft(version_id=draft.id)
            logger.info(
                "sync_global: published",
                instruction_code=instruction_code,
                action=action,
                new_version_id=str(result_version.id),
                archived_previous=bool(published),
            )
            return action

        except GlobalInstructionDuplicateContentError:
            logger.warning(
                "sync_global: duplicate content, treating as SKIP",
                instruction_code=instruction_code,
            )
            return SKIP

        except Exception as exc:
            logger.exception(
                "sync_global: error",
                instruction_code=instruction_code,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return ERROR


async def sync_global_checks(
    *,
    only_code: str | None = None,
    dry_run: bool = False,
    change_summary: str | None = None,
    base_path: Path = _GLOBAL_CHECKS_PATH,
) -> dict[str, int]:
    """Синхронизировать все global check инструкции (или одну по коду)."""

    yaml_files: list[Path] = sorted(
        f for ext in ("*.yaml", "*.yml")
        for f in base_path.rglob(ext)
    )

    if not yaml_files:
        logger.warning(
            "sync_global_checks: no YAML files found",
            path=str(base_path),
        )
        return {SKIP: 0, CREATE_PUBLISH: 0, UPDATE_PUBLISH: 0, ERROR: 0}

    counts: dict[str, int] = {SKIP: 0, CREATE_PUBLISH: 0, UPDATE_PUBLISH: 0, ERROR: 0}
    for yaml_file in yaml_files:
        try:
            result = await _sync_one_global(
                yaml_file=yaml_file,
                dry_run=dry_run,
                change_summary=change_summary,
                only_code=only_code,
            )
        except Exception as exc:
            logger.exception(
                "sync_global_checks: unexpected error",
                path=str(yaml_file),
                error=str(exc),
            )
            result = ERROR
        counts[result] = counts.get(result, 0) + 1

    return counts


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

def _print_summary(kind: str, counts: dict[str, int]) -> None:
    total = sum(counts.values())
    print(f"\n{'─' * 52}")
    print(f"  Kind          : {kind}")
    print(f"  SKIP          : {counts.get(SKIP, 0)}")
    print(f"  CREATE_PUBLISH: {counts.get(CREATE_PUBLISH, 0)}")
    print(f"  UPDATE_PUBLISH: {counts.get(UPDATE_PUBLISH, 0)}")
    print(f"  ERROR         : {counts.get(ERROR, 0)}")
    print(f"  Total         : {total}")


async def _run(
    *,
    kind: str,
    sync_all: bool,
    code: str | None,
    dry_run: bool,
    change_summary: str | None,
) -> bool:
    """
    Единая async entry point — все операции в одном event loop.
    Возвращает True если были ошибки.
    """
    has_error = False

    if kind in ("doc_type", "all"):
        counts = await sync_doc_types(
            only_code=code if kind == "doc_type" else None,
            dry_run=dry_run,
            change_summary=change_summary,
        )
        _print_summary("doc_type", counts)
        if counts.get(ERROR, 0) > 0:
            has_error = True

    if kind in ("global", "all"):
        counts = await sync_global_checks(
            only_code=code if kind == "global" else None,
            dry_run=dry_run,
            change_summary=change_summary,
        )
        _print_summary("global", counts)
        if counts.get(ERROR, 0) > 0:
            has_error = True

    return has_error


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sync базовых platform instructions из YAML-файлов в БД.\n"
            "Запускать из /srv/steloom-dev:\n"
            "  python src/scripts/sync_base_instructions.py --kind all --all --publish"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--kind",
        choices=["doc_type", "global", "all"],
        required=True,
        help="Тип инструкций: doc_type | global | all",
    )
    parser.add_argument(
        "--all",
        dest="sync_all",
        action="store_true",
        default=False,
        help="Синхронизировать все инструкции выбранного kind",
    )
    parser.add_argument(
        "--code",
        type=str,
        default=None,
        help="Синхронизировать только конкретный код (doc_type_code или instruction_code)",
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
    parser.add_argument(
        "--change-summary",
        type=str,
        default=None,
        dest="change_summary",
        help="Описание изменений для новой версии (опционально)",
    )
    args = parser.parse_args()

    # Если нет --publish, форсируем dry-run (защита от случайного запуска)
    dry_run = args.dry_run or not args.publish

    if dry_run and not args.dry_run:
        print("\n[INFO] --publish не указан, работаем в dry-run режиме.\n")

    if not args.sync_all and not args.code:
        parser.error("Укажите --all (все) или --code <код> (конкретный)")

    if args.sync_all and args.code:
        parser.error("Нельзя использовать --all и --code одновременно")

    print(
        f"\n{'=' * 52}\n"
        f"  Sync Base Instructions\n"
        f"  kind={args.kind}  "
        f"{'all' if args.sync_all else ('code=' + args.code)}\n"
        f"  mode={'DRY RUN' if dry_run else 'PUBLISH'}\n"
        f"{'=' * 52}"
    )

    has_error = asyncio.run(_run(
        kind=args.kind,
        sync_all=args.sync_all,
        code=args.code,
        dry_run=dry_run,
        change_summary=args.change_summary,
    ))

    print()
    if has_error:
        print("  [WARN] Завершено с ошибками. Проверьте лог выше.")
        raise SystemExit(1)
    else:
        print("  [OK] Завершено успешно.")


if __name__ == "__main__":
    main()

    

