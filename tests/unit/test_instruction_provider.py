"""
Unit-тесты для InstructionProvider Pattern.

Проверяет:
- FilesystemInstructionProvider: чтение YAML с диска (прямой путь и glob-fallback)
- DatabaseInstructionProvider: чтение из dict-снимка
- DocTypeCheckLoader: делегирование в провайдер + дефолтный провайдер

Стратегия изоляции:
- tmp_path (pytest fixture) — временная директория вместо реального реестра
- monkeypatch.setattr — изоляция settings.CLASSIFIER_REGISTRY_PATH
- Никаких БД, Celery, FastAPI импортов
"""

from __future__ import annotations

import pytest
import yaml

# ---------------------------------------------------------------------------
# Патчим settings ДО импорта модуля, чтобы избежать side-effects при импорте
# ---------------------------------------------------------------------------
# Примечание: FilesystemInstructionProvider читает settings.CLASSIFIER_REGISTRY_PATH
# в __init__, поэтому патч через monkeypatch нужен ДО создания экземпляра,
# но ПОСЛЕ импорта класса. Импортируем модуль здесь — settings читается лениво.

from engine.doc_type_checks.loader import (
    DatabaseInstructionProvider,
    DocTypeCheckLoader,
    FilesystemInstructionProvider,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def registry_dir(tmp_path):
    """Временная директория, имитирующая CLASSIFIER_REGISTRY_PATH."""
    return tmp_path


@pytest.fixture()
def sample_yaml_data() -> dict:
    """Минимальный валидный YAML-payload инструкции."""
    return {
        "doc_type": "test_contract",
        "checks_v8": [
            {
                "id": "check_001",
                "name": "Test Check",
                "severity": "high",
            }
        ],
    }


@pytest.fixture()
def yaml_file(registry_dir, sample_yaml_data):
    """YAML-файл в корне временного реестра."""
    path = registry_dir / "test_contract.yaml"
    path.write_text(yaml.dump(sample_yaml_data), encoding="utf-8")
    return path


@pytest.fixture()
def yaml_file_in_subdir(registry_dir, sample_yaml_data):
    """YAML-файл в подпапке (для glob-fallback теста)."""
    subdir = registry_dir / "real_estate" / "contracts"
    subdir.mkdir(parents=True)
    path = subdir / "nested_contract.yaml"
    path.write_text(yaml.dump(sample_yaml_data), encoding="utf-8")
    return path


# ===========================================================================
# FilesystemInstructionProvider
# ===========================================================================


class TestFilesystemInstructionProvider:

    def test_returns_yaml_data_from_direct_path(self, yaml_file, registry_dir, sample_yaml_data):
        """
        Прямой файл {registry_dir}/{doc_type}.yaml читается корректно.
        Возвращаемый dict совпадает с содержимым YAML.
        """
        provider = FilesystemInstructionProvider(registry_dir=str(registry_dir))
        result = provider.get_instruction_data("test_contract")

        assert result is not None
        assert result["doc_type"] == sample_yaml_data["doc_type"]
        assert result["checks_v8"] == sample_yaml_data["checks_v8"]

    def test_returns_none_for_missing_doc_type(self, registry_dir):
        """
        Несуществующий doc_type → None, без исключений.
        """
        provider = FilesystemInstructionProvider(registry_dir=str(registry_dir))
        result = provider.get_instruction_data("nonexistent_doc_type")

        assert result is None

    def test_glob_fallback_finds_file_in_subdir(
        self, yaml_file_in_subdir, registry_dir, sample_yaml_data
    ):
        """
        Если прямого файла нет, провайдер ищет через glob в подпапках.
        Файл в подпапке должен быть найден.
        """
        provider = FilesystemInstructionProvider(registry_dir=str(registry_dir))
        result = provider.get_instruction_data("nested_contract")

        assert result is not None
        assert result["doc_type"] == sample_yaml_data["doc_type"]

    def test_returns_empty_dict_for_empty_yaml(self, registry_dir):
        """
        Пустой YAML-файл → возвращает пустой dict, не None.
        yaml.safe_load("") возвращает None, провайдер должен вернуть {}.
        """
        path = registry_dir / "empty_doc.yaml"
        path.write_text("", encoding="utf-8")

        provider = FilesystemInstructionProvider(registry_dir=str(registry_dir))
        result = provider.get_instruction_data("empty_doc")

        # yaml.safe_load("") == None → провайдер делает `or {}` → {}
        assert result == {}

    def test_returns_none_on_invalid_yaml(self, registry_dir):
        """
        Невалидный YAML → None (graceful degradation, не crash).
        """
        path = registry_dir / "broken_doc.yaml"
        path.write_text("key: [unclosed bracket", encoding="utf-8")

        provider = FilesystemInstructionProvider(registry_dir=str(registry_dir))
        result = provider.get_instruction_data("broken_doc")

        assert result is None

    def test_uses_settings_registry_path_by_default(
        self, monkeypatch, registry_dir, sample_yaml_data
    ):
        """
        Без явного registry_dir провайдер читает путь из settings.
        """
        monkeypatch.setattr(
            "engine.doc_type_checks.loader.settings.CLASSIFIER_REGISTRY_PATH",
            str(registry_dir),
        )
        yaml_path = registry_dir / "settings_contract.yaml"
        yaml_path.write_text(yaml.dump(sample_yaml_data), encoding="utf-8")

        provider = FilesystemInstructionProvider()  # без аргументов
        result = provider.get_instruction_data("settings_contract")

        assert result is not None
        assert result["doc_type"] == sample_yaml_data["doc_type"]


# ===========================================================================
# DatabaseInstructionProvider
# ===========================================================================


class TestDatabaseInstructionProvider:

    def test_returns_data_from_snapshot_dict(self, sample_yaml_data):
        """
        Провайдер возвращает данные из переданного snapshot-словаря.
        """
        snapshot = {
            "contract_type_a": sample_yaml_data,
            "lease_agreement": {"doc_type": "lease_agreement", "checks_v8": []},
        }
        provider = DatabaseInstructionProvider(instruction_versions=snapshot)

        result = provider.get_instruction_data("contract_type_a")

        assert result is not None
        assert result["doc_type"] == "test_contract"
        assert len(result["checks_v8"]) == 1

    def test_returns_none_for_unknown_doc_type(self, sample_yaml_data):
        """
        Несуществующий doc_type → None (dict.get() возвращает None).
        """
        snapshot = {"contract_type_a": sample_yaml_data}
        provider = DatabaseInstructionProvider(instruction_versions=snapshot)

        result = provider.get_instruction_data("unknown_type_xyz")

        assert result is None

    def test_returns_none_for_empty_snapshot(self):
        """
        Пустой snapshot → None для любого doc_type.
        """
        provider = DatabaseInstructionProvider(instruction_versions={})

        result = provider.get_instruction_data("any_type")

        assert result is None

    def test_isolates_doc_types(self, sample_yaml_data):
        """
        Запрос одного doc_type не влияет на другой.
        Данные изолированы по ключу.
        """
        snapshot = {
            "type_a": {"name": "A"},
            "type_b": {"name": "B"},
        }
        provider = DatabaseInstructionProvider(instruction_versions=snapshot)

        result_a = provider.get_instruction_data("type_a")
        result_b = provider.get_instruction_data("type_b")

        assert result_a["name"] == "A"
        assert result_b["name"] == "B"

    def test_returns_exact_object_reference(self, sample_yaml_data):
        """
        Провайдер возвращает тот же объект что и в snapshot (no copy).
        Важно для performance — не клонируем тяжёлые payload'ы.
        """
        snapshot = {"contract_type_a": sample_yaml_data}
        provider = DatabaseInstructionProvider(instruction_versions=snapshot)

        result = provider.get_instruction_data("contract_type_a")

        assert result is sample_yaml_data


# ===========================================================================
# DocTypeCheckLoader — делегирование
# ===========================================================================


class TestDocTypeCheckLoader:

    def test_delegates_load_yaml_to_provider(self):
        """
        DocTypeCheckLoader._load_yaml() вызывает provider.get_instruction_data().
        Проверяем что loader делегирует, а не читает сам.
        """

        class SpyProvider:
            """Провайдер-шпион: записывает вызовы."""

            def __init__(self):
                self.calls: list[str] = []

            def get_instruction_data(self, doc_type: str) -> dict | None:
                self.calls.append(doc_type)
                return {"checks_v8": [], "doc_type_checks": [], "compliance_rules": []}

        spy = SpyProvider()
        loader = DocTypeCheckLoader(provider=spy)

        loader._load_yaml("some_doc_type")

        assert "some_doc_type" in spy.calls

    def test_default_provider_is_filesystem(self, monkeypatch, tmp_path):
        """
        DocTypeCheckLoader без явного провайдера использует FilesystemInstructionProvider.
        """
        monkeypatch.setattr(
            "engine.doc_type_checks.loader.settings.CLASSIFIER_REGISTRY_PATH",
            str(tmp_path),
        )

        loader = DocTypeCheckLoader()  # без provider=

        assert isinstance(loader.provider, FilesystemInstructionProvider)

    def test_explicit_provider_overrides_default(self):
        """
        Явно переданный провайдер используется вместо дефолтного Filesystem.
        """
        snapshot = {"my_doc": {"checks_v8": []}}
        db_provider = DatabaseInstructionProvider(instruction_versions=snapshot)

        loader = DocTypeCheckLoader(provider=db_provider)

        assert loader.provider is db_provider

    def test_load_yaml_returns_none_when_provider_returns_none(self):
        """
        Если провайдер вернул None — _load_yaml тоже возвращает None.
        """

        class NullProvider:
            def get_instruction_data(self, doc_type: str) -> dict | None:
                return None

        loader = DocTypeCheckLoader(provider=NullProvider())
        result = loader._load_yaml("any_type")

        assert result is None

    def test_load_checks_for_doc_returns_empty_for_none_yaml(self):
        """
        Если провайдер вернул None — load_checks_for_doc возвращает [].
        Не должно быть исключений.
        """

        class NullProvider:
            def get_instruction_data(self, doc_type: str) -> dict | None:
                return None

        loader = DocTypeCheckLoader(provider=NullProvider())
        result = loader.load_checks_for_doc(
            doc_type="any_type",
            applicable_triggers=[],
        )

        assert result == []