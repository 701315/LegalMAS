from services.pipeline_view.normalizers import extract_clause_tree_text
from services.pipeline_view.stage_structure import flatten_clause_tree


def test_extract_clause_tree_text_prefers_canonical_subtree_text() -> None:
    node = {
        "effective_uid": "main_contract:1",
        "raw_uid": "1",
        "title": "ОПРЕДЕЛЕНИЯ",
        "own_text": "Собственный текст раздела.",
        "subtree_text": "Полный текст раздела и дочерних пунктов.",
    }

    assert extract_clause_tree_text(node) == "Полный текст раздела и дочерних пунктов."


def test_extract_clause_tree_text_falls_back_to_own_text() -> None:
    node = {
        "effective_uid": "main_contract:1.1",
        "own_text": "Текст leaf-клаузы.",
        "subtree_text": None,
    }

    assert extract_clause_tree_text(node) == "Текст leaf-клаузы."


def test_extract_clause_tree_text_supports_legacy_text() -> None:
    assert extract_clause_tree_text({"text": "Legacy clause text."}) == "Legacy clause text."


def test_flatten_clause_tree_uses_effective_uid_and_canonical_text() -> None:
    node = {
        "effective_uid": "main_contract:1",
        "raw_uid": "1",
        "title": "ОПРЕДЕЛЕНИЯ",
        "level": 1,
        "start_page": 2,
        "end_page": 3,
        "own_text": "Короткий текст.",
        "subtree_text": "Полный текст раздела.",
        "children": [],
    }
    sections = []

    flatten_clause_tree(
        node,
        sections,
        level=1,
        path_indices=[0],
    )

    assert len(sections) == 1

    section = sections[0]
    assert section.id == "main_contract:1#0"
    assert section.clause_uid == "main_contract:1"
    assert section.title == "ОПРЕДЕЛЕНИЯ"
    assert section.structure_text == "Полный текст раздела."
    assert section.text_preview == "Полный текст раздела."
    assert section.page_from == 2
    assert section.page_to == 3


def test_flatten_clause_tree_keeps_legacy_clause_uid_support() -> None:
    node = {
        "clause_uid": "5.2",
        "title": "Legacy clause",
        "text": "Legacy text",
        "children": [],
    }
    sections = []

    flatten_clause_tree(
        node,
        sections,
        level=1,
        path_indices=[0],
    )

    assert len(sections) == 1
    assert sections[0].clause_uid == "5.2"
    assert sections[0].structure_text == "Legacy text"


def test_flatten_clause_tree_prefers_effective_uid_over_raw_uid() -> None:
    node = {
        "effective_uid": "appendix-1:1",
        "raw_uid": "1",
        "title": "Appendix clause",
        "subtree_text": "Appendix content",
        "children": [],
    }
    sections = []

    flatten_clause_tree(
        node,
        sections,
        level=1,
        path_indices=[0],
    )

    assert sections[0].clause_uid == "appendix-1:1"
    assert sections[0].id == "appendix-1:1#0"


    