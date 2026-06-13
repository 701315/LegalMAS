from uuid import uuid4

from engine.content.clause_tree_builder import ClauseTreeBuilder


def test_leaf_chunks_include_synthetic_preamble():
    doc_id = uuid4()

    tree = {
        "document_id": str(doc_id),
        "root": [
            {
                "effective_uid": "main_contract:__preamble__",
                "raw_uid": "__preamble__",
                "scope": "main_contract",
                "title": "",
                "level": 1,
                "node_kind": "leaf",
                "node_origin": "synthetic_preamble",
                "content_mode": "full_text",
                "citability_hint": "high",
                "own_element_ids": ["e1", "e2"],
                "subtree_element_ids": ["e1", "e2"],
                "start_page": 1,
                "end_page": 1,
                "children": [],
                "diagnostics": {},
            },
            {
                "effective_uid": "main_contract:1",
                "raw_uid": "1",
                "scope": "main_contract",
                "title": "ОПРЕДЕЛЕНИЯ",
                "level": 1,
                "node_kind": "leaf",
                "own_element_ids": ["e3"],
                "subtree_element_ids": ["e3"],
                "start_page": 2,
                "end_page": 2,
                "children": [],
                "diagnostics": {},
            },
        ],
    }

    layout = {
        "elements": [
            {"element_id": "e1", "page": 1, "type": "text", "text": "Продавец ООО «Альфа»"},
            {"element_id": "e2", "page": 1, "type": "text", "text": "Покупатель ООО «Бета»"},
            {"element_id": "e3", "page": 2, "type": "text", "text": "1.1 «Акт» означает ..."},
        ]
    }

    result = ClauseTreeBuilder.build_leaf_chunks(
        doc_id=doc_id,
        tree=tree,
        layout=layout,
    )

    chunks = result.chunks
    preamble_chunks = [
        ch for ch in chunks
        if (ch.get("metadata") or {}).get("effective_uid") == "main_contract:__preamble__"
    ]

    assert preamble_chunks
    assert "Продавец ООО" in preamble_chunks[0]["text"]
    assert "Покупатель ООО" in preamble_chunks[0]["text"]



    