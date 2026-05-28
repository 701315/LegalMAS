import sys
import os
sys.path.append(os.path.join(os.getcwd(), "src"))

def test_imports():
    errors = []
    print("🔍 Проверка импортов (исправленные пути)...\n")

    # 1. MODELS
    for mod in ["_constants", "_normalization", "_identity", "_diagnostics", "_nodes", "_tree", "_graph", "_result"]:
        path = f"services.structure._models.{mod}"
        try:
            __import__(path)
            print(f"✅ Внутренний модель {mod}: OK")
        except Exception as e:
            errors.append(f"❌ Ошибка в {path}: {e}")

    # 2. PIPELINE
    for mod in ["_utils", "_element_validation", "_quality_metrics", "_toc_workflow", "_degraded_fallback", "_segment_utils", "_core_builder"]:
        path = f"services.structure._pipeline.{mod}"
        try:
            __import__(path)
            print(f"✅ Внутренний pipeline {mod}: OK")
        except Exception as e:
            errors.append(f"❌ Ошибка в {path}: {e}")

    print("\n--- Проверка фасадов ---")
    
    try:
        from services.structure.models import ClauseNode, FileStructureResult
        print("✅ Фасад models: OK")
    except Exception as e:
        errors.append(f"❌ Фасад models ERROR: {e}")

    try:
        from services.structure.pipeline import build_file_structure, build_structure
        print("✅ Фасад pipeline: OK")
    except Exception as e:
        errors.append(f"❌ Фасад pipeline ERROR: {e}")

    try:
        from services.structure.element_classifier import annotate_elements_with_guard
        print("✅ Фасад element_classifier: OK")
    except Exception as e:
        errors.append(f"❌ Фасад element_classifier ERROR: {e}")

    if not errors:
        print("\n🎉 ВСЕ ЗЕЛЕНОЕ! Рефакторинг завершен успешно.")
    else:
        print(f"\n⚠️ ОШИБОК: {len(errors)}")
        for err in errors: print(err)

if __name__ == "__main__":
    test_imports()