#!/usr/bin/env python3
"""
Full QA Validation for Deal Processing
Usage: .venv/bin/python scripts/qa_deal_validation.py
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import json
from pathlib import Path

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 15432,
    "database": "mas_dd",
    "user": "mas",
    "password": "mas_super_password"
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def validate_deal(deal_id, doc_ids):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    report = {
        "deal_id": deal_id,
        "documents": [],
        "segmentation_status": "unknown",
        "embeddings_status": "unknown",
        "checks_status": "unknown",
        "segmentation": {},
        "embeddings": {},
        "checks_summary": {},
        "runs_info": {}
    }
    
    # Documents
    cur.execute("""
        SELECT id, filename, status, created_at, updated_at, 
               classification_confidence, doc_type, classification_outcome
        FROM documents
        WHERE deal_id = %s::uuid AND id = ANY(%s::uuid[])
    """, (deal_id, doc_ids))
    
    for d in cur.fetchall():
        report["documents"].append(dict(d))
    
    # Segmentation - document_segments
    for doc_id in doc_ids:
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN segment_type = 'clause' THEN 1 ELSE 0 END) as clauses,
                   SUM(CASE WHEN segment_type = 'section' THEN 1 ELSE 0 END) as sections
            FROM document_segments
            WHERE document_id = %s::uuid
        """, (doc_id,))
        seg = cur.fetchone()
        report["segmentation"][doc_id] = dict(seg)
        total = seg['total'] or 0
        if total > 0:
            report["segmentation_status"] = "completed"
        elif report["segmentation_status"] != "completed":
            report["segmentation_status"] = "pending"
    
    # Embeddings - check segment_chunks_ref in document_segments
    for doc_id in doc_ids:
        cur.execute("""
            SELECT COUNT(*) as with_chunks
            FROM document_segments
            WHERE document_id = %s::uuid
              AND segment_chunks_ref IS NOT NULL
        """, (doc_id,))
        emb = cur.fetchone()
        chunks = emb['with_chunks'] or 0
        report["embeddings"][doc_id] = {"chunks": chunks}
        if chunks > 0:
            report["embeddings_status"] = "completed"
        elif report["embeddings_status"] != "completed":
            report["embeddings_status"] = "pending"
    
    # Runs info
    cur.execute("""
        SELECT id, status, total_checks, completed_checks, 
               started_at, completed_at, pipeline_strategy
        FROM runs
        WHERE deal_id = %s::uuid
        ORDER BY created_at DESC
        LIMIT 5
    """, (deal_id,))
    
    runs = cur.fetchall()
    for r in runs:
        report["runs_info"][str(r['id'])] = dict(r)
    
    # Check results - join with runs
    cur.execute("""
        SELECT cr.result as status, cr.severity, COUNT(*) as count
        FROM check_results cr
        JOIN runs r ON cr.run_id = r.id
        WHERE r.deal_id = %s::uuid
        GROUP BY cr.result, cr.severity
    """, (deal_id,))
    
    for r in cur.fetchall():
        key = f"{r['status']}_{r['severity']}"
        report["checks_summary"][key] = r['count']
    
    total_checks = sum(report["checks_summary"].values())
    report["checks_status"] = "completed" if total_checks > 0 else "pending"
    
    cur.close()
    conn.close()
    
    return report


if __name__ == "__main__":
    deal_id = "84ac2558-cd3e-44fe-af80-bd3dd4bd0795"
    doc_ids = [
        "a9a8c1f5-6b00-4562-99ee-962f22de6d1a",
        "4612e993-5515-46b0-aa81-9df5cbe66ae8"
    ]
    
    report = validate_deal(deal_id, doc_ids)
    
    output_path = Path(f"/tmp/qa_report_{deal_id[:8]}.json")
    output_path.write_text(json.dumps(report, indent=2, default=str))
    
    print(f"✅ QA Report generated: {output_path}")
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    
    print(f"\n📄 Documents: {len(report['documents'])}")
    for d in report['documents']:
        print(f"   - {d['filename']}")
        print(f"     Status: {d['status']}")
        print(f"     Doc Type: {d['doc_type']}")
        print(f"     Classification: {d['classification_outcome']}")
    
    print(f"\n🔪 Segmentation Status: {report['segmentation_status']}")
    for doc_id, seg in report['segmentation'].items():
        total = seg.get('total') or 0
        clauses = seg.get('clauses') or 0
        print(f"   - {doc_id[:8]}...: {total} segments ({clauses} clauses)")
    
    print(f"\n🔢 Embeddings/Chunks Status: {report['embeddings_status']}")
    for doc_id, emb in report['embeddings'].items():
        chunks = emb.get('chunks') or 0
        print(f"   - {doc_id[:8]}...: {chunks} segments with chunks")
    
    print(f"\n📋 Runs: {len(report['runs_info'])}")
    for run_id, run in report['runs_info'].items():
        print(f"   - {run_id[:8]}...: {run['status']} ({run['completed_checks']}/{run['total_checks']} checks)")
    
    print(f"\n✅ Checks Status: {report['checks_status']}")
    for status_sev, count in report['checks_summary'].items():
        print(f"   - {status_sev}: {count}")
    
    print(f"\n{'='*80}")
    print("RECOMMENDATION")
    print(f"{'='*80}")
    
    if report['segmentation_status'] == "pending":
        print("⚠️  Segmentation pipeline has not run yet.")
        print("   → Check semantic enrichment worker")
    elif report['embeddings_status'] == "pending":
        print("⚠️  Chunks/Embeddings not generated yet.")
        print("   → Check chunking pipeline")
    elif report['checks_status'] == "pending":
        print("⚠️  Checks not executed yet.")
        print("   → Run check runner for this deal")
    else:
        print("✅ All pipeline stages completed!")
