"""Unit tests для Monolingual Projector (Phase 4)."""

import pytest
from services.document_layout.monolingual_projector import MonolingualProjector
from services.document_layout.schemas import CanonicalAtom, CanonicalAtomSource


class TestMonolingualProjector:
    def test_target_language_atoms_projected(self):
        atom_ru = CanonicalAtom(
            element_id="atom:000001",
            page=1,
            bbox=(10.0, 10.0, 100.0, 20.0),
            source_reading_order=1,
            layout_order=1,
            text="Текст на русском языке",
            label="paragraph",
            language="ru",
            source=CanonicalAtomSource(docling_collection="texts"),
        )
        atom_en = CanonicalAtom(
            element_id="atom:000002",
            page=1,
            bbox=(10.0, 30.0, 100.0, 40.0),
            source_reading_order=2,
            layout_order=2,
            text="English text to be excluded",
            label="paragraph",
            language="en",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        projector = MonolingualProjector()
        result = projector.project([atom_ru, atom_en], target_language="ru")

        assert result.projected_atom_count == 1
        assert result.elements[0].text == "Текст на русском языке"
        assert result.elements[0].language == "ru"
        assert result.elements[0].projection_method == "native_language_atom"

    def test_shared_atoms_included_in_all_projections(self):
        atom_shared = CanonicalAtom(
            element_id="atom:000003",
            page=1,
            bbox=(10.0, 10.0, 50.0, 20.0),
            source_reading_order=1,
            layout_order=1,
            text="100 000 USD",
            label="paragraph",
            language="shared",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        projector = MonolingualProjector()
        result_ru = projector.project([atom_shared], target_language="ru")
        result_en = projector.project([atom_shared], target_language="en")

        assert result_ru.projected_atom_count == 1
        assert result_ru.elements[0].text == "100 000 USD"
        assert result_ru.elements[0].language == "shared"

        assert result_en.projected_atom_count == 1
        assert result_en.elements[0].text == "100 000 USD"

    def test_safe_split_slash_resolves_mixed_atom(self):
        atom_mixed = CanonicalAtom(
            element_id="atom:000004",
            page=1,
            bbox=(10.0, 10.0, 200.0, 20.0),
            source_reading_order=1,
            layout_order=1,
            text="Party A / Сторона А",
            label="paragraph",
            language="mixed",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        projector = MonolingualProjector()
        result_ru = projector.project([atom_mixed], target_language="ru")

        assert result_ru.mixed_atoms_resolved == 1
        assert result_ru.elements[0].text == "Сторона А"
        assert result_ru.elements[0].projection_method == "safe_split_mixed"
        assert result_ru.elements[0].language == "ru"

    def test_marker_preservation_without_opposite_language_leakage(self):
        """
        Инвариант §II.2 Принцип 7:
        Маркер из английского пункта переносится как marker-only элемент с пустым текстом.
        Английский текст пункта НЕ просачивается в русскую проекцию.
        """
        atom_en_marker = CanonicalAtom(
            element_id="atom:000005",
            page=2,
            bbox=(10.0, 50.0, 200.0, 60.0),
            source_reading_order=5,
            layout_order=5,
            text="3.2 Governing Law clause in English",
            marker="3.2",
            is_marker_only=False,
            label="list_item",
            language="en",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        projector = MonolingualProjector()
        result_ru = projector.project([atom_en_marker], target_language="ru")

        assert result_ru.projected_atom_count == 1
        el = result_ru.elements[0]
        assert el.marker == "3.2"
        assert el.is_marker_only is True
        assert el.text == ""  # Текст строго пустой!
        assert el.projection_method == "preserved_marker_without_target_text"
        assert el.needs_review is True
        assert result_ru.projected_marker_only_atom_count == 1
        assert result_ru.marker_trace.projected == 1
