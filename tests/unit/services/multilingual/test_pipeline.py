# tests/unit/services/multilingual/test_pipeline.py

"""
Integration тесты для оркестратора pipeline.py.

Покрывает:
- Пустой input
- Монолингвальный документ (RU only)
- Билингвальный документ (RU+EN) с parallel_columns
- Билингвальный документ с inline separator
- Билингвальный документ с bilingual cells в tables
- Language stats computation
- Warnings aggregation
- Timings в processing_trace
- Deterministic output
- Real document scenario (Simonova SPA subset)
"""

from __future__ import annotations

import pytest

from services.multilingual.models import (
    ANALYSIS_SOURCE_KIND,
    SCHEMA_VERSION,
    PipelineResult,
)
from services.multilingual.pipeline import (
    _compute_language_stats,
    run_multilingual_pipeline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_element(
    element_id: str,
    text: str,
    page: int = 1,
    bbox: list | None = None,
    type_: str = "text",
) -> dict:
    return {
        "element_id": element_id,
        "text": text,
        "page": page,
        "bbox": bbox or [50, 100, 400, 120],
        "type": type_,
        "confidence": 1.0,
    }


def _make_raw_layout(
    elements: list,
    tables: list | None = None,
    document_id: str = "doc_001",
    document_version_id: str = "ver_001",
) -> dict:
    return {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "elements": elements,
        "tables": tables or [],
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_empty_layout(self) -> None:
        result = run_multilingual_pipeline({}, "ru")
        assert isinstance(result, PipelineResult)
        assert result.elements == []
        assert result.schema_version == SCHEMA_VERSION

    def test_empty_elements(self) -> None:
        layout = _make_raw_layout([])
        result = run_multilingual_pipeline(layout, "ru")
        assert result.elements == []

    def test_target_language_preserved(self) -> None:
        layout = _make_raw_layout([])
        result = run_multilingual_pipeline(layout, "en")
        assert result.target_language == "en"


# ---------------------------------------------------------------------------
# Monolingual document
# ---------------------------------------------------------------------------


class TestMonolingualDocument:
    def test_russian_only_document(self) -> None:
        elements = [
            _make_element("e1", "Договор купли-продажи имущества", page=1),
            _make_element("e2", "Настоящий договор заключен между сторонами", page=1),
            _make_element("e3", "Стороны договорились о нижеследующем", page=1),
        ]
        layout = _make_raw_layout(elements)
        result = run_multilingual_pipeline(layout, "ru")

        # Все сегменты visible (нет hidden)
        visible = result.get_visible_elements()
        assert len(visible) == 3
        hidden = result.get_hidden_elements()
        assert len(hidden) == 0

        # Все на русском
        for el in visible:
            assert el.metadata["language"] == "ru"

    def test_monolingual_language_ratio(self) -> None:
        elements = [_make_element("e1", "Русский текст длинный достаточно", page=1)]
        layout = _make_raw_layout(elements)
        result = run_multilingual_pipeline(layout, "ru")

        # 100% RU
        assert result.metadata.target_language_ratio == 1.0
        assert result.metadata.language_ratios == {"ru": 1.0}
        assert not result.metadata.is_multilingual


# ---------------------------------------------------------------------------
# Bilingual document with parallel columns
# ---------------------------------------------------------------------------


class TestBilingualParallelColumns:
    def test_stacked_pairs_bilingual(self) -> None:
        # Простой случай: EN элемент, за ним RU элемент, одинаковый X
        elements = [
            _make_element("e_en", "SALE AND PURCHASE AGREEMENT",
                         page=1, bbox=[100, 100, 500, 115]),
            _make_element("e_ru", "ДОГОВОР КУПЛИ-ПРОДАЖИ",
                         page=1, bbox=[100, 120, 500, 135]),
        ]
        layout = _make_raw_layout(elements)
        result = run_multilingual_pipeline(layout, "ru")

        # Ожидаем что оба сегмента classify как разные языки
        # и попадут в какую-то группу (parallel или orphan)
        assert len(result.elements) == 2

        # RU должен быть visible, EN может быть hidden если pair сформировался
        languages_in_visible = [
            el.metadata.get("language") for el in result.get_visible_elements()
        ]
        assert "ru" in languages_in_visible


# ---------------------------------------------------------------------------
# Bilingual with inline separator (Pattern 2 из Simonova SPA)
# ---------------------------------------------------------------------------


class TestInlineSeparator:
    def test_slash_separator_split_and_pair(self) -> None:
        # Реальный паттерн: "APPENDICES / ПРИЛОЖЕНИЯ"
        elements = [
            _make_element("e1", "APPENDICES / ПРИЛОЖЕНИЯ",
                         page=2, bbox=[85, 376, 247, 387]),
        ]
        layout = _make_raw_layout(elements)
        result = run_multilingual_pipeline(layout, "ru")

        # Должно быть 2 элемента (split произошёл в Layer 2)
        assert len(result.elements) == 2

        # После Layer 4 они должны быть в одной ParallelGroup
        # (split_from_single_element имеет max confidence)
        visible = result.get_visible_elements()
        hidden = result.get_hidden_elements()

        # target=ru → RU visible, EN hidden
        assert len(visible) == 1
        assert len(hidden) == 1
        assert visible[0].metadata["language"] == "ru"
        assert hidden[0].metadata["language"] == "en"


# ---------------------------------------------------------------------------
# Bilingual with appendix headers
# ---------------------------------------------------------------------------


class TestAppendixHeaders:
    def test_appendix_headers_paired_by_anchor(self) -> None:
        elements = [
            _make_element("e_app_en",
                         "APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE",
                         page=2, bbox=[85, 405, 555, 416]),
            _make_element("e_app_ru",
                         "ПРИЛОЖЕНИЕ № 1 ФОРМА АКТА",
                         page=2, bbox=[85, 420, 555, 431]),
        ]
        layout = _make_raw_layout(elements)
        result = run_multilingual_pipeline(layout, "ru")

        # target=ru → RU visible, EN hidden
        visible = result.get_visible_elements()
        assert len(visible) == 1
        assert visible[0].metadata["language"] == "ru"


# ---------------------------------------------------------------------------
# Tables processing
# ---------------------------------------------------------------------------


class TestTables:
    def test_bilingual_table_cells(self) -> None:
        tables = [{
            "page": 28,
            "rows": [
                ["№", "Объекты \\ Objects", "Стоимость"],
                ["1", "Земельный участок \\ Land plot", "500 000"],
            ],
        }]
        layout = _make_raw_layout([], tables=tables)
        result = run_multilingual_pipeline(layout, "ru")

        # Tables should be processed
        assert len(result.tables) == 1
        assert "bilingual_cells" in result.tables[0]


# ---------------------------------------------------------------------------
# Language stats
# ---------------------------------------------------------------------------


class TestLanguageStats:
    def test_compute_stats_empty(self) -> None:
        langs, ratios = _compute_language_stats([])
        assert langs == []
        assert ratios == {}

    def test_compute_stats_bilingual_document(self) -> None:
        # Проверяем через полный pipeline
        elements = [
            _make_element("e1", "Достаточно длинный русский текст для detection", page=1),
            _make_element("e2", "Sufficiently long English text for detection here", page=1),
        ]
        layout = _make_raw_layout(elements)
        result = run_multilingual_pipeline(layout, "ru")

        # Detected должен содержать оба языка
        assert "ru" in result.detected_languages
        assert "en" in result.detected_languages
        assert result.metadata.is_multilingual is True


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        elements = [
            _make_element("e1", "Русский текст", page=1),
            _make_element("e2", "English text", page=1),
        ]
        layout = _make_raw_layout(elements)

        result1 = run_multilingual_pipeline(layout, "ru")
        result2 = run_multilingual_pipeline(layout, "ru")

        # Element IDs идентичны в обоих
        ids1 = [el.element_id for el in result1.elements]
        ids2 = [el.element_id for el in result2.elements]
        assert ids1 == ids2

        # Visibility identical
        for e1, e2 in zip(result1.elements, result2.elements):
            assert e1.metadata.get("visibility_in_target_language") == \
                   e2.metadata.get("visibility_in_target_language")


# ---------------------------------------------------------------------------
# Timings in processing_trace
# ---------------------------------------------------------------------------


class TestTimings:
    def test_layer_timings_recorded(self) -> None:
        elements = [_make_element("e1", "Русский текст длинный", page=1)]
        layout = _make_raw_layout(elements)
        result = run_multilingual_pipeline(layout, "ru")

        trace = result.metadata.processing_trace
        # Все layer timings записаны и >= 0
        assert trace.layer1_seconds >= 0
        assert trace.layer2_seconds >= 0
        assert trace.layer3_seconds >= 0
        assert trace.layer4_seconds >= 0
        assert trace.layer5_seconds >= 0
        assert trace.layer6_seconds >= 0
        assert trace.total_seconds > 0

    def test_analysis_source_kind_in_metadata(self) -> None:
        layout = _make_raw_layout([])
        result = run_multilingual_pipeline(layout, "ru")

        assert (
            result.metadata.language_filter["analysis_source_kind"]
            == ANALYSIS_SOURCE_KIND
        )


# ---------------------------------------------------------------------------
# to_monolingual_layout integration
# ---------------------------------------------------------------------------


class TestMonolingualLayout:
    def test_to_monolingual_after_full_pipeline(self) -> None:
        elements = [
            _make_element("e_ru", "Русский текст",
                         page=1, bbox=[100, 100, 500, 115]),
            _make_element("e_en", "English text",
                         page=1, bbox=[100, 200, 500, 215]),
        ]
        layout = _make_raw_layout(elements)
        result = run_multilingual_pipeline(layout, "ru")

        mono = result.to_monolingual_layout()

        # mono должен содержать поля для classify_elements
        assert "document_id" in mono
        assert "document_version_id" in mono
        assert "elements" in mono
        assert "tables" in mono
        assert "metadata" in mono

        # Только visible elements
        for el in mono["elements"]:
            assert el["metadata"].get("visibility_in_target_language") != "hidden"


# ---------------------------------------------------------------------------
# Real document subset scenario
# ---------------------------------------------------------------------------


class TestRealDocumentSubset:
    """
    Простой subset из реального документа Simonova SPA.
    Проверяет что pipeline обрабатывает realistic данные.
    """

    def test_title_page_bilingual(self) -> None:
        # Титульный лист: stacked_pairs pattern
        elements = [
            # Английский заголовок
            _make_element("e_1", "REAL ESTATE SALE AND PURCHASE AGREEMENT",
                         page=1, bbox=[138, 68, 485, 82], type_="heading"),
            # Русский заголовок
            _make_element("e_2", "ДОГОВОР КУПЛИ-ПРОДАЖИ ОБЪЕКТОВ НЕДВИЖИМОСТИ",
                         page=1, bbox=[101, 89, 522, 103], type_="heading"),
            # Дата EN
            _make_element("e_3", "DATED 15 DECEMBER 2014",
                         page=1, bbox=[242, 136, 381, 147], type_="heading"),
            # Дата RU
            _make_element("e_4", "ОТ 15 ДЕКАБРЯ 2014",
                         page=1, bbox=[259, 154, 364, 165], type_="heading"),
        ]
        layout = _make_raw_layout(elements)
        result = run_multilingual_pipeline(layout, "ru")

        # Должно быть 4 elements обработано
        assert len(result.elements) == 4

        # Обнаружены оба языка
        assert "ru" in result.detected_languages
        assert "en" in result.detected_languages

    def test_toc_entries_paired(self) -> None:
        # TOC entries из page 2: числовые anchors должны спариться
        elements = [
            _make_element("e_toc_en_1", "1. DEFINITIONS...............................4",
                         page=2, bbox=[85, 66, 538, 77], type_="heading"),
            _make_element("e_toc_ru_1", "1 ОПРЕДЕЛЕНИЯ...............................4",
                         page=2, bbox=[85, 85, 538, 96], type_="heading"),
            _make_element("e_toc_en_2", "2. SUBJECT OF THE AGREEMENT.....5",
                         page=2, bbox=[85, 103, 538, 114], type_="heading"),
            _make_element("e_toc_ru_2", "2 ПРЕДМЕТ ДОГОВОРА.....5",
                         page=2, bbox=[85, 122, 538, 133], type_="heading"),
        ]
        layout = _make_raw_layout(elements)
        result = run_multilingual_pipeline(layout, "ru")

        # 4 элемента обработаны
        assert len(result.elements) == 4

        # После target=ru: 2 visible RU, 2 hidden EN (если pair сформировался)
        # Или все visible если pair не найден - depends on implementation
        visible_count = len(result.get_visible_elements())
        # Как минимум RU должны быть visible
        assert visible_count >= 2



        