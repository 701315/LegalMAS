"""
Unit tests for two-level registry loader and normalization.
"""

import pytest
import yaml

# Импортируем только саму функцию
from src.classifiers.registry_loader import get_all_trigger_names, load_registry


@pytest.fixture(autouse=True)
def reset_cache():
    # Очищаем кэш перед каждым тестом, вызывая метод у импортированной функции
    load_registry.cache_clear()
    yield
    load_registry.cache_clear()


class TestRegistryLoader:
    def test_merges_nested_runtime_structure(self, tmp_path):
        """
        Проверка, что загрузчик выносит правила из classification_runtime_v1 на верхний уровень.
        """
        registry_idx = {"document_types": [{"type": "contract_nested", "name": "Nested Type"}]}
        # Имитируем вашу структуру YAML
        instruction_yaml = {
            "type": "contract_nested",
            "classification_runtime_v1": {
                "rules": {"keywords": {"high": ["nested_key"]}},
                "filename_patterns": ["nested_pattern"],
                "trigger_definitions": {"t1": {"any_keywords": ["k1"]}},
            },
            "metadata": {"language": "en"},
        }

        (tmp_path / "registry.yaml").write_text(yaml.dump(registry_idx))
        (tmp_path / "contract_nested.yaml").write_text(yaml.dump(instruction_yaml))

        reg = load_registry(str(tmp_path))
        cfg = reg["document_types"][0]

        # Проверяем нормализацию (поля должны быть на верхнем уровне)
        assert cfg["rules"]["keywords"]["high"] == ["nested_key"]
        assert "nested_pattern" in cfg["filename_patterns"]
        assert "t1" in cfg["trigger_definitions"]
        assert cfg["metadata"]["language"] == "en"

    def test_merges_index_and_instructions(self, tmp_path):
        registry_idx = {
            "document_types": [
                {"type": "t1", "category": "cat1"},
                {"type": "t2", "category": "cat2"},
            ]
        }
        (tmp_path / "registry.yaml").write_text(yaml.dump(registry_idx))
        (tmp_path / "t1.yaml").write_text(yaml.dump({"rules": {"keywords": {"low": ["k1"]}}}))

        reg = load_registry(str(tmp_path))
        assert len(reg["document_types"]) == 2
        t1 = next(t for t in reg["document_types"] if t["type"] == "t1")
        assert t1["category"] == "cat1"  # из индекса
        assert "rules" in t1  # из инструкции

    def test_get_all_trigger_names_dynamic(self, tmp_path):
        registry_idx = {"document_types": [{"type": "doc_a"}]}
        instr_a = {
            "trigger_definitions": {
                "mortgage": {"any_keywords": ["1"]},
                "residential": {"any_keywords": ["2"]},
            }
        }
        (tmp_path / "registry.yaml").write_text(yaml.dump(registry_idx))
        (tmp_path / "doc_a.yaml").write_text(yaml.dump(instr_a))

        reg = load_registry(str(tmp_path))
        names = get_all_trigger_names(reg)
        assert "mortgage" in names
        assert "residential" in names
