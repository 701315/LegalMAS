"""Unit tests для Language Classifier (Phase 3)."""

import pytest
from services.document_layout.language_classifier import (
    LanguageClassifier,
    classify_text,
)
from services.document_layout.schemas import CanonicalAtom, CanonicalAtomSource


class TestClassifyText:
    def test_pure_cyrillic_returns_ru(self):
        result = classify_text("Все споры и разногласия разрешаются путём переговоров.")
        assert result.language == "ru"
        assert result.confidence >= 0.95
        assert result.evidence.cyrillic_chars > 0
        assert result.evidence.latin_chars == 0
        assert result.evidence.classification_method == "script_dominant"

    def test_pure_latin_returns_en(self):
        result = classify_text("This Agreement is governed by the laws of England and Wales.")
        assert result.language == "en"
        assert result.confidence >= 0.95
        assert result.evidence.latin_chars > 0
        assert result.evidence.cyrillic_chars == 0
        assert result.evidence.classification_method == "script_dominant"

    def test_numbers_and_punctuation_return_shared(self):
        # Нумерация пункта
        assert classify_text("7.1.2").language == "shared"
        # Денежная сумма
        assert classify_text("$1,000,000.00").language == "shared"
        # Дата
        assert classify_text("12.05.2024").language == "shared"
        # Пустая строка
        assert classify_text("   ").language == "shared"

    def test_mixed_bilingual_text_returns_mixed(self):
        # Строка содержит значительное количество и кириллицы, и латиницы
        text = "Force majeure / Форс-мажорные обстоятельства сторон"
        result = classify_text(text)
        assert result.language == "mixed"
        assert result.evidence.classification_method == "mixed_scripts"
        assert result.evidence.cyrillic_chars >= 5
        assert result.evidence.latin_chars >= 5

    def test_minor_latin_in_russian_sentence_stays_ru(self):
        # 3 буквы латиницы при 30+ буквах кириллицы не делают строку mixed
        text = "Стороны заключили настоящий договор с компанией LLC 'ИнвестПроект'."
        result = classify_text(text)
        assert result.language == "ru"
        assert result.evidence.cyrillic_chars > result.evidence.latin_chars


class TestLanguageClassifierAtoms:
    def test_classify_atoms_updates_atom_fields(self):
        atom1 = CanonicalAtom(
            element_id="atom:000001",
            page=1,
            bbox=(10.0, 10.0, 100.0, 20.0),
            source_reading_order=1,
            layout_order=1,
            text="Пункт договора на русском языке",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )
        atom2 = CanonicalAtom(
            element_id="atom:000002",
            page=1,
            bbox=(10.0, 30.0, 100.0, 40.0),
            source_reading_order=2,
            layout_order=2,
            text="100 000 руб.",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        classifier = LanguageClassifier()
        enriched = classifier.classify_atoms([atom1, atom2])

        assert len(enriched) == 2
        assert enriched[0].language == "ru"
        assert enriched[0].language_evidence is not None
        assert enriched[0].language_evidence.cyrillic_chars > 0

        # "100 000 руб." имеет 3 буквы кириллицы ("руб") -> проверяем классификацию
        assert enriched[1].language in ("ru", "shared")
