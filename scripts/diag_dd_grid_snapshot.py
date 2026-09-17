"""
Диагностика: какая инструкция реально зафиксирована в ране и что читает DD Grid.

Запуск:
    python scripts/diag_dd_grid_snapshot.py              # последний ран
    python scripts/diag_dd_grid_snapshot.py <run_uuid>   # конкретный ран
    python scripts/diag_dd_grid_snapshot.py --deal <deal_uuid>  # последний ран сделки
"""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from typing import Any

from sqlalchemy import text

from db.session import engine


def _short(value: Any, limit: int = 200) -> str:
    s = json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value
    return s if len(s) <= limit else s[:limit] + "…"


async def _resolve_run_id(conn, args) -> uuid.UUID:
    if args.run_id:
        return uuid.UUID(args.run_id)

    if args.deal:
        row = (
            await conn.execute(
                text(
                    "SELECT id FROM runs WHERE deal_id = :deal_id "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"deal_id": args.deal},
            )
        ).first()
        if not row:
            raise SystemExit(f"Нет ранов для deal_id={args.deal}")
        return row[0]

    row = (
        await conn.execute(
            text("SELECT id FROM runs ORDER BY created_at DESC LIMIT 1")
        )
    ).first()
    if not row:
        raise SystemExit("В таблице runs ничего нет")
    return row[0]


async def main(args) -> None:
    async with engine.connect() as conn:
        run_id = await _resolve_run_id(conn, args)
        print(f"\n=== RUN {run_id} ===\n")

        # 1. Что в самом ране
        run_row = (
            await conn.execute(
                text(
                    "SELECT snapshot_schema_version, "
                    "       instruction_versions, "
                    "       instruction_snapshot_manifest, "
                    "       (instruction_snapshot_payload IS NOT NULL) AS has_payload, "
                    "       instruction_snapshot_payload, "
                    "       deal_id, playbook_version_id, status "
                    "FROM runs WHERE id = :id"
                ),
                {"id": run_id},
            )
        ).first()

        if run_row is None:
            raise SystemExit(f"Run {run_id} не найден")

        (
            schema_ver,
            instr_versions,
            instr_manifest,
            has_payload,
            instr_payload,
            deal_id,
            pb_version_id,
            run_status,
        ) = run_row

        print(f"snapshot_schema_version = {schema_ver}")
        print(f"run.status              = {run_status}")
        print(f"deal_id                 = {deal_id}")
        print(f"playbook_version_id     = {pb_version_id}")
        print(f"has_payload             = {has_payload}")
        print()

        print(f"instruction_versions keys     = {sorted((instr_versions or {}).keys())}")
        print(f"instruction_snapshot_payload = {sorted((instr_payload or {}).keys())}")
        print(f"instruction_snapshot_manifest keys = {sorted((instr_manifest or {}).keys())}")
        print()

        if schema_ver is None:
            print("⚠  LEGACY RUN (snapshot_schema_version IS NULL)")
            print("   → DD Grid по контракту имеет право на filesystem fallback.")
            print("   → Метка «Legacy» в UI — КОРРЕКТНА.")
        else:
            print(f"✓  STRICT RUN (snapshot_schema_version={schema_ver})")
            if not has_payload:
                print("   ❌ Инвариант нарушен: strict-ран без instruction_snapshot_payload.")
                print("      DD Grid должен fail-fast, а не читать файлсистему.")
        print()

        # 2. Что в documents
        docs_rows = (
            await conn.execute(
                text(
                    "SELECT DISTINCT doc_type FROM documents "
                    "WHERE deal_id = :deal_id AND doc_type IS NOT NULL"
                ),
                {"deal_id": deal_id},
            )
        ).all()
        doc_types = sorted(r[0] for r in docs_rows)
        print(f"doc_types в документах сделки = {doc_types}")
        print()

        # 3. Для каждого doc_type — сравнить base и effective
        for doc_type in doc_types:
            print(f"--- doc_type = {doc_type} ---")

            version_id_str = (instr_versions or {}).get(doc_type)
            print(f"  instruction_versions[{doc_type}] = {version_id_str}")

            has_eff = doc_type in (instr_payload or {})
            print(f"  instruction_snapshot_payload[{doc_type}] present = {has_eff}")

            if version_id_str:
                try:
                    base_row = (
                        await conn.execute(
                            text(
                                "SELECT id, version_status, owner_scope, tenant_id, "
                                "       immutable_content_hash, "
                                "       compiled_payload->'checks_v8'->0->>'name' AS first_check_name, "
                                "       compiled_payload IS NOT NULL AS has_compiled "
                                "FROM document_type_instruction_versions WHERE id = :id"
                            ),
                            {"id": uuid.UUID(version_id_str)},
                        )
                    ).first()

                    if base_row is None:
                        print(f"  ❌ base version row НЕ НАЙДЕН в БД для id={version_id_str}")
                    else:
                        (
                            b_id, b_status, b_scope, b_tenant, b_hash,
                            b_first_check, b_has_compiled,
                        ) = base_row
                        print(f"  base.status      = {b_status}")
                        print(f"  base.owner_scope = {b_scope}")
                        print(f"  base.has_compiled_payload = {b_has_compiled}")
                        print(f"  base.first_check_name = {_short(b_first_check, 120)}")
                except Exception as exc:
                    print(f"  ❌ Не удалось прочитать base version: {exc}")

            if has_eff:
                eff_payload = (instr_payload or {})[doc_type] or {}
                eff_first = None
                if isinstance(eff_payload, dict):
                    checks = eff_payload.get("checks_v8") or []
                    if checks and isinstance(checks[0], dict):
                        eff_first = checks[0].get("name")
                print(f"  effective.first_check_name = {_short(eff_first, 120)}")

                base_first = None
                if version_id_str:
                    try:
                        base_first_row = (
                            await conn.execute(
                                text(
                                    "SELECT compiled_payload->'checks_v8'->0->>'name' "
                                    "FROM document_type_instruction_versions WHERE id = :id"
                                ),
                                {"id": uuid.UUID(version_id_str)},
                            )
                        ).first()
                        base_first = base_first_row[0] if base_first_row else None
                    except Exception:
                        pass

                if base_first is not None and eff_first is not None:
                    if base_first != eff_first:
                        print(
                            "  ⚠  BASE ≠ EFFECTIVE  → DD Grid будет показывать "
                            "«не ту» инструкцию"
                        )
                        print(f"     base      = {_short(base_first, 120)}")
                        print(f"     effective = {_short(eff_first, 120)}")
                    else:
                        print("  ✓  BASE == EFFECTIVE (override chain не меняет результат)")
                elif has_eff and base_first is None:
                    print("  ⚠  Есть effective, нет base.first_check_name "
                          "(base row отсутствует или compiled_payload пустой)")
            print()

        # 4. Прогноз для DD Grid
        print("=== ПРОГНОЗ ПОВЕДЕНИЯ DD Grid ===")
        if schema_ver is None and not instr_versions:
            print("DD Grid: FilesystemInstructionProvider (метка Legacy)")
        elif instr_versions:
            missing_in_versions = set(doc_types) - set((instr_versions or {}).keys())
            if missing_in_versions:
                print(f"DD Grid: для {sorted(missing_in_versions)} метка будет «Legacy», "
                      "контент — с диска")
            else:
                print("DD Grid: метка «Persisted» для всех doc_types, "
                      "но контент читается из BASE, а не из EFFECTIVE")
        else:
            print("DD Grid: compiled_map пуст → FilesystemInstructionProvider")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", nargs="?", help="UUID рана")
    parser.add_argument("--deal", help="UUID сделки; возьмёт последний ран")
    args = parser.parse_args()
    asyncio.run(main(args))

    