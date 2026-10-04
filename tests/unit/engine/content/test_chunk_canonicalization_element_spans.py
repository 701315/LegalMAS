"""Юнит-тест: build_sized_chunks_from_leaf генерирует element_spans."""
import uuid

from engine.content.chunk_canonicalization import build_sized_chunks_from_leaf


def _make_leaf(text, effective_uid, element_ids, start_page=1, end_page=1):
    return {
        "text": text,
        "metadata": {
            "effective_uid": effective_uid,
            "raw_uid": effective_uid.split(":")[-1] if ":" in effective_uid else effective_uid,
            "scope": "main_contract",
            "node_kind": "leaf",
            "element_ids": element_ids,
            "start_page": start_page,
            "end_page": end_page,
        },
    }


def test_element_spans_built_when_info_map_provided():
    doc_id = uuid.uuid4()
    leaf = _make_leaf(
        text="ДОГОВОР\n\nМежду ООО Ромашка",
        effective_uid="main_contract:S",
        element_ids=["el_1", "el_2"],
        start_page=1, end_page=2,
    )
    info_map = {
        "el_1": {"text": "ДОГОВОР", "page": 1, "_seq": 0},
        "el_2": {"text": "Между ООО Ромашка", "page": 2, "_seq": 1},
    }

    sized = build_sized_chunks_from_leaf(
        doc_id=doc_id,
        leaf_chunks=[leaf],
        target_tokens=300, max_tokens=800, overlap_ratio=0.15,
        total_pages=10,
        element_info_map=info_map,
    )

    assert len(sized) == 1
    spans = sized[0]["metadata"].get("element_spans")
    assert spans == [
        ["el_1", 1, 0, 7],
        ["el_2", 2, 9, 26],
    ]


def test_element_spans_not_built_without_info_map():
    """Backward compatibility: без element_info_map - нет element_spans."""
    doc_id = uuid.uuid4()
    leaf = _make_leaf(
        text="ДОГОВОР\n\nМежду ООО Ромашка",
        effective_uid="main_contract:S",
        element_ids=["el_1", "el_2"],
    )

    sized = build_sized_chunks_from_leaf(
        doc_id=doc_id,
        leaf_chunks=[leaf],
        target_tokens=300, max_tokens=800, overlap_ratio=0.15,
        total_pages=10,
        element_info_map=None,
    )

    assert len(sized) == 1
    assert "element_spans" not in sized[0]["metadata"]


def test_element_spans_partial_when_some_elements_missing():
    """Часть элементов не найдена - offsets найденных используются."""
    doc_id = uuid.uuid4()
    leaf = _make_leaf(
        text="ДОГОВОР\n\nМежду ООО Ромашка",
        effective_uid="main_contract:S",
        element_ids=["el_1", "el_2", "el_3"],
    )
    info_map = {
        "el_1": {"text": "ДОГОВОР", "page": 1, "_seq": 0},
        "el_2": {"text": "ОТСУТСТВУЕТ", "page": 1, "_seq": 1},
        "el_3": {"text": "Между ООО Ромашка", "page": 2, "_seq": 2},
    }

    sized = build_sized_chunks_from_leaf(
        doc_id=doc_id,
        leaf_chunks=[leaf],
        target_tokens=300, max_tokens=800, overlap_ratio=0.15,
        total_pages=10,
        element_info_map=info_map,
    )

    spans = sized[0]["metadata"].get("element_spans")
    # el_2 отсутствует, el_1 и el_3 - есть
    assert [s[0] for s in spans] == ["el_1", "el_3"]


def test_element_spans_respect_seq_order_not_input_order():
    """element_ids могут прийти в произвольном порядке - сортируем по _seq."""
    doc_id = uuid.uuid4()
    leaf = _make_leaf(
        text="ПЕРВЫЙ\n\nВТОРОЙ",
        effective_uid="main_contract:X",
        element_ids=["el_2", "el_1"],  # обратный порядок
    )
    info_map = {
        "el_1": {"text": "ПЕРВЫЙ", "page": 1, "_seq": 0},
        "el_2": {"text": "ВТОРОЙ", "page": 1, "_seq": 1},
    }

    sized = build_sized_chunks_from_leaf(
        doc_id=doc_id,
        leaf_chunks=[leaf],
        target_tokens=300, max_tokens=800, overlap_ratio=0.15,
        total_pages=10,
        element_info_map=info_map,
    )

    spans = sized[0]["metadata"].get("element_spans")
    assert [s[0] for s in spans] == ["el_1", "el_2"]
