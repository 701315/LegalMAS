#!/usr/bin/env python3
"""
Тест multilingual pipeline на реальном документе из MinIO.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.config import settings
from storage.artifact_store import ArtifactStore, ArtifactPath
from services.multilingual.pipeline import run_multilingual_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Test multilingual pipeline on real document"
    )
    parser.add_argument("--document-id", required=True, help="Document UUID")
    parser.add_argument("--deal-id", required=True, help="Deal UUID")
    parser.add_argument(
        "--tenant-id",
        default="11111111-1111-1111-1111-111111111111",
        help="Tenant UUID",
    )
    parser.add_argument(
        "--target-language",
        default="ru",
        help="Целевой язык (ru, en, fr, ...)",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/multilingual_test",
        help="Куда сохранить результат",
    )
    parser.add_argument(
        "--show-elements",
        type=int,
        default=20,
        help="Сколько элементов показать (0 = не показывать)",
    )

    args = parser.parse_args()

    print(f"[info] Loading document {args.document_id} from MinIO...")

    store = ArtifactStore(settings)

    raw_path = ArtifactPath.layout_raw(
        tenant_id=args.tenant_id,
        deal_id=args.deal_id,
        document_id=args.document_id,
    )

    try:
        raw_layout = store.get_json(raw_path)
    except Exception as e:
        print(f"[error] Failed to read raw_layout from MinIO: {e}")
        print(f"[info] Path was: {raw_path}")
        print()
        print("[info] Возможно документ ещё не прошёл стадию extract.")
        return 1

    print(f"[info] Loaded raw_layout:")
    print(f"       - elements: {len(raw_layout.get('elements', []))}")
    print(f"       - tables: {len(raw_layout.get('tables', []))}")
    print(f"       - pages: {raw_layout.get('metadata', {}).get('pages', 'unknown')}")
    print()

    print(f"[info] Running multilingual pipeline (target_language={args.target_language})...")
    print()

    result = run_multilingual_pipeline(
        raw_layout=raw_layout,
        target_language=args.target_language,
    )

    print("=" * 70)
    print("METRICS")
    print("=" * 70)
    qm = result.metadata.quality_metrics
    print(f"Total elements:        {len(result.elements)}")
    print(f"Visible elements:      {qm.visible_segments_count}")
    print(f"Hidden elements:       {qm.segments_hidden}")
    print(f"Parallel groups:       {qm.parallel_groups_count}")
    print(f"Orphan groups:         {qm.orphan_groups_count}")
    print(f"Monolingual groups:    {qm.monolingual_groups_count}")
    print(f"Orphan ratio:          {qm.orphan_ratio:.3f}  (цель ≤0.15)")
    print(f"Language purity (P):   {qm.language_purity_precision:.3f}  (цель ≥0.95)")
    print(f"Language purity (R):   {qm.language_purity_recall:.3f}  (цель ≥0.90)")
    print()
    print(f"Detected languages:    {result.detected_languages}")
    print(f"Target language:       {result.target_language}")
    print(f"Target ratio:          {result.metadata.target_language_ratio:.3f}")
    print(f"Is multilingual:       {result.metadata.is_multilingual}")
    print()
    print("Alignment methods:")
    for method, count in sorted(qm.alignments_by_method.items()):
        print(f"  - {method}: {count}")
    print()
    print(f"Processing warnings:   {len(result.metadata.processing_trace.warnings)}")
    print(f"Total time:            {result.metadata.processing_trace.total_seconds:.3f}s")
    print()

    if args.show_elements > 0:
        print("=" * 70)
        print(f"FIRST {args.show_elements} ELEMENTS")
        print("=" * 70)
        for i, el in enumerate(result.elements[: args.show_elements]):
            visibility = el.metadata.get("visibility_in_target_language", "unknown")
            lang = el.metadata.get("language", "unknown")
            text_preview = el.text[:80].replace("\n", " ")
            if len(el.text) > 80:
                text_preview += "..."

            hidden_info = ""
            if visibility == "hidden":
                partners = el.metadata.get("translation_of", [])
                hidden_info = f" → translation_of={partners}"

            print(f"{i:3}. [{visibility:8}] [{lang:2}] {text_preview}{hidden_info}")
        print()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    full_path = output_dir / "layout_primary_v2_full.json"
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"[info] Saved full result to {full_path}")

    mono_path = output_dir / "layout_primary_v2_monolingual.json"
    with open(mono_path, "w", encoding="utf-8") as f:
        json.dump(result.to_monolingual_layout(), f, ensure_ascii=False, indent=2)
    print(f"[info] Saved monolingual result to {mono_path}")

    summary_path = output_dir / "summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"Document: {args.document_id}\n")
        f.write(f"Target language: {args.target_language}\n")
        f.write(f"Total elements: {len(result.elements)}\n")
        f.write(f"Visible: {qm.visible_segments_count}\n")
        f.write(f"Hidden: {qm.segments_hidden}\n")
        f.write(f"Orphan ratio: {qm.orphan_ratio:.3f}\n")
        f.write(f"Purity precision: {qm.language_purity_precision:.3f}\n")
        f.write(f"Purity recall: {qm.language_purity_recall:.3f}\n")
        f.write(f"Processing time: {result.metadata.processing_trace.total_seconds:.3f}s\n")
    print(f"[info] Saved summary to {summary_path}")

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
