#!/usr/bin/env python3
"""Анализ ошибок language detection в multilingual pipeline."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from services.multilingual.normalization import _script_of_char


def _detect_script(text: str) -> str:
    """Определить доминирующий скрипт в тексте."""
    script_counts = defaultdict(int)
    for ch in text:
        if not ch.isalpha():
            continue
        script = _script_of_char(ch)
        if script != "other":
            script_counts[script] += 1
    
    if not script_counts:
        return "other"
    
    return max(script_counts.items(), key=lambda x: x[1])[0]


def analyze_errors(full_json_path: str, top_n: int = 30):
    """Анализировать ошибки детекции языка."""
    
    with open(full_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    elements = data.get("elements", [])
    
    errors = {
        "latin_detected_as_cyrillic": [],
        "cyrillic_detected_as_latin": [],
        "short_text_errors": [],
        "orphan_instead_of_pair": [],
    }
    
    stats = {
        "total_elements": len(elements),
        "by_detected_language": defaultdict(int),
        "by_script": defaultdict(int),
        "by_visibility": defaultdict(int),
        "by_detection_method": defaultdict(int),
        "script_vs_language": defaultdict(lambda: defaultdict(int)),
    }
    
    for i, el in enumerate(elements):
        text = el.get("text", "")
        detected_lang = el.get("metadata", {}).get("language", "unknown")
        script = el.get("metadata", {}).get("script", "other")
        visibility = el.get("metadata", {}).get("visibility_in_target_language", "unknown")
        detection_method = el.get("metadata", {}).get("detection_method", "unknown")
        confidence = el.get("metadata", {}).get("language_confidence", 0.0)
        translation_of = el.get("metadata", {}).get("translation_of", [])
        
        actual_script = _detect_script(text)
        expected_lang_by_script = {"cyrillic": "ru", "latin": "en"}.get(actual_script, "unknown")
        
        stats["by_detected_language"][detected_lang] += 1
        stats["by_script"][actual_script] += 1
        stats["by_visibility"][visibility] += 1
        stats["by_detection_method"][detection_method] += 1
        stats["script_vs_language"][actual_script][detected_lang] += 1
        
        text_len = len(text.strip())
        is_short = text_len < 15
        
        if actual_script == "latin" and detected_lang == "ru":
            errors["latin_detected_as_cyrillic"].append({
                "index": i, "text": text[:80], "text_len": text_len,
                "script": actual_script, "detected_lang": detected_lang,
                "visibility": visibility, "detection_method": detection_method,
                "confidence": confidence, "has_translation_of": len(translation_of) > 0,
            })
        
        if actual_script == "cyrillic" and detected_lang == "en":
            errors["cyrillic_detected_as_latin"].append({
                "index": i, "text": text[:80], "text_len": text_len,
                "script": actual_script, "detected_lang": detected_lang,
                "visibility": visibility, "detection_method": detection_method,
                "confidence": confidence,
            })
        
        if is_short and detected_lang != expected_lang_by_script:
            errors["short_text_errors"].append({
                "index": i, "text": text[:80], "text_len": text_len,
                "script": actual_script, "detected_lang": detected_lang,
                "expected_lang": expected_lang_by_script,
                "detection_method": detection_method, "confidence": confidence,
            })
        
        if len(translation_of) > 0 and visibility != "hidden":
            errors["orphan_instead_of_pair"].append({
                "index": i, "text": text[:80], "detected_lang": detected_lang,
                "script": actual_script, "visibility": visibility,
                "translation_of": translation_of, "detection_method": detection_method,
            })
    
    print("=" * 80)
    print("LANGUAGE DETECTION ERROR ANALYSIS")
    print("=" * 80)
    
    print(f"\n📊 ОБЩАЯ СТАТИСТИКА")
    print(f"Total elements: {stats['total_elements']}")
    
    print(f"\n📈 By detected language:")
    for lang, count in sorted(stats["by_detected_language"].items(), key=lambda x: -x[1]):
        print(f"  {lang}: {count} ({count/stats['total_elements']*100:.1f}%)")
    
    print(f"\n📈 By script (actual text):")
    for script, count in sorted(stats["by_script"].items(), key=lambda x: -x[1]):
        print(f"  {script}: {count} ({count/stats['total_elements']*100:.1f}%)")
    
    print(f"\n📈 Script vs Detected Language matrix:")
    for script in sorted(stats["script_vs_language"].keys()):
        print(f"  {script}:")
        for lang, count in sorted(stats["script_vs_language"][script].items(), key=lambda x: -x[1]):
            print(f"    → {lang}: {count}")
    
    print(f"\n📈 By detection method:")
    for method, count in sorted(stats["by_detection_method"].items(), key=lambda x: -x[1]):
        print(f"  {method}: {count}")
    
    print(f"\n❌ ОШИБКИ")
    for error_type, error_list in errors.items():
        print(f"\n{error_type}: {len(error_list)} ошибок")
        if error_list:
            print(f"  Примеры (первые {min(top_n, len(error_list))}):")
            for err in error_list[:top_n]:
                print(f"    [{err['index']:4d}] script={err['script']:10s} detected={err['detected_lang']:3s} "
                      f"visibility={err['visibility']:20s} method={err['detection_method']:20s} "
                      f"conf={err['confidence']:.2f} len={err['text_len']:3d}")
                print(f"           text: \"{err['text']}\"")
                if err.get('has_translation_of'):
                    print(f"           ⚠️  HAS translation_of но visibility={err['visibility']}")
    
    print("\n" + "=" * 80)
    
    report_path = Path(full_json_path).parent / "error_analysis_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump({
            "stats": {k: dict(v) if isinstance(v, defaultdict) else v for k, v in stats.items()},
            "error_counts": {k: len(v) for k, v in errors.items()},
        }, f, ensure_ascii=False, indent=2)
    
    print(f"📁 Полный отчёт сохранён: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-json", required=True)
    parser.add_argument("--top-n", type=int, default=30)
    args = parser.parse_args()
    analyze_errors(args.full_json, args.top_n)
