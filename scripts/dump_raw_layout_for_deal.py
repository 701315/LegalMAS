"""
Утилита для выгрузки text_layout_raw.json документов сделки.

Использование:
    python scripts/dump_raw_layout_for_deal.py \
        --deal-id a8ad762f-9ce7-49c1-9b09-6a1168a8508c \
        --run-id 1fcaeb45-fb15-486d-8f25-095408810a32 \
        --output-dir /tmp/multilingual_samples \
        --max-elements 200

Что делает:
- находит все document_versions для указанной сделки (или конкретного run)
- показывает какие документы есть, их языки и наличие raw_layout
- скачивает raw_layout для каждого документа через ArtifactStore
- сохраняет обрезанную версию (первые N элементов + весь metadata)

Требования:
- запускать из корня проекта: cd /srv/steloom-dev
- активированный venv: source .venv/bin/activate
- переменные окружения из .env (Postgres, MinIO) должны быть доступны
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

# Добавляем src в PYTHONPATH если запускаем как обычный скрипт
_repo_root = Path(__file__).resolve().parent.parent
_src_root = _repo_root / "src"
if _src_root.exists() and str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))


async def _main_async(
    deal_id: str,
    run_id: str | None,
    output_dir: Path,
    max_elements: int,
    document_id_filter: str | None,
) -> int:
    """
    Основная async логика.

    Возвращает exit code: 0 если всё хорошо, 1 при ошибке.
    """
    # Импорты внутри функции чтобы sys.path успел настроиться
    from core.config import settings
    from db.uow import db_uow
    from storage.artifact_store import ArtifactStore
    from sqlalchemy import text as sql_text

    print(f"[info] deal_id = {deal_id}")
    if run_id:
        print(f"[info] run_id  = {run_id}")
    else:
        print("[info] run_id  = <not specified, will list all documents of the deal>")

    print(f"[info] output_dir = {output_dir}")
    print(f"[info] max_elements per document = {max_elements}")

    output_dir.mkdir(parents=True, exist_ok=True)

    store = ArtifactStore(settings)

    async with db_uow() as uow:
        session = uow.session

        # ── 1. Получаем список документов сделки ─────────────────────────
        # Используем прямой SQL чтобы не зависеть от точных имён методов
        # репозитория, которые могут отличаться в вашей версии кода.

        query = """
        SELECT
            d.id                              AS document_id,
            d.filename                        AS filename,
            d.status                          AS status,
            d.detected_languages              AS detected_languages,
            d.language_discovery_status       AS lang_discovery_status,
            dv.id                             AS version_id,
            dv.text_layout_raw_ref            AS raw_ref,
            dv.layout_primary_ref             AS primary_ref,
            dv.layout_primary_sanitized_ref   AS sanitized_ref,
            dv.origin_filetype                AS origin_filetype,
            dv.created_at                     AS version_created_at
        FROM documents d
        JOIN document_versions dv
            ON dv.document_id = d.id
        WHERE d.deal_id = :deal_id
        ORDER BY d.created_at ASC, dv.created_at DESC
        """

        result = await session.execute(
            sql_text(query),
            {"deal_id": deal_id},
        )
        rows = result.mappings().all()

        if not rows:
            print(f"[error] No documents found for deal_id={deal_id}")
            return 1

        print()
        print(f"[info] Found {len(rows)} document version(s) for deal")
        print("-" * 100)

        # Показываем таблицу
        for i, row in enumerate(rows, start=1):
            langs = row["detected_languages"] or []
            langs_str = ",".join(langs) if isinstance(langs, list) else str(langs)
            print(f"{i:2}. document_id     = {row['document_id']}")
            print(f"    version_id      = {row['version_id']}")
            print(f"    filename        = {row['filename']}")
            print(f"    status          = {row['status']}")
            print(f"    origin_filetype = {row['origin_filetype']}")
            print(f"    languages       = [{langs_str}]  (lang_discovery={row['lang_discovery_status']})")
            print(f"    raw_ref         = {row['raw_ref'] or '<empty>'}")
            print(f"    primary_ref     = {row['primary_ref'] or '<empty>'}")
            print(f"    sanitized_ref   = {row['sanitized_ref'] or '<empty>'}")
            print()

        # ── 2. Фильтруем документы ───────────────────────────────────────

        candidates: list[dict[str, Any]] = []
        for row in rows:
            if document_id_filter and str(row["document_id"]) != document_id_filter:
                continue

            if not row["raw_ref"]:
                print(f"[skip] document_id={row['document_id']} has no raw_ref, skipping")
                continue

            candidates.append(dict(row))

        if not candidates:
            print("[error] No documents with raw_ref found after filtering")
            return 1

        print(f"[info] Will dump raw_layout for {len(candidates)} document(s)")
        print()

        # ── 3. Скачиваем raw_layout для каждого и сохраняем ─────────────

        for row in candidates:
            document_id = str(row["document_id"])
            version_id = str(row["version_id"])
            raw_ref = row["raw_ref"]
            langs = row["detected_languages"] or []
            langs_str = "-".join(sorted(langs)) if isinstance(langs, list) and langs else "unknown"

            print(f"[dump] document_id={document_id}")
            print(f"       version_id={version_id}")
            print(f"       raw_ref={raw_ref}")

            # Преобразуем s3://bucket/path в чистый path для ArtifactStore
            prefix = f"s3://{store.bucket}/"
            if not raw_ref.startswith(prefix):
                print(f"[error] raw_ref does not start with {prefix}, skipping")
                continue

            s3_path = raw_ref.replace(prefix, "", 1)

            try:
                raw_layout = store.get_json(s3_path)
            except Exception as e:
                print(f"[error] Failed to read raw_layout from MinIO: {e}")
                continue

            elements = raw_layout.get("elements", []) or []
            tables = raw_layout.get("tables", []) or []
            total_elements = len(elements)
            total_tables = len(tables)

            print(f"       total elements = {total_elements}")
            print(f"       total tables   = {total_tables}")

            # Обрезаем elements до первых max_elements
            truncated = dict(raw_layout)
            truncated["elements"] = elements[:max_elements]

            # Добавляем маркер что файл обрезан
            truncated["_dump_meta"] = {
                "original_element_count": total_elements,
                "truncated_to": min(max_elements, total_elements),
                "original_table_count": total_tables,
                "tables_included_in_dump": len(tables),
                "detected_languages": list(langs) if langs else [],
                "filename": row["filename"],
                "status": row["status"],
            }

            # Формируем имя файла
            safe_filename = _safe_filename(row["filename"] or "unknown")
            output_filename = f"{langs_str}__{safe_filename}__{document_id[:8]}.json"
            output_path = output_dir / output_filename

            try:
                output_path.write_text(
                    json.dumps(truncated, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"       saved to {output_path}")
                print(f"       size on disk: {output_path.stat().st_size:,} bytes")
            except Exception as e:
                print(f"[error] Failed to write output file: {e}")
                continue

            print()

    print("[done] All dumps complete")
    print(f"[done] Files are in: {output_dir}")
    return 0


def _safe_filename(name: str) -> str:
    """
    Убирает опасные символы из имени файла, оставляя только a-z, 0-9, _, -.
    """
    result = []
    for ch in name.lower():
        if ch.isalnum() or ch in ("_", "-", "."):
            result.append(ch)
        else:
            result.append("_")
    safe = "".join(result).strip("_")
    return safe[:60] if safe else "unnamed"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump text_layout_raw.json for documents of a specific deal",
    )
    parser.add_argument(
        "--deal-id",
        required=True,
        help="Deal UUID (обязательно)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run UUID (опционально, для информации в логах)",
    )
    parser.add_argument(
        "--document-id",
        default=None,
        help="Если указан — выгружает только этот конкретный document_id",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/multilingual_samples",
        help="Куда сохранять JSON файлы (по умолчанию /tmp/multilingual_samples)",
    )
    parser.add_argument(
        "--max-elements",
        type=int,
        default=200,
        help="Сколько первых элементов оставить в каждом дампе (по умолчанию 200)",
    )

    args = parser.parse_args()

    # Валидация UUID
    try:
        uuid.UUID(args.deal_id)
    except ValueError:
        print(f"[error] --deal-id is not a valid UUID: {args.deal_id}")
        return 2

    if args.run_id:
        try:
            uuid.UUID(args.run_id)
        except ValueError:
            print(f"[error] --run-id is not a valid UUID: {args.run_id}")
            return 2

    if args.document_id:
        try:
            uuid.UUID(args.document_id)
        except ValueError:
            print(f"[error] --document-id is not a valid UUID: {args.document_id}")
            return 2

    output_dir = Path(args.output_dir)

    exit_code = asyncio.run(
        _main_async(
            deal_id=args.deal_id,
            run_id=args.run_id,
            output_dir=output_dir,
            max_elements=args.max_elements,
            document_id_filter=args.document_id,
        )
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())


    