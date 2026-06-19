#!/usr/bin/env python3
"""
Inspect which chunks/contexts were used for checks in a given run/document.

Usage:
  python3 scripts/inspect_check_contexts.py \
    --run-id ca33c12e-6fdf-4273-8eb6-bbb9fbc91d85 \
    --document-id 3c90865f-3cb4-4d4d-82cc-14af76246554

Optional:
  --check-id parties_and_authority
  --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pprint import pprint

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://mas:mas_dev_password@localhost:5432/mas_dd"
).replace("postgresql+asyncpg://", "postgresql://")


def get_args():
    p = argparse.ArgumentParser(description="Inspect contexts/chunks used for check extraction")
    p.add_argument("--run-id", required=True)
    p.add_argument("--document-id", required=True)
    p.add_argument("--check-id", required=False)
    p.add_argument("--verbose", action="store_true", default=False)
    return p.parse_args()


def connect():
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("[ERROR] install psycopg2-binary", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    return conn


def fetch_check_results(conn, run_id: str, document_id: str, check_id: str | None):
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = """
        SELECT
            id,
            run_id,
            document_id,
            check_id,
            check_name,
            result,
            execution_status,
            detector_used,
            display_text,
            page,
            clause_uid,
            element_id,
            segment_id,
            segment_type,
            segment_title,
            segment_order,
            is_primary_segment,
            chunk_id,
            chunk_index,
            context_trace,
            structured_data,
            quality_flags,
            created_at
        FROM check_results
        WHERE run_id = %s
          AND document_id = %s
    """
    params = [run_id, document_id]

    if check_id:
        sql += " AND check_id = %s"
        params.append(check_id)

    sql += " ORDER BY check_id, created_at"

    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]


def discover_chunk_tables(conn):
    """
    Ищем таблицы, похожие на хранилище чанков.
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND (
            table_name ILIKE '%chunk%'
            OR table_name ILIKE '%segment%'
            OR table_name ILIKE '%legal_unit%'
            OR table_name ILIKE '%element%'
            OR table_name ILIKE '%clause%'
          )
        ORDER BY table_name
    """)
    tables = [r["table_name"] for r in cur.fetchall()]

    discovered = []

    for table in tables:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
        """, (table,))
        cols = [r["column_name"] for r in cur.fetchall()]

        discovered.append({
            "table": table,
            "columns": cols,
        })

    cur.close()
    return discovered


def score_chunk_table(candidate: dict) -> int:
    """
    Простейшая эвристика: чем больше признаков chunk storage, тем выше score.
    """
    cols = set(candidate["columns"])
    score = 0

    if "document_id" in cols:
        score += 3
    if "id" in cols:
        score += 2
    if "text" in cols:
        score += 5
    if "chunk_id" in cols:
        score += 5
    if "chunk_index" in cols:
        score += 4
    if "page" in cols or "start_page" in cols:
        score += 2
    if "clause_uid" in cols:
        score += 2
    if "segment_id" in cols:
        score += 2
    if "metadata" in cols:
        score += 1

    return score


def pick_best_chunk_table(discovered: list[dict]) -> dict | None:
    if not discovered:
        return None

    ranked = sorted(
        discovered,
        key=lambda x: score_chunk_table(x),
        reverse=True,
    )

    best = ranked[0]
    if score_chunk_table(best) < 6:
        return None
    return best


def fetch_chunk_texts(conn, chunk_table: dict, document_id: str, chunk_ids: list[str]):
    """
    Пытаемся вытащить тексты chunk'ов из найденной таблицы.
    Поддерживаем разные схемы:
      - column chunk_id
      - column id
    """
    if not chunk_table or not chunk_ids:
        return {}

    import psycopg2.extras
    table = chunk_table["table"]
    cols = set(chunk_table["columns"])

    key_col = None
    if "chunk_id" in cols:
        key_col = "chunk_id"
    elif "id" in cols:
        key_col = "id"
    else:
        return {}

    text_col = "text" if "text" in cols else None
    if not text_col:
        return {}

    selected_cols = [key_col, text_col]

    optional_cols = ["document_id", "page", "start_page", "end_page", "clause_uid",
                     "segment_id", "segment_type", "chunk_index"]
    for c in optional_cols:
        if c in cols and c not in selected_cols:
            selected_cols.append(c)

    sql = f"""
        SELECT {", ".join(selected_cols)}
        FROM {table}
        WHERE {key_col} = ANY(%s)
    """

    # если в таблице есть document_id — добавляем фильтр
    if "document_id" in cols:
        sql += " AND document_id = %s"

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if "document_id" in cols:
        cur.execute(sql, (chunk_ids, document_id))
    else:
        cur.execute(sql, (chunk_ids,))

    rows = cur.fetchall()
    cur.close()

    result = {}
    for r in rows:
        result[str(r[key_col])] = dict(r)
    return result


def collect_chunk_ids(rows: list[dict]) -> list[str]:
    ids = set()

    for row in rows:
        if row.get("chunk_id"):
            ids.add(str(row["chunk_id"]))

        trace = row.get("context_trace") or []
        if isinstance(trace, list):
            for item in trace:
                if isinstance(item, dict):
                    cid = item.get("chunk_id")
                    if cid:
                        ids.add(str(cid))

    return sorted(ids)


def summarize_structured_data(sd: dict) -> dict:
    """
    Упрощённый вид structured_data: field -> {value, found, source, confidence}
    """
    out = {}
    for k, v in (sd or {}).items():
        if isinstance(v, dict):
            out[k] = {
                "value": v.get("value"),
                "found": v.get("found"),
                "source": v.get("source"),
                "confidence": v.get("confidence"),
            }
        else:
            out[k] = v
    return out


def main():
    args = get_args()
    conn = connect()

    rows = fetch_check_results(conn, args.run_id, args.document_id, args.check_id)

    if not rows:
        print("[INFO] check_results not found")
        return

    print("=" * 88)
    print("CHECK RESULTS")
    print("=" * 88)

    for row in rows:
        print(f"\ncheck_id:          {row['check_id']}")
        print(f"result:            {row.get('result')}")
        print(f"execution_status:  {row.get('execution_status')}")
        print(f"detector_used:     {row.get('detector_used')}")
        print(f"display_text:      {repr(row.get('display_text'))}")
        print(f"page:              {row.get('page')}")
        print(f"clause_uid:        {row.get('clause_uid')}")
        print(f"element_id:        {row.get('element_id')}")
        print(f"segment_id:        {row.get('segment_id')}")
        print(f"segment_type:      {row.get('segment_type')}")
        print(f"segment_title:     {row.get('segment_title')}")
        print(f"chunk_id:          {row.get('chunk_id')}")
        print(f"chunk_index:       {row.get('chunk_index')}")
        print(f"context_trace?:    {'yes' if row.get('context_trace') else 'no'}")

        if args.verbose:
            print("structured_data:")
            pprint(summarize_structured_data(row.get("structured_data") or {}), width=120)

        trace = row.get("context_trace") or []
        if trace:
            print("context_trace:")
            for item in trace:
                if not isinstance(item, dict):
                    continue
                print(
                    f"  rank={item.get('rank')} "
                    f"chunk_id={item.get('chunk_id')} "
                    f"chunk_index={item.get('chunk_index')} "
                    f"page={item.get('page')} "
                    f"clause_uid={item.get('clause_uid')} "
                    f"segment_id={item.get('segment_id')} "
                    f"score={item.get('score')}"
                )

    print("\n" + "=" * 88)
    print("DISCOVERING CHUNK TABLES")
    print("=" * 88)

    discovered = discover_chunk_tables(conn)
    for d in discovered:
        print(f"- {d['table']}: {', '.join(d['columns'][:12])}" +
              (" ..." if len(d["columns"]) > 12 else ""))

    best = pick_best_chunk_table(discovered)
    if best:
        print(f"\n[INFO] Best chunk-like table guess: {best['table']}")
    else:
        print("\n[WARN] Could not confidently detect a chunk storage table")

    chunk_ids = collect_chunk_ids(rows)
    if chunk_ids:
        print(f"\nCollected chunk_ids: {len(chunk_ids)}")
        for cid in chunk_ids[:10]:
            print(f"  - {cid}")
        if len(chunk_ids) > 10:
            print(f"  ... and {len(chunk_ids)-10} more")
    else:
        print("\n[WARN] No chunk_ids found in check_results/context_trace")

    if best and chunk_ids:
        print("\n" + "=" * 88)
        print("CHUNK TEXTS")
        print("=" * 88)

        chunk_rows = fetch_chunk_texts(conn, best, args.document_id, chunk_ids)

        if not chunk_rows:
            print("[WARN] Chunk rows not found in detected table")
        else:
            for cid in chunk_ids:
                row = chunk_rows.get(cid)
                if not row:
                    print(f"\nchunk_id={cid}\n  [NOT FOUND IN TABLE {best['table']}]")
                    continue

                print(f"\nchunk_id={cid}")
                for meta_key in ["document_id", "page", "start_page", "end_page", "clause_uid",
                                 "segment_id", "segment_type", "chunk_index"]:
                    if meta_key in row:
                        print(f"  {meta_key}: {row.get(meta_key)}")

                text = row.get("text") or ""
                preview = text[:1500]
                print("  text_preview:")
                print("  " + preview.replace("\n", "\n  "))

    conn.close()


if __name__ == "__main__":
    main()


    