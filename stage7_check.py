#!/usr/bin/env python3
"""
Quick Stage 7 checklist for LegalMAS.

Запуск:
    cd ~/projects/LegalMAS
    python stage7_check.py
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def exists(path: str) -> bool:
    return (ROOT / path).is_file()


def check_requirements() -> bool:
    req = read(ROOT / "requirements.txt")
    ok1 = "thefuzz" in req
    ok2 = "python-Levenshtein" in req
    print(f"[7.1] requirements: thefuzz      -> {'OK' if ok1 else 'MISSING'}")
    print(f"[7.1] requirements: python-Levenshtein -> {'OK' if ok2 else 'MISSING'}")
    return ok1 and ok2


def check_config() -> bool:
    cfg_path = ROOT / "src" / "core" / "config.py"
    src = read(cfg_path)
    keys = [
        "DEDUP_EXACT_ENABLED",
        "RELATIONS_FILENAME_ENABLED",
        "RELATIONS_TEXT_ENABLED",
        "RELATIONS_FILENAME_SIMILARITY_THRESHOLD",
        "RELATIONS_MAX_HOPS",
        "RELATIONS_MAX_FAMILY_SIZE",
        "FAMILY_MASTER_DOC_TYPES",
        "FAMILY_MASTER_MIN_CLASSIFICATION_LEVEL",
        "FAMILY_CLASSIFICATION_LEVEL_PRIORITY",
    ]
    all_ok = True
    for k in keys:
        ok = k in src
        print(f"[7.2] config.py: {k:40} -> {'OK' if ok else 'MISSING'}")
        all_ok = all_ok and ok
    return all_ok


def check_relations_models() -> bool:
    path = ROOT / "src" / "services" / "relations" / "models.py"
    src = read(path)
    ok_fg = "class FamilyGroup" in src and "master_classification_level" in src
    ok_dedup = "class DedupResult" in src
    print(f"[7.3] FamilyGroup in relations/models.py           -> {'OK' if ok_fg else 'MISSING'}")
    print(f"[7.3] DedupResult in relations/models.py          -> {'OK' if ok_dedup else 'MISSING'}")
    return ok_fg and ok_dedup


def check_yaml_loader() -> bool:
    path = ROOT / "src" / "services" / "classifier" / "yaml_loader.py"
    src = read(path)
    ok_method = "def get_master_doc_types" in src
    print(f"[7.4] YAMLPlaybookLoader.get_master_doc_types()   -> {'OK' if ok_method else 'MISSING'}")
    return ok_method


def check_exact_dedup_service() -> bool:
    path = ROOT / "src" / "services" / "relations" / "dedup.py"
    src = read(path)
    ok_class = "class ExactDedupService" in src
    ok_result = "DedupResult" in src
    ok_detected = "DetectedRelation" in src
    print(f"[7.5] ExactDedupService class                     -> {'OK' if ok_class else 'MISSING'}")
    print(f"[7.5] uses DedupResult                            -> {'OK' if ok_result else 'MISSING'}")
    print(f"[7.5] uses DetectedRelation                       -> {'OK' if ok_detected else 'MISSING'}")
    return ok_class and ok_result and ok_detected


def check_family_builder() -> bool:
    path = ROOT / "src" / "services" / "relations" / "family_builder.py"
    src = read(path)
    ok_class = "class FamilyBuilder" in src
    ok_yaml_load = "_load_master_doc_types" in src
    ok_level = "FAMILY_CLASSIFICATION_LEVEL_PRIORITY" in src
    print(f"[7.6] FamilyBuilder class                          -> {'OK' if ok_class else 'MISSING'}")
    print(f"[7.6] _load_master_doc_types()                     -> {'OK' if ok_yaml_load else 'MISSING'}")
    print(f"[7.6] uses FAMILY_CLASSIFICATION_LEVEL_PRIORITY    -> {'OK' if ok_level else 'MISSING'}")
    return ok_class and ok_yaml_load and ok_level


def check_relation_detector() -> bool:
    path = ROOT / "src" / "services" / "relations" / "detector.py"
    src = read(path)
    ok_method = "_find_master_document" in src
    ok_fuzz = "from thefuzz import fuzz" in src or "thefuzz" in src
    ok_level = "FAMILY_CLASSIFICATION_LEVEL_PRIORITY" in src
    print(f"[7.7] RelationDetector._find_master_document()     -> {'OK' if ok_method else 'MISSING'}")
    print(f"[7.7] uses thefuzz                                 -> {'OK' if ok_fuzz else 'MISSING'}")
    print(f"[7.7] uses FAMILY_CLASSIFICATION_LEVEL_PRIORITY    -> {'OK' if ok_level else 'MISSING'}")
    return ok_method and ok_fuzz and ok_level


def check_worker_pipeline() -> bool:
    path = ROOT / "src" / "workers" / "relations_worker.py"
    src = read(path)
    ok_dedup = "ExactDedupService" in src
    ok_builder = "FamilyBuilder" in src
    ok_detector = "RelationDetector" in src
    ok_summary = "Family masters classification summary" in src
    print(f"[7.8] relations_worker uses ExactDedupService      -> {'OK' if ok_dedup else 'MISSING'}")
    print(f"[7.8] relations_worker uses RelationDetector       -> {'OK' if ok_detector else 'MISSING'}")
    print(f"[7.8] relations_worker uses FamilyBuilder          -> {'OK' if ok_builder else 'MISSING'}")
    print(f"[7.9] logs masters classification summary          -> {'OK' if ok_summary else 'MISSING'}")
    return ok_dedup and ok_builder and ok_detector and ok_summary


def check_fixtures() -> bool:
    path = ROOT / "tests" / "fixtures" / "relations_test_data.py"
    src = read(path)
    # просто проверим наличие ключевых полей в каком‑то наборе данных
    ok = bool(src) and all(
        k in src
        for k in [
            "classification_level",
            "classification_confidence",
            "yaml_instruction_available",
            "applicable_triggers",
            "sha256_file",
        ]
    )
    print(f"[7.10] fixtures/relations_test_data.py              -> {'OK' if ok else 'MISSING/INCOMPLETE'}")
    return ok


def check_unit_tests() -> bool:
    fb = read(ROOT / "tests" / "unit" / "test_family_builder.py")
    rd = read(ROOT / "tests" / "unit" / "test_relationdetector.py")
    dd = read(ROOT / "tests" / "unit" / "test_dedup.py")

    ok_fb_level = "test_l3_master_preferred_over_l2" in fb
    ok_dd = "TestExactDedupService" in dd
    ok_rd = "TestMasterSelectionByClassificationLevel" in rd or "test_l3_master_preferred_over_l2" in rd

    print(f"[7.11] test_family_builder: L3 over L2             -> {'OK' if ok_fb_level else 'MISSING'}")
    print(f"[7.11] test_dedup: TestExactDedupService           -> {'OK' if ok_dd else 'MISSING'}")
    print(f"[7.12] test_relationdetector: master by level      -> {'OK' if ok_rd else 'MISSING'}")
    return ok_fb_level and ok_dd and ok_rd


def check_integration_tests() -> bool:
    w = read(ROOT / "tests" / "integration" / "test_relations_worker.py")
    ok_basic = "test_relations_worker_basic_flow" in w
    ok_class = "classification_awareness" in w or "classification" in w
    print(f"[7.13] integration: basic_flow                     -> {'OK' if ok_basic else 'MISSING'}")
    print(f"[7.13] integration: classification-awareness       -> {'PRESENT' if ok_class else 'MISSING (optional)'}")
    return ok_basic


def main() -> None:
    print("=== Stage 7 checklist scan ===\n")
    checks = [
        check_requirements,
        check_config,
        check_relations_models,
        check_yaml_loader,
        check_exact_dedup_service,
        check_family_builder,
        check_relation_detector,
        check_worker_pipeline,
        check_fixtures,
        check_unit_tests,
        check_integration_tests,
    ]
    all_ok = True
    for fn in checks:
        try:
            ok = fn()
            all_ok = all_ok and ok
        except Exception as e:
            print(f"{fn.__name__}: ERROR -> {e}")
            all_ok = False
        print()
    print("=== Summary ===")
    print("All critical Stage 7 pieces present:" , "YES" if all_ok else "NO")


if __name__ == "__main__":
    main()

