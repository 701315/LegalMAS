"""
Bootstrap import for platform global instructions.

Что делает:
- сканирует playbooks/global_checks/**/*.yaml;
- читает canonical compiled configs через load_global_checks();
- создаёт published platform rows в global_instruction_versions;
- если row уже существует, но compiled_payload битый / null / draft,
  выполняет repair/backfill.

Важно:
- DB source of truth остаётся БД;
- этот скрипт нужен для initial bootstrap и безопасного повторного прогона.

Использование:
    python src/scripts/import_global_instructions.py
    python src/scripts/import_global_instructions.py --dry-run
    python src/scripts/import_global_instructions.py --path /custom/path/global_checks
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

_SRC = Path(__file__).resolve().parents[1]  # .../src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.logging import get_logger, setup_logging
from core.playbooks.compiler import load_global_checks
from db.repositories.global_instruction_version_repo import (
    GlobalInstructionVersionRepository,
)
from db.session import get_session, transactional_session

setup_logging()
logger = get_logger(__name__)

_PROJECT_ROOT = _SRC.parent
_DEFAULT_GLOBAL_CHECKS_PATH = _PROJECT_ROOT / "playbooks" / "global_checks"


def _compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _compute_payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _find_yaml_files(base_path: Path) -> list[Path]:
    files: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        files.extend(base_path.rglob(ext))
    return sorted(files)


def _parse_yaml_file(path: Path) -> tuple[dict, str] | None:
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw)
        if not isinstance(parsed, dict):
            logger.warning(
                "import_global_instructions: skipping non-dict YAML",
                path=str(path),
                got_type=type(parsed).__name__,
            )
            return None
        return parsed, raw
    except Exception as exc:
        logger.error(
            "import_global_instructions: failed to parse YAML",
            path=str(path),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None


def _extract_instruction_code(parsed: dict, path: Path) -> str | None:
    for field in ("id", "instruction_code", "check_id"):
        value = parsed.get(field)
        if value and isinstance(value, str) and value.strip():
            return value.strip()

    logger.warning(
        "import_global_instructions: no instruction code field found, skipping",
        path=str(path),
        available_keys=list(parsed.keys())[:15],
    )
    return None


def _extract_name(parsed: dict, payload: dict, instruction_code: str) -> str:
    for candidate in (
        parsed.get("name"),
        payload.get("name"),
        parsed.get("title"),
        parsed.get("label"),
    ):
        if candidate and str(candidate).strip():
            return str(candidate).strip()[:300]
    return instruction_code


def _extract_group(parsed: dict, payload: dict, path: Path) -> str | None:
    for candidate in (
        parsed.get("group"),
        payload.get("group"),
        parsed.get("category"),
        payload.get("category"),
        parsed.get("topic_code"),
        payload.get("topic_code"),
    ):
        if candidate and str(candidate).strip():
            return str(candidate).strip()[:100]
    # fallback: parent directory name
    if path.parent and path.parent.name:
        return path.parent.name[:100]
    return None


def _to_payload_dict(cfg: object) -> dict:
    if hasattr(cfg, "model_dump"):
        return cfg.model_dump(mode="python")
    if hasattr(cfg, "dict"):
        return cfg.dict()
    raise TypeError(f"Unsupported config object type: {type(cfg).__name__}")


async def _inspect_existing_state(
    *,
    repo: GlobalInstructionVersionRepository,
    instruction_code: str,
    source_sha256: str,
) -> str:
    """
    Return:
      - 'create'
      - 'repair'
      - 'skip'
    """
    existing = await repo.get_by_instruction_code_and_sha256(
        instruction_code=instruction_code,
        source_sha256=source_sha256,
        owner_scope="platform",
    )
    if existing is None:
        return "create"

    payload = existing.compiled_payload
    if not isinstance(payload, dict):
        return "repair"

    if existing.version_status != "published":
        return "repair"

    if not existing.immutable_content_hash:
        return "repair"

    return "skip"


async def _import_single_file(
    *,
    path: Path,
    canonical_checks: dict[str, object],
    dry_run: bool,
) -> str:
    """
    Returns:
      created | repaired | skipped | error
    """
    parse_result = _parse_yaml_file(path)
    if parse_result is None:
        return "error"

    parsed, raw_content = parse_result
    instruction_code = _extract_instruction_code(parsed, path)
    if instruction_code is None:
        return "error"

    canonical_cfg = canonical_checks.get(instruction_code)
    if canonical_cfg is None:
        logger.error(
            "import_global_instructions: canonical compiled config not found for YAML instruction",
            instruction_code=instruction_code,
            path=str(path),
        )
        return "error"

    try:
        payload = _to_payload_dict(canonical_cfg)
    except Exception as exc:
        logger.error(
            "import_global_instructions: failed to serialize canonical config",
            instruction_code=instruction_code,
            path=str(path),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return "error"

    source_sha256 = _compute_sha256(raw_content)
    immutable_hash = _compute_payload_hash(payload)

    try:
        relative_path = str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        relative_path = str(path)

    name = _extract_name(parsed, payload, instruction_code)
    group = _extract_group(parsed, payload, path)
    validation_report = {
        "errors": [],
        "warnings": [],
        "bootstrap_import": True,
        "compiled_from": "core.playbooks.compiler.load_global_checks",
    }

    if dry_run:
        async with get_session() as session:
            repo = GlobalInstructionVersionRepository(session)
            action = await _inspect_existing_state(
                repo=repo,
                instruction_code=instruction_code,
                source_sha256=source_sha256,
            )
            logger.info(
                "import_global_instructions: [DRY RUN] planned action",
                instruction_code=instruction_code,
                action=action,
                path=relative_path,
            )
            return {"create": "created", "repair": "repaired", "skip": "skipped"}[action]

    async with transactional_session() as session:
        repo = GlobalInstructionVersionRepository(session)
        existing = await repo.get_by_instruction_code_and_sha256(
            instruction_code=instruction_code,
            source_sha256=source_sha256,
            owner_scope="platform",
        )

        now = datetime.now(timezone.utc)

        if existing is None:
            version = await repo.create_version(
                instruction_code=instruction_code,
                name=name,
                group=group,
                source_format="yaml",
                source_yaml=raw_content,
                source_sha256=source_sha256,
                source_path=relative_path,
                compiled_payload=payload,
                version_status="published",
                immutable_content_hash=immutable_hash,
                validation_report=validation_report,
                published_at=now,
                change_summary=f"Initial bootstrap import from {path.name}",
                owner_scope="platform",
                tenant_id=None,
            )
            logger.info(
                "import_global_instructions: created published version",
                instruction_code=instruction_code,
                version_id=str(version.id),
                path=relative_path,
            )
            return "created"

        needs_repair = (
            not isinstance(existing.compiled_payload, dict)
            or existing.version_status != "published"
            or not existing.immutable_content_hash
            or existing.name != name
            or existing.group != group
        )

        if not needs_repair:
            logger.debug(
                "import_global_instructions: already up-to-date, skipping",
                instruction_code=instruction_code,
                version_id=str(existing.id),
            )
            return "skipped"

        await repo.update_version(
            existing,
            source_yaml=raw_content,
            source_sha256=source_sha256,
            compiled_payload=payload,
            name=name,
            group=group,
            source_path=relative_path,
            validation_report=validation_report,
            change_summary=f"Bootstrap repair/backfill from {path.name}",
            immutable_content_hash=immutable_hash,
            version_status="published",
            published_at=existing.published_at or now,
        )

        logger.info(
            "import_global_instructions: repaired existing version",
            instruction_code=instruction_code,
            version_id=str(existing.id),
            path=relative_path,
        )
        return "repaired"


async def import_global_instructions(
    *,
    base_path: Path = _DEFAULT_GLOBAL_CHECKS_PATH,
    dry_run: bool = False,
) -> dict[str, int]:
    if not base_path.exists():
        logger.error(
            "import_global_instructions: path does not exist",
            path=str(base_path),
        )
        return {
            "created": 0,
            "repaired": 0,
            "skipped": 0,
            "errors": 1,
            "total": 0,
        }

    if not base_path.is_dir():
        logger.error(
            "import_global_instructions: path is not a directory",
            path=str(base_path),
        )
        return {
            "created": 0,
            "repaired": 0,
            "skipped": 0,
            "errors": 1,
            "total": 0,
        }

    yaml_files = _find_yaml_files(base_path)
    if not yaml_files:
        logger.warning(
            "import_global_instructions: no YAML files found",
            path=str(base_path),
        )
        return {
            "created": 0,
            "repaired": 0,
            "skipped": 0,
            "errors": 0,
            "total": 0,
        }

    canonical_checks = load_global_checks()
    if not canonical_checks:
        logger.error(
            "import_global_instructions: load_global_checks() returned empty result"
        )
        return {
            "created": 0,
            "repaired": 0,
            "skipped": 0,
            "errors": len(yaml_files),
            "total": len(yaml_files),
        }

    logger.info(
        "import_global_instructions: starting",
        path=str(base_path),
        files_count=len(yaml_files),
        canonical_checks_count=len(canonical_checks),
        dry_run=dry_run,
    )

    counts: dict[str, int] = {
        "created": 0,
        "repaired": 0,
        "skipped": 0,
        "errors": 0,
    }

    for yaml_path in yaml_files:
        try:
            result = await _import_single_file(
                path=yaml_path,
                canonical_checks=canonical_checks,
                dry_run=dry_run,
            )
            counts[result] = counts.get(result, 0) + 1
        except Exception as exc:
            logger.exception(
                "import_global_instructions: unexpected error processing file",
                path=str(yaml_path),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            counts["errors"] += 1

    counts["total"] = len(yaml_files)

    logger.info(
        "import_global_instructions: completed",
        created=counts["created"],
        repaired=counts["repaired"],
        skipped=counts["skipped"],
        errors=counts["errors"],
        total=counts["total"],
        dry_run=dry_run,
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap import platform global instructions into DB",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=_DEFAULT_GLOBAL_CHECKS_PATH,
        help=f"Path to global_checks directory (default: {_DEFAULT_GLOBAL_CHECKS_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview actions without writing to DB",
    )
    args = parser.parse_args()

    result = asyncio.run(
        import_global_instructions(
            base_path=args.path,
            dry_run=args.dry_run,
        )
    )

    print("\nImport global instructions result:")
    print(f"  Created:   {result['created']}")
    print(f"  Repaired:  {result['repaired']}")
    print(f"  Skipped:   {result['skipped']}")
    print(f"  Errors:    {result['errors']}")
    print(f"  Total:     {result['total']}")

    if result["errors"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


    