"""
Unit tests for StructureBuilder service.
"""

from src.services.structure.builder import StructureBuilder


def _elements(*texts, page=1):
    return [
        {
            "element_id": f"e{i:03d}",
            "text": t,
            "page": page,
            "type": "text",
        }
        for i, t in enumerate(texts)
    ]


class TestStructureBuilder:
    def test_numeric_headings(self):
        elements = _elements(
            "1. Предмет договора",
            "Настоящий договор заключён между сторонами.",
            "2. Цена сделки",
            "Цена составляет 1 000 000 рублей.",
        )
        tree = StructureBuilder().build("doc1", elements)
        assert not tree.degraded
        assert len(tree.root) == 2
        assert tree.root[0].clause_uid == "1"
        assert tree.root[1].clause_uid == "2"

    def test_nested_headings(self):
        elements = _elements(
            "1. Предмет договора",
            "Текст.",
            "1.1. Объект сделки",
            "Подробности.",
            "1.2. Стоимость",
            "Цена.",
        )
        tree = StructureBuilder().build("doc1", elements)
        assert not tree.degraded
        assert len(tree.root) == 1
        assert len(tree.root[0].children) == 2
        assert tree.root[0].children[0].clause_uid == "1.1"

    def test_degraded_mode_no_headings(self):
        elements = _elements(
            "Просто обычный текст без нумерации.",
            "Ещё один абзац.",
            "И ещё один абзац.",
        )
        tree = StructureBuilder().build("doc1", elements)
        assert tree.degraded
        assert tree.structure_confidence == "LOW"

    def test_cross_reference_detection(self):
        elements = _elements(
            "1. Предмет договора",
            "В соответствии со см. п. 2.1 настоящего договора.",
            "2. Цена",
            "2.1. Порядок расчётов",
            "Расчёты производятся согласно п. 1.",
        )
        tree = StructureBuilder().build("doc1", elements)
        # Должно найти ссылку 2.1 -> 1 или наоборот
        assert len(tree.references_index) >= 1

    def test_to_dict_structure(self):
        elements = _elements("1. Заголовок", "Текст пункта.")
        tree = StructureBuilder().build("doc1", elements)
        d = tree.to_dict()
        assert "document_id" in d
        assert "root" in d
        assert "structure_confidence" in d
        assert isinstance(d["root"], list)
        assert d["root"][0]["clause_uid"] == "1"
