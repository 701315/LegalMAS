"""Тесты парсинга fallback_texts из description поля YAML."""
import pytest

from engine.doc_type_checks.loader import (
    DocTypeCheckLoader,
    _extract_fallback_texts_from_description,
)


class TestExtractFallbackTexts:
    """Парсинг Fallback: "X" / "Y" из description."""

    @pytest.mark.parametrize("desc,expected", [
        ('Fallback: "Не установлен" / "Не удалось определить".',
         ["Не установлен", "Не удалось определить"]),
        ('Fallback: "Данные не определены".',
         ["Данные не определены"]),
        ('Fallback: "A" / "B" / "C".',
         ["A", "B", "C"]),
        ('fallback: "X" / "Y".',
         ["X", "Y"]),                              # case-insensitive
        ('Краткое описание.\nFallback: "X" / "Y".\nЕщё текст.',
         ["X", "Y"]),                              # не в начале строки
        ('  " X " / " Y ".', []),                    # нет Fallback:
        ('Fallback: "X" / "Y" / "X".', ["X", "Y"]),  # дедупликация
        ('Fallback: "Заверения не предусмотрены" / "Не удалось определить".',
         ["Заверения не предусмотрены", "Не удалось определить"]),
        ('Fallback: "Не установлено" / "Не применимо" (если объект не недвижимость).',
         ["Не установлено", "Не применимо"]),
        ('Fallback: "Не установлен".', ["Не установлен"]),
        ('', []),
        (None, []),
        ('Нет здесь ничего', []),
    ])
    def test_extract(self, desc, expected):
        assert _extract_fallback_texts_from_description(desc) == expected


class TestLoaderParsesFallback:
    """ExtractionFieldConfig.fallback_texts из description."""

    def test_from_description(self):
        loader = DocTypeCheckLoader(provider=None)
        cfg = {
            "enabled": True,
            "fields": [{
                "name": "x_details",
                "type": "string",
                "presentation": "fact",
                "description": (
                    "Описание. "
                    'Fallback: "Не установлено" / "Не удалось определить".'
                ),
            }],
        }
        result = loader._parse_extraction(cfg)
        assert result is not None
        assert result.fields[0].fallback_texts == [
            "Не установлено", "Не удалось определить",
        ]

    def test_explicit_overrides_description(self):
        loader = DocTypeCheckLoader(provider=None)
        cfg = {
            "enabled": True,
            "fields": [{
                "name": "x_details",
                "type": "string",
                "presentation": "fact",
                "description": 'Fallback: "Из description".',
                "fallback_texts": ["Из YAML"],
            }],
        }
        result = loader._parse_extraction(cfg)
        assert result is not None
        assert result.fields[0].fallback_texts == ["Из YAML"]

    def test_no_fallback_gives_empty_list(self):
        loader = DocTypeCheckLoader(provider=None)
        cfg = {
            "enabled": True,
            "fields": [{
                "name": "x_details",
                "type": "string",
                "presentation": "fact",
                "description": "Описание без Fallback.",
            }],
        }
        result = loader._parse_extraction(cfg)
        assert result is not None
        assert result.fields[0].fallback_texts == []

        