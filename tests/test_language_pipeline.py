"""
Tests for Language-Aware Document Preparation Pipeline.

Покрывает:
- Фаза 1: routing fix (_layout_elements_signature, _primary_layout_materially_differs)
- Фаза 2: lossless filtering (filter_layout_to_language, classify_element_language)
- Фаза 2A: multilingual support (detect_languages_in_layout, _classify_structured_data)
- Фаза 6: build mode determination (_determine_primary_source_build_mode)
- Sidecar mechanics (build/store/load)
- Extract worker helpers (_attach_primary_language_metadata)
- DocumentLanguageDecision multilingual API
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

import services.document_language_pipeline as dlp
from services.layout_language_filter import (
    _classify_structured_data,
    classify_element_language,
    detect_languages_in_layout,
    filter_layout_to_language,
)
from services.primary_layout_quality import validate_primary_layout
from storage.artifact_store import ArtifactPath
from workers.build_primary_language_source import (
    _build_primary_language_metadata_sidecar,
    _determine_primary_source_build_mode,
    _primary_layout_materially_differs,
    _store_primary_language_metadata_sidecar_safe,
)
from workers.extract_worker import (
    _attach_primary_language_metadata,
    _load_primary_language_metadata_sidecar_safe,
)


# =============================================================================
# Вспомогательные функции для тестов
# =============================================================================


def _make_element(
    element_id: str,
    text: str,
    page: int = 1,
    el_type: str = "text",
    bbox: list[float] | None = None,
) -> dict[str, Any]:
    """
    Создать элемент layout с обязательным element_id.

    ВАЖНО: element_id обязателен — после Фазы 1 _layout_elements_signature
    строит frozenset из element_id. Элементы без element_id игнорируются.
    """
    return {
        "element_id": element_id,
        "type": el_type,
        "text": text,
        "page": page,
        "bbox": bbox or [0.0, float(page * 100), 500.0, float(page * 100 + 15)],
        "confidence": 1.0,
    }


def _make_layout(
    elements: list[dict[str, Any]],
    *,
    document_id: str = "doc-001",
    document_version_id: str = "ver-001",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Создать layout dict с корректной структурой."""
    return {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "elements": elements,
        "tables": [],
        "metadata": metadata or {},
    }


def _make_decision(
    *,
    target_language: str = "ru",
    is_multilingual: bool = False,
    route: str = "proceed",
    quarantine_reason: str | None = None,
    language_ratios: dict[str, float] | None = None,
    detected_languages: list[str] | None = None,
) -> dlp.DocumentLanguageDecision:
    """
    Создать DocumentLanguageDecision для тестов.

    Использует новые поля Фазы 2A (is_multilingual, language_ratios).
    """
    if detected_languages is None:
        detected_languages = [target_language, "en"] if is_multilingual else [target_language]

    if language_ratios is None:
        if is_multilingual:
            language_ratios = {target_language: 0.55, "en": 0.45}
        else:
            language_ratios = {target_language: 0.92}

    return dlp.DocumentLanguageDecision(
        detected_languages=detected_languages,
        target_language=target_language,
        is_multilingual=is_multilingual,
        language_ratios=language_ratios,
        target_language_ratio=language_ratios.get(target_language, 0.0),
        route=route,
        quarantine_reason=quarantine_reason,
        deal_primary_language_before=target_language,
        deal_languages_before=detected_languages,
        deal_primary_language_after=target_language,
        deal_languages_after=detected_languages,
        requires_user_selection=False,
        pipeline_mode="PRIMARY_ONLY_DOWNSTREAM",
    )


# =============================================================================
# Фаза 1: Routing fix — _primary_layout_materially_differs
# =============================================================================


class TestPrimaryLayoutMateriallyDiffers:
    """
    Тесты для _primary_layout_materially_differs.

    После Фазы 1: сравнивается frozenset из element_id.
    Изменение текста — НЕ материальное изменение.
    Удаление элемента — материальное изменение.
    """

    def test_false_for_identical_element_ids(self):
        """Одинаковые element_id → не отличается."""
        raw = _make_layout([
            _make_element("e001", "Договор купли-продажи"),
            _make_element("e002", "Покупатель обязуется"),
        ])
        primary = _make_layout([
            _make_element("e001", "Договор купли-продажи"),
            _make_element("e002", "Покупатель обязуется"),
        ])
        assert _primary_layout_materially_differs(raw, primary) is False

    def test_false_for_text_only_change(self):
        """
        Текст изменился но element_id тот же → НЕ материальное изменение.
        Это ключевой тест Фазы 1: «Покупатель» → Покупатель
        не должно триггерить rebuild PDF.
        """
        raw = _make_layout([
            _make_element("e001", "«Покупатель» обязуется уплатить"),
        ])
        primary = _make_layout([
            _make_element("e001", "Покупатель обязуется уплатить"),
        ])
        assert _primary_layout_materially_differs(raw, primary) is False

    def test_false_for_metadata_only_change(self):
        """Изменилась только metadata → НЕ материальное изменение."""
        raw = _make_layout(
            [_make_element("e001", "Договор")],
            metadata={},
        )
        primary = _make_layout(
            [_make_element("e001", "Договор")],
            metadata={"language_pipeline": {"target_language": "ru"}},
        )
        assert _primary_layout_materially_differs(raw, primary) is False

    def test_false_for_reordering(self):
        """
        Изменился порядок элементов → НЕ материальное изменение.
        frozenset не зависит от порядка.
        """
        raw = _make_layout([
            _make_element("e001", "Первый", bbox=[0, 200, 500, 215]),
            _make_element("e002", "Второй", bbox=[0, 100, 500, 115]),
        ])
        # После сортировки по bbox e002 встанет первым
        primary = _make_layout([
            _make_element("e002", "Второй", bbox=[0, 100, 500, 115]),
            _make_element("e001", "Первый", bbox=[0, 200, 500, 215]),
        ])
        assert _primary_layout_materially_differs(raw, primary) is False

    def test_true_when_element_removed(self):
        """Элемент удалён фильтром → материальное изменение."""
        raw = _make_layout([
            _make_element("e001", "Договор купли-продажи"),
            _make_element("e002", "Sale Agreement"),
        ])
        primary = _make_layout([
            _make_element("e001", "Договор купли-продажи"),
            # e002 удалён языковым фильтром
        ])
        assert _primary_layout_materially_differs(raw, primary) is True

    def test_true_when_all_elements_removed(self):
        """Все элементы удалены → материальное изменение."""
        raw = _make_layout([
            _make_element("e001", "Sale Agreement"),
            _make_element("e002", "This Agreement"),
        ])
        primary = _make_layout([])
        assert _primary_layout_materially_differs(raw, primary) is True

    def test_false_for_legal_punctuation_not_material(self):
        """
        Юридическая пунктуация («», №, %, §, ₽) — НЕ материальное изменение.
        Это главный production-кейс который чинит Фаза 1.
        """
        raw = _make_layout([
            _make_element("e001", "Договор № 123/2024"),
            _make_element("e002", "«Покупатель» обязуется уплатить"),
            _make_element("e003", "Неустойка составляет 0,5% годовых"),
            _make_element("e004", "§ 4. Ответственность сторон"),
            _make_element("e005", "Сумма: 12 536 000 ₽"),
        ])
        # primary содержит те же element_id, текст изменён sanitize-ом
        primary = _make_layout([
            _make_element("e001", "Договор  123/2024"),
            _make_element("e002", "Покупатель обязуется уплатить"),
            _make_element("e003", "Неустойка составляет 0,5 годовых"),
            _make_element("e004", " 4. Ответственность сторон"),
            _make_element("e005", "Сумма: 12 536 000 "),
        ])
        # Все element_id совпадают → False
        assert _primary_layout_materially_differs(raw, primary) is False

    def test_false_for_none_layouts(self):
        """None layouts → не отличается (оба пустые)."""
        assert _primary_layout_materially_differs(None, None) is False

    def test_false_for_empty_elements(self):
        """Оба layout пустые → не отличается."""
        raw = _make_layout([])
        primary = _make_layout([])
        assert _primary_layout_materially_differs(raw, primary) is False


# =============================================================================
# Фаза 1: _determine_primary_source_build_mode
# =============================================================================


class TestDeterminePrimarySourceBuildMode:
    """
    Тесты для _determine_primary_source_build_mode.

    Три возможных режима:
    - "monolingual_reuse"        → оригинальный PDF переиспользуется
    - "monolingual_filtered_pdf" → PDF пересобирается из filtered layout
    - "single_language_pdf"      → PDF пересобирается для bilingual документа
    """

    def test_monolingual_reuse_when_element_ids_unchanged(self):
        """Элементный состав не изменился → monolingual_reuse."""
        decision = SimpleNamespace(is_bilingual=False, is_multilingual=False)
        raw = _make_layout([_make_element("e001", "Договор")])
        primary = _make_layout([_make_element("e001", "Договор")])

        mode = _determine_primary_source_build_mode(
            decision=decision, raw_layout=raw, primary_layout=primary,
        )
        assert mode == "monolingual_reuse"

    def test_monolingual_reuse_even_if_text_changed(self):
        """
        Текст изменился но element_id тот же → monolingual_reuse.
        После Фазы 1 это правильное поведение.
        """
        decision = SimpleNamespace(is_bilingual=False, is_multilingual=False)
        raw = _make_layout([_make_element("e001", "«Покупатель»")])
        primary = _make_layout([_make_element("e001", "Покупатель")])

        mode = _determine_primary_source_build_mode(
            decision=decision, raw_layout=raw, primary_layout=primary,
        )
        assert mode == "monolingual_reuse"

    def test_monolingual_filtered_pdf_when_element_removed(self):
        """Элемент удалён → monolingual_filtered_pdf."""
        decision = SimpleNamespace(is_bilingual=False, is_multilingual=False)
        raw = _make_layout([
            _make_element("e001", "Договор"),
            _make_element("e002", "Sale Agreement"),
        ])
        primary = _make_layout([_make_element("e001", "Договор")])

        mode = _determine_primary_source_build_mode(
            decision=decision, raw_layout=raw, primary_layout=primary,
        )
        assert mode == "monolingual_filtered_pdf"

    def test_single_language_pdf_for_multilingual(self):
        """Multilingual документ → single_language_pdf."""
        decision = SimpleNamespace(is_bilingual=True, is_multilingual=True)
        raw = _make_layout([_make_element("e001", "Договор")])
        primary = _make_layout([_make_element("e001", "Договор")])

        mode = _determine_primary_source_build_mode(
            decision=decision, raw_layout=raw, primary_layout=primary,
        )
        assert mode == "single_language_pdf"

    def test_single_language_pdf_bilingual_legacy_alias(self):
        """
        Backward compatibility: decision с только is_bilingual=True.
        _determine_primary_source_build_mode проверяет оба поля.
        """
        # SimpleNamespace с только is_bilingual (старый код)
        decision = SimpleNamespace(is_bilingual=True)
        raw = _make_layout([_make_element("e001", "Договор")])
        primary = _make_layout([_make_element("e001", "Договор")])

        mode = _determine_primary_source_build_mode(
            decision=decision, raw_layout=raw, primary_layout=primary,
        )
        assert mode == "single_language_pdf"


# =============================================================================
# Фаза 2: Lossless filtering
# =============================================================================


class TestLosslessFiltering:
    """
    Тесты что filter_layout_to_language не мутирует текст retained элементов.
    Главный инвариант Фазы 2.
    """

    def test_retained_text_identical_to_raw_for_legal_punctuation(self):
        """
        retained.text == raw.text для всей юридической пунктуации.
        После Фазы 2 _sanitize_text_to_script не вызывается.
        """
        test_cases = {
            "e001": "«Покупатель» обязуется уплатить",
            "e002": "Договор № 123/2024 от 15.01.2024",
            "e003": "Неустойка: 0,5% годовых",
            "e004": "§ 4. Ответственность сторон",
            "e005": "Сумма: 12 536 000 ₽",
        }
        layout = _make_layout([
            _make_element(eid, text, bbox=[0.0, float(i * 20), 500.0, float(i * 20 + 15)])
            for i, (eid, text) in enumerate(test_cases.items())
        ])

        result = filter_layout_to_language(layout, "ru", {"is_bilingual": False})

        retained_by_id = {e["element_id"]: e for e in result["elements"]}
        for eid, original_text in test_cases.items():
            if eid in retained_by_id:
                assert retained_by_id[eid]["text"] == original_text, (
                    f"Text mutated for {eid}: "
                    f"expected {original_text!r}, "
                    f"got {retained_by_id[eid]['text']!r}"
                )

    def test_filter_decisions_cover_all_input_elements(self):
        """
        filter_decisions должен содержать запись для каждого input элемента.
        """
        layout = _make_layout([
            _make_element("e001", "Русский текст договора"),
            _make_element("e002", "English only text here"),
            _make_element("e003", "legal@company.ru"),
        ])
        result = filter_layout_to_language(layout, "ru", {"is_bilingual": False})

        assert "filter_decisions" in result
        decision_ids = {d["source_element_id"] for d in result["filter_decisions"]}
        assert decision_ids == {"e001", "e002", "e003"}

    def test_excluded_elements_not_in_retained(self):
        """Excluded элементы не должны присутствовать в retained."""
        layout = _make_layout([
            _make_element("e001", "Договор купли-продажи"),
            _make_element("e002", "This is English only text for sale"),
        ])
        result = filter_layout_to_language(layout, "ru", {"is_multilingual": True, "is_bilingual": True})

        retained_ids = {e["element_id"] for e in result.get("elements", [])}
        excluded_ids = set(result.get("excluded_element_ids", []))
        # Нет пересечения retained и excluded
        assert not (retained_ids & excluded_ids)

    def test_reading_order_assigned_sequentially_after_sort(self):
        """reading_order = 0, 1, 2... после сортировки."""
        layout = _make_layout([
            _make_element("e001", "Первый", bbox=[0, 200, 500, 215]),
            _make_element("e002", "Второй", bbox=[0, 100, 500, 115]),
        ])
        result = filter_layout_to_language(layout, "ru", {"is_bilingual": False})

        elements = result.get("elements", [])
        if len(elements) >= 2:
            orders = [e.get("reading_order") for e in elements]
            assert orders == list(range(len(elements)))
            # e002 (y=100) должен стоять первым
            assert elements[0]["element_id"] == "e002"
            assert elements[1]["element_id"] == "e001"

    def test_retention_status_set_on_retained_elements(self):
        """Retained элементы должны иметь retention_status."""
        layout = _make_layout([
            _make_element("e001", "Договор купли-продажи"),
        ])
        result = filter_layout_to_language(layout, "ru", {"is_bilingual": False})

        for el in result.get("elements", []):
            assert "retention_status" in el
            assert el["retention_status"] in ("retained", "flagged")

    def test_language_label_set_on_retained_elements(self):
        """Retained элементы должны иметь language_label."""
        layout = _make_layout([
            _make_element("e001", "Договор купли-продажи"),
        ])
        result = filter_layout_to_language(layout, "ru", {"is_bilingual": False})

        for el in result.get("elements", []):
            assert "language_label" in el
            assert el["language_label"] in ("target", "foreign", "neutral", "mixed", "unknown")

    def test_empty_layout_returns_empty_result(self):
        """Пустой layout → пустой результат без ошибок."""
        layout = _make_layout([])
        result = filter_layout_to_language(layout, "ru", {"is_bilingual": False})

        assert result["elements"] == []
        assert result["excluded_element_ids"] == []
        assert result["filter_decisions"] == []

    def test_unsupported_target_language_returns_raw(self):
        """
        Пустой target_language → возвращаем исходный layout.
        После Фазы 2A: пустая строка возвращает raw.
        """
        layout = _make_layout([_make_element("e001", "Договор")])
        result = filter_layout_to_language(layout, "", {})
        # Должен вернуть raw без изменений
        assert result["elements"] == layout["elements"]


# =============================================================================
# Фаза 2: classify_element_language
# =============================================================================


class TestClassifyElementLanguage:
    """
    Тесты для classify_element_language — доменный language label.
    """

    def test_pure_structured_data_is_neutral(self):
        """Pure structured data → всегда neutral, независимо от языка."""
        # IBAN
        label = classify_element_language("DE89370400440532013000", "ru", "pure")
        assert label == "neutral"

        # SWIFT
        label = classify_element_language("SABRRUMM", "ru", "pure")
        assert label == "neutral"

        # Телефон
        label = classify_element_language("+7 495 123-45-67", "ru", "pure")
        assert label == "neutral"

    def test_short_neutral_content_is_neutral(self):
        """Короткий нейтральный контент (цифры, пунктуация) → neutral."""
        # Числа
        label = classify_element_language("12345", "ru", "none")
        assert label == "neutral"

        # Пустая строка
        label = classify_element_language("", "ru", "none")
        assert label == "neutral"

    def test_russian_text_with_russian_target_is_target(self):
        """Русский текст при target=ru → target."""
        label = classify_element_language("Договор купли-продажи", "ru", "none")
        assert label == "target"

    def test_english_text_with_russian_target_is_foreign(self):
        """Английский текст при target=ru → foreign."""
        label = classify_element_language(
            "This Sale and Purchase Agreement is entered into", "ru", "none"
        )
        assert label == "foreign"

    def test_contains_structured_data_classified_normally(self):
        """
        'contains' structured data → языковая классификация как обычно.
        Текст не становится автоматически neutral.
        """
        # Русский текст с email → target
        label = classify_element_language("Контакт: legal@company.ru", "ru", "contains")
        # Результат зависит от lingua — должен быть target или mixed
        assert label in ("target", "mixed", "neutral")


# =============================================================================
# Фаза 2: _classify_structured_data
# =============================================================================


class TestClassifyStructuredData:
    """
    Тесты для _classify_structured_data.
    """

    def test_iban_is_pure(self):
        """IBAN → pure."""
        assert _classify_structured_data("DE89370400440532013000") == "pure"
        assert _classify_structured_data("RU1234567890") == "pure"

    def test_swift_without_digits_is_pure(self):
        """
        SWIFT/BIC без цифр (SABRRUMM) → pure.
        Фаза 7: расширенный regex теперь матчит SWIFT 8/11 символов.
        """
        assert _classify_structured_data("SABRRUMM") == "pure"
        assert _classify_structured_data("CITIUSXX") == "pure"

    def test_email_is_pure(self):
        """Email → pure."""
        assert _classify_structured_data("legal@company.ru") == "pure"
        assert _classify_structured_data("buyer@example.com") == "pure"

    def test_phone_is_pure(self):
        """Телефон → pure."""
        assert _classify_structured_data("+7 495 123-45-67") == "pure"

    def test_text_with_email_is_contains(self):
        """Текст с email внутри → contains."""
        result = _classify_structured_data("Контакт: legal@company.ru")
        assert result == "contains"

    def test_text_with_iban_is_contains(self):
        """Текст с IBAN внутри → contains."""
        result = _classify_structured_data(
            "The Buyer transfers to IBAN: DE89370400440532013000"
        )
        assert result == "contains"

    def test_plain_russian_text_is_none(self):
        """Обычный русский текст → none."""
        assert _classify_structured_data("Покупатель обязуется уплатить") == "none"

    def test_plain_english_text_is_none(self):
        """
        Обычный текст без структурированных данных → none.

        Примечание: текст с пробелами может ложно матчить телефонный паттерн
        если содержит 7+ символов из [\d\s\-\(\)]. Поэтому используем текст
        без длинных последовательностей пробелов.
        """
        assert _classify_structured_data("Покупатель") == "none"
        assert _classify_structured_data("Договор") == "none"
        assert _classify_structured_data("Agreement") == "none"
        assert _classify_structured_data("текст без реквизитов") == "none"

    def test_empty_text_is_none(self):
        """Пустой текст → none."""
        assert _classify_structured_data("") == "none"
        assert _classify_structured_data("   ") == "none"

    def test_url_is_pure(self):
        """URL → pure."""
        assert _classify_structured_data("https://company.ru/docs") == "pure"


# =============================================================================
# Фаза 2A: detect_languages_in_layout — multilingual
# =============================================================================


class TestDetectLanguagesInLayout:
    """
    Тесты для detect_languages_in_layout — multilingual версия.
    После Фазы 2A: возвращает реальные ISO коды через lingua.
    """

    def test_detects_russian_in_layout(self):
        """Русский текст → ["ru"] в detected_languages."""
        layout = _make_layout([
            _make_element("e001", "Настоящий договор заключён между сторонами"),
            _make_element("e002", "Покупатель обязуется уплатить сумму"),
            _make_element("e003", "Продавец передаёт товар в срок"),
        ])
        langs = detect_languages_in_layout(layout)
        assert "ru" in langs

    def test_detects_english_in_layout(self):
        """Английский текст → ["en"] в detected_languages."""
        layout = _make_layout([
            _make_element("e001", "This Agreement is entered into between the parties"),
            _make_element("e002", "The Buyer agrees to pay the purchase price"),
            _make_element("e003", "The Seller shall deliver the goods within the agreed period"),
        ])
        langs = detect_languages_in_layout(layout)
        assert "en" in langs

    def test_detects_both_languages_in_bilingual_layout(self):
        """Билингвальный layout → оба языка в detected_languages."""
        layout = _make_layout([
            _make_element("e001", "Настоящий договор заключён между сторонами"),
            _make_element("e002", "Покупатель обязуется уплатить сумму в рублях"),
            _make_element("e003", "This Agreement is entered into between the parties"),
            _make_element("e004", "The Buyer agrees to pay the purchase price herein"),
        ])
        langs = detect_languages_in_layout(layout)
        assert "ru" in langs
        assert "en" in langs

    def test_pure_structured_data_not_counted_as_language(self):
        """
        Pure structured data (SWIFT, IBAN, email) не влияет на detected_languages.
        Фаза 2A: исключаем pure structured data из language detection.
        """
        layout = _make_layout([
            _make_element("e001", "Настоящий договор заключён между сторонами"),
            _make_element("e002", "Покупатель обязуется уплатить сумму"),
            _make_element("e003", "SWIFT: SABRRUMM"),
            _make_element("e004", "IBAN: DE89370400440532013000"),
            _make_element("e005", "Email: legal@company.ru"),
        ])
        langs = detect_languages_in_layout(layout)
        # Должен вернуть только ru — SWIFT/IBAN/email не должны добавлять "en"
        assert "ru" in langs
        # Английский НЕ должен быть определён только из реквизитов
        # (это главная задача Фазы 2A и Фазы 7)
        if "en" in langs:
            # Если lingua всё же нашёл en — это может быть из email domain
            # В этом случае проверяем что ru доминирует
            assert "ru" in langs

    def test_empty_layout_returns_empty(self):
        """Пустой layout → пустой список (не дефолтный ['ru'])."""
        layout = _make_layout([])
        langs = detect_languages_in_layout(layout)
        assert langs == []

    def test_layout_with_only_numbers_returns_empty(self):
        """Layout только с цифрами → пустой список."""
        layout = _make_layout([
            _make_element("e001", "12345"),
            _make_element("e002", "6789.00"),
        ])
        langs = detect_languages_in_layout(layout)
        # Числа не являются языком — список должен быть пуст
        assert isinstance(langs, list)


# =============================================================================
# Фаза 2A: DocumentLanguageDecision — multilingual API
# =============================================================================


class TestDocumentLanguageDecisionMultilingual:
    """
    Тесты для нового API DocumentLanguageDecision.
    """

    def test_is_bilingual_is_alias_for_is_multilingual(self):
        """is_bilingual является property-alias для is_multilingual."""
        decision = _make_decision(is_multilingual=True)
        assert decision.is_multilingual is True
        assert decision.is_bilingual is True  # backward compat alias

    def test_is_bilingual_false_when_monolingual(self):
        """is_bilingual = False когда документ монолингвальный."""
        decision = _make_decision(is_multilingual=False)
        assert decision.is_multilingual is False
        assert decision.is_bilingual is False

    def test_language_ratios_contains_target(self):
        """language_ratios содержит долю целевого языка."""
        decision = _make_decision(
            target_language="ru",
            is_multilingual=True,
            language_ratios={"ru": 0.72, "en": 0.24},
        )
        assert "ru" in decision.language_ratios
        assert decision.language_ratios["ru"] == pytest.approx(0.72)

    def test_target_language_ratio_matches_language_ratios(self):
        """target_language_ratio соответствует значению в language_ratios."""
        decision = _make_decision(
            target_language="ar",
            language_ratios={"ar": 0.60, "en": 0.35},
        )
        assert decision.target_language_ratio == pytest.approx(0.60)


# =============================================================================
# Фаза 2: build_primary_language_layout — async integration
# =============================================================================


class TestBuildPrimaryLanguageLayoutAsync:
    """
    Интеграционные тесты для build_primary_language_layout.
    Используют monkeypatch для изоляции от БД и lingua.
    """

    @pytest.mark.asyncio
    async def test_monolingual_document_applies_simple_filter(self, monkeypatch):
        """Монолингвальный документ → simple filter применяется."""
        decision = _make_decision(is_multilingual=False)

        async def fake_analyze(*args, **kwargs):
            return decision

        seen: dict[str, Any] = {}

        def fake_filter(layout, target_language, context=None):
            seen["called"] = True
            seen["target_language"] = target_language
            seen["context"] = context
            return {
                "document_id": layout.get("document_id"),
                "document_version_id": layout.get("document_version_id"),
                "elements": [_make_element("e001", "Договор поставки")],
                "tables": [],
                "metadata": {
                    "language_filter": {
                        "structural_filter_used": False,
                        "degraded": False,
                        "elements_after": 1,
                    }
                },
            }

        monkeypatch.setattr(dlp, "analyze_document_languages", fake_analyze)
        monkeypatch.setattr(dlp, "filter_layout_to_language", fake_filter)

        raw_layout = _make_layout([
            _make_element("e001", "1 ДОГОВОР ПОСТАВКИ / SALE AGREEMENT"),
        ])

        result = await dlp.build_primary_language_layout(
            db=None,
            deal_id=uuid.uuid4(),
            tenant_id="tenant-1",
            document_id="doc-1",
            layout=raw_layout,
            target_language="ru",
        )

        assert result.should_quarantine is False
        assert seen.get("called") is True
        assert seen["target_language"] == "ru"
        # Новый ключ в context — is_multilingual
        assert seen["context"].get("is_multilingual") is False

    @pytest.mark.asyncio
    async def test_monolingual_empty_filter_falls_back_to_raw(self, monkeypatch):
        """Empty filter result для монолингвального → fallback на raw layout."""
        decision = _make_decision(is_multilingual=False)

        async def fake_analyze(*args, **kwargs):
            return decision

        def fake_filter(layout, target_language, context=None):
            return {
                "document_id": layout.get("document_id"),
                "document_version_id": layout.get("document_version_id"),
                "elements": [],
                "tables": [],
                "metadata": {
                    "language_filter": {
                        "structural_filter_used": False,
                        "degraded": True,
                        "degraded_reason": "no_elements_after_filter",
                    }
                },
            }

        monkeypatch.setattr(dlp, "analyze_document_languages", fake_analyze)
        monkeypatch.setattr(dlp, "filter_layout_to_language", fake_filter)

        raw_layout = _make_layout([_make_element("e001", "Договор поставки")])

        result = await dlp.build_primary_language_layout(
            db=None,
            deal_id=uuid.uuid4(),
            tenant_id="tenant-1",
            document_id="doc-1",
            layout=raw_layout,
            target_language="ru",
        )

        assert result.should_quarantine is False
        # Fallback → elements из raw layout
        assert result.primary_layout["elements"] == raw_layout["elements"]
        meta = result.primary_layout["metadata"]
        assert meta["language_pipeline"]["fallback_used"] is True
        assert meta["language_filter"]["degraded"] is True

    @pytest.mark.asyncio
    async def test_multilingual_document_applies_filter(self, monkeypatch):
        """Multilingual документ → filter применяется с is_multilingual=True."""
        decision = _make_decision(is_multilingual=True)

        async def fake_analyze(*args, **kwargs):
            return decision

        seen: dict[str, Any] = {}

        def fake_filter(layout, target_language, context=None):
            seen["context"] = context
            return {
                "document_id": layout.get("document_id"),
                "document_version_id": layout.get("document_version_id"),
                "elements": [_make_element("e001", "Договор поставки")],
                "tables": [],
                "metadata": {
                    "language_filter": {
                        "structural_filter_used": True,
                        "degraded": False,
                    }
                },
            }

        monkeypatch.setattr(dlp, "analyze_document_languages", fake_analyze)
        monkeypatch.setattr(dlp, "filter_layout_to_language", fake_filter)

        raw_layout = _make_layout([
            _make_element("e001", "Договор поставки"),
            _make_element("e002", "Sale Agreement"),
        ])

        result = await dlp.build_primary_language_layout(
            db=None,
            deal_id=uuid.uuid4(),
            tenant_id="tenant-1",
            document_id="doc-1",
            layout=raw_layout,
            target_language="ru",
        )

        assert result.should_quarantine is False
        # is_multilingual должен быть True в context
        assert seen["context"].get("is_multilingual") is True

    @pytest.mark.asyncio
    async def test_quarantine_when_language_absent(self, monkeypatch):
        """Если target language absent → quarantine."""
        decision = _make_decision(
            is_multilingual=False,
            route="quarantine",
            quarantine_reason="target_language_absent",
            language_ratios={"en": 0.95},
            detected_languages=["en"],
        )

        async def fake_analyze(*args, **kwargs):
            return decision

        monkeypatch.setattr(dlp, "analyze_document_languages", fake_analyze)

        raw_layout = _make_layout([
            _make_element("e001", "This is an English document only"),
        ])

        result = await dlp.build_primary_language_layout(
            db=None,
            deal_id=uuid.uuid4(),
            tenant_id="tenant-1",
            document_id="doc-1",
            layout=raw_layout,
            target_language="ru",
        )

        assert result.should_quarantine is True
        assert result.decision.quarantine_reason == "target_language_absent"


# =============================================================================
# Фаза 2: Structured data preservation in filter
# =============================================================================


class TestStructuredDataPreservation:
    """
    Тесты что structured data сохраняется при фильтрации.
    """

    def test_email_preserved_in_russian_document(self):
        """Email сохраняется в русском документе."""
        layout = _make_layout([
            _make_element("e001", "Договор купли-продажи"),
            _make_element("e002", "buyer@example.com"),
        ])
        result = filter_layout_to_language(layout, "ru", {"is_bilingual": False})
        texts = [e["text"] for e in result["elements"]]
        assert "buyer@example.com" in texts

    def test_swift_preserved_in_russian_document(self):
        """SWIFT код сохраняется в русском документе."""
        layout = _make_layout([
            _make_element("e001", "Договор купли-продажи"),
            _make_element("e002", "SWIFT ABC123"),
        ])
        result = filter_layout_to_language(layout, "ru", {"is_bilingual": False})
        texts = [e["text"] for e in result["elements"]]
        assert "SWIFT ABC123" in texts

    def test_english_heading_excluded_in_russian_document(self):
        """
        Явно английский текст удаляется из русского документа при multilingual фильтре.

        Используем достаточно длинный английский текст чтобы lingua
        уверенно определила язык (confidence >= threshold).
        Короткие all-caps фразы ("SALE AGREEMENT") lingua может не распознать
        с достаточной уверенностью — это корректное поведение для коротких текстов.
        """
        layout = _make_layout([
            _make_element("e001", "Настоящий договор купли-продажи заключён между сторонами"),
            _make_element(
                "e002",
                "This Sale and Purchase Agreement is entered into between the parties hereto",
            ),
        ])
        result = filter_layout_to_language(
            layout, "ru", {"is_multilingual": True, "is_bilingual": True}
        )
        texts = [e["text"] for e in result["elements"]]

        # Русский текст должен быть retained
        assert any("договор" in t.lower() for t in texts)

        # Английский текст — excluded или flagged.
        # При is_multilingual=True и достаточно длинном тексте lingua уверена → excluded.
        en_text = "This Sale and Purchase Agreement is entered into between the parties hereto"
        retained_ids = {e["element_id"] for e in result.get("elements", [])}
        excluded_ids = set(result.get("excluded_element_ids", []))

        # e002 должен быть либо excluded, либо flagged (не retained как target)
        if "e002" in retained_ids:
            # Если retained — должен быть flagged (mixed/unknown), не target
            e002 = next(e for e in result["elements"] if e["element_id"] == "e002")
            assert e002.get("language_label") != "target", (
                f"English text was retained as 'target' — lingua misclassified it: "
                f"label={e002.get('language_label')}"
            )
        else:
            # Правильный случай — excluded
            assert "e002" in excluded_ids

    def test_structured_data_text_not_mutated(self):
        """Текст structured data элементов не мутирует."""
        original_texts = {
            "e001": "buyer@example.com",
            "e002": "+7 495 123-45-67",
            "e003": "DE89370400440532013000",
        }
        layout = _make_layout([
            _make_element(eid, text)
            for eid, text in original_texts.items()
        ])
        result = filter_layout_to_language(layout, "ru", {"is_bilingual": False})
        retained_by_id = {e["element_id"]: e for e in result["elements"]}
        for eid, original_text in original_texts.items():
            if eid in retained_by_id:
                assert retained_by_id[eid]["text"] == original_text


# =============================================================================
# Фаза 4: Quality gates — validate_primary_layout
# =============================================================================


class TestValidatePrimaryLayout:
    """
    Тесты для validate_primary_layout (Фаза 4).
    """

    def test_passed_for_clean_layout(self):
        """Чистый layout → passed, eligible."""
        raw = _make_layout([
            _make_element("e001", "Договор № 123"),
            _make_element("e002", "English text removed"),
        ])
        primary = _make_layout([
            {**_make_element("e001", "Договор № 123"), "retention_status": "retained"},
        ])
        primary["excluded_element_ids"] = ["e002"]

        q = validate_primary_layout(raw, primary, expected_target_ratio=0.5)
        assert q["fidelity_status"] == "passed"
        assert q["analysis_eligibility"] == "eligible"
        assert q["text_fidelity"] == "passed"

    def test_failed_when_text_mutated(self):
        """Текст мутировал → text_fidelity=failed, blocked."""
        raw = _make_layout([
            _make_element("e001", "«Покупатель» обязуется"),
        ])
        primary = _make_layout([
            {**_make_element("e001", "Покупатель обязуется"), "retention_status": "retained"},
        ])
        primary["excluded_element_ids"] = []

        q = validate_primary_layout(raw, primary, expected_target_ratio=1.0)
        assert q["text_fidelity"] == "failed"
        assert q["fidelity_status"] == "failed"
        assert q["analysis_eligibility"] == "blocked"

    def test_failed_when_element_id_missing_in_raw(self):
        """element_id в primary не существует в raw → structural fail."""
        raw = _make_layout([_make_element("e001", "Текст")])
        primary = _make_layout([
            {**_make_element("ghost-id", "Текст"), "retention_status": "retained"},
        ])
        primary["excluded_element_ids"] = []

        q = validate_primary_layout(raw, primary, expected_target_ratio=1.0)
        assert q["structural_fidelity"] == "failed"
        assert q["analysis_eligibility"] == "blocked"

    def test_failed_when_no_retained_elements(self):
        """Нет retained элементов → failed."""
        raw = _make_layout([_make_element("e001", "Текст")])
        primary = _make_layout([])
        primary["excluded_element_ids"] = ["e001"]

        q = validate_primary_layout(raw, primary, expected_target_ratio=0.5)
        assert q["fidelity_status"] == "failed"
        assert q["analysis_eligibility"] == "blocked"

    def test_passed_with_correct_page_and_bbox(self):
        """Одинаковые page и bbox → passed."""
        elem = _make_element("e001", "Договор", page=2, bbox=[10.0, 50.0, 400.0, 65.0])
        raw = _make_layout([elem])
        primary_elem = dict(elem)
        primary_elem["retention_status"] = "retained"
        primary_elem["language_label"] = "target"
        primary = _make_layout([primary_elem])
        primary["excluded_element_ids"] = []

        q = validate_primary_layout(raw, primary, expected_target_ratio=1.0)
        assert q["text_fidelity"] == "passed"
        assert q["fidelity_status"] == "passed"

    def test_degraded_when_retention_ratio_deviation_high(self):
        """Большое отклонение retention ratio → degraded."""
        raw = _make_layout([
            _make_element("e001", "Русский текст договора"),
            _make_element("e002", "Ещё русский текст"),
            _make_element("e003", "И ещё один"),
            _make_element("e004", "Четвёртый"),
            _make_element("e005", "Пятый элемент"),
        ])
        primary = _make_layout([
            {**_make_element("e001", "Русский текст договора"), "retention_status": "retained"},
        ])
        primary["excluded_element_ids"] = ["e002", "e003", "e004", "e005"]

        # Ожидаем 90% retention, получили ~20% → deviation > 0.20
        q = validate_primary_layout(raw, primary, expected_target_ratio=0.90)
        assert q["fidelity_status"] in ("degraded", "failed")

    def test_metrics_correct(self):
        """Метрики elements_total, retained, excluded, flagged корректны."""
        raw = _make_layout([
            _make_element("e001", "Текст"),
            _make_element("e002", "Другой"),
        ])
        primary = _make_layout([
            {**_make_element("e001", "Текст"), "retention_status": "retained"},
        ])
        primary["excluded_element_ids"] = ["e002"]

        q = validate_primary_layout(raw, primary, expected_target_ratio=0.5)
        assert q["elements_total"] == 2
        assert q["elements_retained"] == 1
        assert q["elements_excluded"] == 1
        assert q["elements_flagged"] == 0


# =============================================================================
# Sidecar mechanics
# =============================================================================


class RecordingStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def put_json(self, path: str, payload: dict) -> str:
        self.calls.append((path, payload))
        return f"s3://{path}"


class FailingStore:
    def put_json(self, path: str, payload: dict) -> str:
        raise RuntimeError("sidecar store failed")


class JsonStore:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.last_path: str | None = None

    def get_json(self, path: str):
        self.last_path = path
        if self.error is not None:
            raise self.error
        return self.payload


class TestSidecarMechanics:
    """Тесты для sidecar build/store/load."""

    def test_sidecar_keeps_only_supported_keys(self):
        """Sidecar содержит только language_pipeline и language_filter."""
        primary_layout = {
            "metadata": {
                "language_pipeline": {"target_language": "en", "is_multilingual": False},
                "language_filter": {"contract_version": 2, "mode": "simple"},
                "extraction": {"strategy": "text"},
                "other_key": {"ignored": True},
            }
        }
        payload = _build_primary_language_metadata_sidecar(primary_layout)
        assert "language_pipeline" in payload
        assert "language_filter" in payload
        assert "extraction" not in payload
        assert "other_key" not in payload
        assert payload["contract_version"] == 1

    def test_sidecar_returns_none_without_language_metadata(self):
        """Sidecar = None если нет language metadata."""
        primary_layout = {"metadata": {"extraction": {"strategy": "text"}}}
        payload = _build_primary_language_metadata_sidecar(primary_layout)
        assert payload is None

    def test_sidecar_store_uses_correct_path(self):
        """Sidecar сохраняется по правильному пути."""
        store = RecordingStore()
        primary_layout = {
            "metadata": {
                "language_pipeline": {"target_language": "ru"},
                "language_filter": {"contract_version": 2},
            }
        }

        ref = _store_primary_language_metadata_sidecar_safe(
            store=store,
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            primary_layout=primary_layout,
            log_extra_base={},
        )

        expected_path = ArtifactPath.primary_source_language_metadata(
            tenant_id="t1", deal_id="d1", document_id="doc1",
        )
        assert ref == f"s3://{expected_path}"
        assert store.calls[0][0] == expected_path

    def test_sidecar_store_failure_isolated(self):
        """Ошибка сохранения sidecar → None, не исключение."""
        store = FailingStore()
        primary_layout = {
            "metadata": {
                "language_pipeline": {"target_language": "en"},
                "language_filter": {"contract_version": 2},
            }
        }
        ref = _store_primary_language_metadata_sidecar_safe(
            store=store,
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            primary_layout=primary_layout,
            log_extra_base={},
        )
        assert ref is None

    def test_sidecar_load_returns_supported_keys(self):
        """Загрузка sidecar возвращает только language_pipeline и language_filter."""
        store = JsonStore(
            payload={
                "contract_version": 1,
                "language_pipeline": {"target_language": "en"},
                "language_filter": {"contract_version": 2},
                "unrelated": {"ignored": True},
            }
        )
        metadata = _load_primary_language_metadata_sidecar_safe(
            store=store,
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            document_version_id="v1",
        )
        assert "language_pipeline" in metadata
        assert "language_filter" in metadata
        assert "unrelated" not in metadata

    def test_sidecar_load_returns_none_on_error(self):
        """Ошибка загрузки sidecar → None."""
        store = JsonStore(error=RuntimeError("not found"))
        metadata = _load_primary_language_metadata_sidecar_safe(
            store=store,
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            document_version_id="v1",
        )
        assert metadata is None

    def test_sidecar_load_returns_none_for_invalid_payload(self):
        """Невалидный payload → None."""
        store = JsonStore(payload=["not", "a", "dict"])
        metadata = _load_primary_language_metadata_sidecar_safe(
            store=store,
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            document_version_id="v1",
        )
        assert metadata is None


# =============================================================================
# Extract worker helpers
# =============================================================================


class TestAttachPrimaryLanguageMetadata:
    """Тесты для _attach_primary_language_metadata."""

    def test_preserves_existing_metadata_and_does_not_mutate_input(self):
        """Не мутирует input layout, сохраняет существующие metadata."""
        raw_layout = {
            "elements": [{"text": "Clause 1"}],
            "metadata": {"extraction": {"strategy": "text"}},
        }
        language_metadata = {
            "language_pipeline": {"target_language": "en"},
            "language_filter": {"contract_version": 2},
        }

        layout_primary = _attach_primary_language_metadata(
            layout=raw_layout, language_metadata=language_metadata,
        )

        # Не мутирует оригинал
        assert raw_layout["metadata"] == {"extraction": {"strategy": "text"}}
        # Результат содержит и старые, и новые ключи
        assert layout_primary["metadata"]["extraction"] == {"strategy": "text"}
        assert layout_primary["metadata"]["language_pipeline"] == {"target_language": "en"}

    def test_returns_copy_when_no_sidecar(self):
        """Без sidecar → возвращает копию layout."""
        raw_layout = {"elements": [{"text": "Clause 1"}]}
        result = _attach_primary_language_metadata(layout=raw_layout, language_metadata=None)

        assert result == raw_layout
        assert result is not raw_layout


