from services.structure.pipeline import build_file_structure
from typing import Any


def test_synthetic_preamble_materialized_as_first_root_node():
    """
    Тест проверяет что synthetic preamble:
    - создаётся как первый root node,
    - содержит текст преамбулы,
    - имеет правильный node_origin.

    Fixture: документ без TOC, только cover block + structural sections.
    В этом случае алгоритм создаёт preamble из leading unowned elements.
    """
    elements = [
        # actual preamble / intro block
        {
            "element_id": "e1",
            "page": 1,
            "type": "text",
            "text": "Настоящий Договор купли-продажи имущества заключен между:",
        },
        {
            "element_id": "e2",
            "page": 1,
            "type": "text",
            "text": "(1) ООО «ПРОДАВЕЦ», ОГРН 1037804009077, ИНН 7802124317, именуемое «Продавец»",
        },
        {
            "element_id": "e3",
            "page": 1,
            "type": "text",
            "text": "(2) ООО «ПОКУПАТЕЛЬ», ОГРН 1117847241236, ИНН 7802753682, именуемое «Покупатель»",
        },
        # first structural heading
        {
            "element_id": "e4",
            "page": 2,
            "type": "heading",
            "text": "1 ОПРЕДЕЛЕНИЯ",
        },
        {
            "element_id": "e5",
            "page": 2,
            "type": "text",
            "text": "1.1 «Акт» означает акт приема-передачи.",
        },
    ]

    result = build_file_structure(
        document_id="doc-preamble-simple",
        elements=elements,
        document_version_id="ver-1",
    )

    tree = result.primary_tree
    root = tree.root

    assert root, "expected non-empty root"
    first = root[0]

    assert first.raw_uid == "__preamble__"
    assert first.node_origin == "synthetic_preamble"
    assert first.start_page == 1

    own_text = first.own_text or ""
    assert "Настоящий Договор купли-продажи имущества заключен" in own_text
    assert "ПРОДАВЕЦ" in own_text
    assert "ПОКУПАТЕЛЬ" in own_text


def test_synthetic_preamble_last_run_selected_when_multiple_leading_blocks():
    """
    Тест проверяет что при нескольких leading runs выбирается ПОСЛЕДНИЙ.

    Fixture: два явно разделённых leading блока + structural heading.
    Разделение через _source_elem_i gap: первый блок idx 0-1, второй idx 10-13.
    """
    from services.structure._hierarchy_builder._core import (
        _find_leading_unowned_runs,
        _select_preamble_candidate_run,
    )

    # Симулируем элементы с явным source gap
    # (как это происходит после TOC suppression: e1/e2 = cover, потом gap, потом e7/e8/e9/e10)
    elements_with_source_i = [
        {"element_id": "e1", "page": 1, "type": "text", "text": "ДОГОВОР",
         "_source_elem_i": 0},
        {"element_id": "e2", "page": 1, "type": "text", "text": "Между",
         "_source_elem_i": 1},
        # gap: source_elem_i 2..9 = TOC (suppressed, их нет в этом списке)
        {"element_id": "e7", "page": 3, "type": "text",
         "text": "Настоящий Договор купли-продажи имущества заключен между:",
         "_source_elem_i": 10},
        {"element_id": "e8", "page": 3, "type": "text",
         "text": "(1) ООО «ПРОДАВЕЦ», ОГРН 1, ИНН 2, именуемое «Продавец»",
         "_source_elem_i": 11},
        {"element_id": "e9", "page": 3, "type": "text",
         "text": "(2) ООО «ПОКУПАТЕЛЬ», ОГРН 3, ИНН 4, именуемое «Покупатель»",
         "_source_elem_i": 12},
    ]

    # Все элементы unowned (пустой map)
    element_to_effective_uid: dict[str, str] = {}

    def stable_id_resolver(el: dict, pos: int) -> str:
        return el.get("element_id", "")

    runs = _find_leading_unowned_runs(
        elements=elements_with_source_i,
        element_to_effective_uid=element_to_effective_uid,
        stable_element_id_resolver=stable_id_resolver,
    )

    assert len(runs) == 2, f"expected 2 runs, got {len(runs)}: {runs}"

    selected = _select_preamble_candidate_run(
        runs=runs,
        elements=elements_with_source_i,
    )

    # Последний run = элементы e7/e8/e9 (positions 2, 3, 4 в элементах списка)
    assert len(selected) == 3
    assert elements_with_source_i[selected[0]]["element_id"] == "e7"
    assert elements_with_source_i[selected[-1]]["element_id"] == "e9"


def test_synthetic_preamble_not_created_when_document_starts_with_structural_heading():
    """
    Если документ начинается сразу с нормального heading,
    synthetic preamble не создаётся.
    """
    elements = [
        {"element_id": "e1", "page": 1, "type": "heading", "text": "1 ПРЕДМЕТ ДОГОВОРА"},
        {"element_id": "e2", "page": 1, "type": "text", "text": "Продавец обязуется передать ..."},
    ]

    result = build_file_structure(
        document_id="doc-2",
        elements=elements,
        document_version_id="ver-2",
    )

    root = result.primary_tree.root
    assert root
    assert root[0].raw_uid != "__preamble__"


def test_synthetic_preamble_not_created_when_document_starts_with_structural_heading():
    elements = [
        {"element_id": "e1", "page": 1, "type": "heading", "text": "1 ПРЕДМЕТ ДОГОВОРА"},
        {"element_id": "e2", "page": 1, "type": "text", "text": "Продавец обязуется передать ..."},
    ]

    result = build_file_structure(
        document_id="doc-2",
        elements=elements,
        document_version_id="ver-2",
    )

    root = result.primary_tree.root
    assert root
    assert root[0].raw_uid != "__preamble__"


def test_synthetic_preamble_uses_segment_scope_not_hardcoded_main_contract():
    """
    Regression test:
    synthetic preamble в appendix segment должен получить scope appendix_2,
    а не main_contract.
    """
    from services.structure._hierarchy_builder._core import (
        _attach_synthetic_preamble_if_needed,
    )
    from services.structure._models._nodes import MutableHierarchyNode

    elements = [
        {
            "element_id": "e1",
            "page": 11,
            "type": "text",
            "text": "ПРИЛОЖЕНИЕ 2",
            "_source_elem_i": 0,
        },
        {
            "element_id": "e2",
            "page": 11,
            "type": "text",
            "text": "Имущество",
            "_source_elem_i": 1,
        },
        {
            "element_id": "e3",
            "page": 11,
            "type": "heading",
            "text": "1 Автоматическая система",
            "_source_elem_i": 2,
        },
    ]

    root_nodes: list[MutableHierarchyNode] = []
    mutable_nodes: dict[str, MutableHierarchyNode] = {
        "appendix_2:1": MutableHierarchyNode(
            effective_uid="appendix_2:1",
            raw_uid="1",
            scope="appendix_2",
            title="Автоматическая система",
            level=1,
            node_kind="leaf",
            node_origin="semantic_heading",
            content_mode="full_text",
            citability="high",
            own_element_ids=["e3"],
            subtree_element_ids=["e3"],
            own_text="1 Автоматическая система",
            subtree_text="1 Автоматическая система",
            start_page=11,
            end_page=11,
            children=[],
            range_end_reason="segment_end",
            diagnostics={},
        )
    }
    root_nodes.append(mutable_nodes["appendix_2:1"])

    element_to_effective_uid = {"e3": "appendix_2:1"}

    def stable_id_resolver(el: dict[str, Any], pos: int) -> str:
        return el.get("element_id", "")

    diagnostics = _attach_synthetic_preamble_if_needed(
        root_nodes=root_nodes,
        mutable_nodes=mutable_nodes,
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        stable_element_id_resolver=stable_id_resolver,
        scope_name="appendix_2",
    )

    assert diagnostics is not None
    assert root_nodes[0].scope == "appendix_2"
    assert root_nodes[0].effective_uid == "appendix_2:__preamble__"


def test_last_preamble_run_respects_upstream_exclusion_flags():
    """
    Regression:
    hierarchy core не должен заново определять TOC.
    Он должен уважать upstream _excluded_from_preamble_candidate flags.
    """
    from services.structure._hierarchy_builder._core import (
        _find_leading_unowned_runs,
        _select_preamble_candidate_run,
        _collect_text_from_positions,
    )

    elements = [
        # cover block
        {
            "element_id": "e1",
            "page": 1,
            "type": "heading",
            "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ ИМУЩЕСТВА",
            "_source_elem_i": 0,
            "_excluded_from_preamble_candidate": False,
        },
        {
            "element_id": "e2",
            "page": 1,
            "type": "text",
            "text": "Между",
            "_source_elem_i": 1,
            "_excluded_from_preamble_candidate": False,
        },

        # TOC block not suppressed from body, but authoritatively excluded upstream
        {
            "element_id": "e3",
            "page": 2,
            "type": "text",
            "text": "СОДЕРЖАНИЕ",
            "_source_elem_i": 2,
            "_excluded_from_preamble_candidate": True,
        },
        {
            "element_id": "e4",
            "page": 2,
            "type": "text",
            "text": "1 ОПРЕДЕЛЕНИЯ........................................3",
            "_source_elem_i": 3,
            "_excluded_from_preamble_candidate": True,
        },
        {
            "element_id": "e5",
            "page": 2,
            "type": "text",
            "text": "(15)",
            "_source_elem_i": 4,
            "_excluded_from_preamble_candidate": True,
        },

        # actual preamble block
        {
            "element_id": "e6",
            "page": 3,
            "type": "heading",
            "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ ИМУЩЕСТВА",
            "_source_elem_i": 10,
            "_excluded_from_preamble_candidate": False,
        },
        {
            "element_id": "e7",
            "page": 3,
            "type": "text",
            "text": "Настоящий Договор купли-продажи имущества заключен между:",
            "_source_elem_i": 11,
            "_excluded_from_preamble_candidate": False,
        },
        {
            "element_id": "e8",
            "page": 3,
            "type": "text",
            "text": "(1) ООО «ПРОДАВЕЦ», ОГРН 1, ИНН 2, именуемое «Продавец»",
            "_source_elem_i": 12,
            "_excluded_from_preamble_candidate": False,
        },
        {
            "element_id": "e9",
            "page": 3,
            "type": "text",
            "text": "(2) ООО «ПОКУПАТЕЛЬ», ОГРН 3, ИНН 4, именуемое «Покупатель»",
            "_source_elem_i": 13,
            "_excluded_from_preamble_candidate": False,
        },
    ]

    element_to_effective_uid: dict[str, str] = {}

    def stable_id_resolver(el: dict, pos: int) -> str:
        return el.get("element_id", "")

    runs = _find_leading_unowned_runs(
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        stable_element_id_resolver=stable_id_resolver,
    )

    selected = _select_preamble_candidate_run(
        runs=runs,
        elements=elements,
    )

    selected_text = _collect_text_from_positions(elements, selected)

    assert "Настоящий Договор купли-продажи имущества заключен" in selected_text
    assert "СОДЕРЖАНИЕ" not in selected_text
    assert "ОПРЕДЕЛЕНИЯ........................................3" not in selected_text
    assert "(15)" not in selected_text

def test_toc_block_elements_excluded_even_if_guard_marks_them_as_false_positive():
    """
    Regression:
    guard.false_positive_indexes защищает body heading candidates от suppression
    в основном pipeline, но НЕ должен защищать их от preamble exclusion.

    toc_in_parsed_block=True должен иметь абсолютный приоритет для preamble selection.
    """
    from services.structure._pipeline._core_builder import _is_excluded_from_preamble_candidate

    # Элемент внутри TOC block, помеченный guard как false positive
    element_in_toc_block_fp = {
        "element_type": "heading_candidate",
        "text": "3 ПОКУПНАЯ",
        "metadata": {
            "toc_in_parsed_block": True,
            "toc_false_positive_by_guard": True,
            "body_recovered_from_toc": False,
        },
    }

    # Должен быть исключён из preamble, несмотря на fp_guard=True
    assert _is_excluded_from_preamble_candidate(element_in_toc_block_fp) is True

    # Элемент вне TOC block, помеченный guard как false positive
    element_outside_toc_block_fp = {
        "element_type": "body_text",
        "text": "Настоящий Договор купли-продажи имущества заключен между:",
        "metadata": {
            "toc_in_parsed_block": False,
            "toc_false_positive_by_guard": True,
            "body_recovered_from_toc": False,
        },
    }

    # Не исключаем: он вне TOC block
    assert _is_excluded_from_preamble_candidate(element_outside_toc_block_fp) is False

    # Элемент вне TOC block, без каких-либо TOC флагов — обычный body
    element_regular_body = {
        "element_type": "body_text",
        "text": "(1) ООО Продавец, ОГРН 1, ИНН 2",
        "metadata": {
            "toc_in_parsed_block": False,
            "toc_false_positive_by_guard": False,
            "body_recovered_from_toc": False,
        },
    }

    assert _is_excluded_from_preamble_candidate(element_regular_body) is False


def test_post_toc_run_is_preferred_over_pre_toc_front_matter():
    """
    Production regression:
    если есть cover/front matter до TOC, затем TOC, затем настоящая преамбула,
    selector должен выбирать post-TOC run, а не front matter до TOC.
    """
    from services.structure._hierarchy_builder._core import (
        _find_leading_unowned_runs,
        _select_preamble_candidate_run,
        _collect_text_from_positions,
    )

    elements = [
        # pre-TOC front matter
        {
            "element_id": "e1",
            "page": 1,
            "type": "text",
            "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ ИМУЩЕСТВА",
            "_source_elem_i": 0,
            "_excluded_from_preamble_candidate": False,
            "_preamble_zone": "pre_toc",
        },
        {
            "element_id": "e2",
            "page": 1,
            "type": "text",
            "text": "Между",
            "_source_elem_i": 1,
            "_excluded_from_preamble_candidate": False,
            "_preamble_zone": "pre_toc",
        },

        # TOC zone elements excluded upstream
        {
            "element_id": "e3",
            "page": 2,
            "type": "text",
            "text": "СОДЕРЖАНИ",
            "_source_elem_i": 2,
            "_excluded_from_preamble_candidate": True,
            "_preamble_zone": "in_toc",
        },
        {
            "element_id": "e4",
            "page": 2,
            "type": "text",
            "text": "Е1",
            "_source_elem_i": 3,
            "_excluded_from_preamble_candidate": True,
            "_preamble_zone": "in_toc",
        },

        # actual post-TOC preamble
        {
            "element_id": "e5",
            "page": 3,
            "type": "text",
            "text": "Настоящий Договор купли-продажи имущества заключен между:",
            "_source_elem_i": 10,
            "_excluded_from_preamble_candidate": False,
            "_preamble_zone": "post_toc",
        },
        {
            "element_id": "e6",
            "page": 3,
            "type": "text",
            "text": "(1) ООО «ПРОДАВЕЦ», ОГРН 1, ИНН 2, именуемое «Продавец»",
            "_source_elem_i": 11,
            "_excluded_from_preamble_candidate": False,
            "_preamble_zone": "post_toc",
        },
        {
            "element_id": "e7",
            "page": 3,
            "type": "text",
            "text": "(2) ООО «ПОКУПАТЕЛЬ», ОГРН 3, ИНН 4, именуемое «Покупатель»",
            "_source_elem_i": 12,
            "_excluded_from_preamble_candidate": False,
            "_preamble_zone": "post_toc",
        },
    ]

    element_to_effective_uid: dict[str, str] = {}

    def stable_id_resolver(el: dict, pos: int) -> str:
        return el.get("element_id", "")

    runs = _find_leading_unowned_runs(
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        stable_element_id_resolver=stable_id_resolver,
    )

    selected = _select_preamble_candidate_run(
        runs=runs,
        elements=elements,
    )

    selected_text = _collect_text_from_positions(elements, selected)

    assert "Настоящий Договор купли-продажи имущества заключен" in selected_text
    assert "ООО «ПРОДАВЕЦ»" in selected_text
    assert "СОДЕРЖАНИ" not in selected_text
    assert "Между" not in selected_text    


def test_synthetic_preamble_repair_disabled_for_non_primary_or_non_contract_segments():
    from services.structure._pipeline._core_builder import _should_enable_synthetic_preamble_repair

    assert _should_enable_synthetic_preamble_repair(
        segment_type="contract",
        is_primary_segment=True,
        scope_name="main_contract",
    ) is True

    assert _should_enable_synthetic_preamble_repair(
        segment_type="appendix",
        is_primary_segment=False,
        scope_name="appendix_1",
    ) is False

    assert _should_enable_synthetic_preamble_repair(
        segment_type="contract",
        is_primary_segment=False,
        scope_name="main_contract",
    ) is False

    assert _should_enable_synthetic_preamble_repair(
        segment_type="appendix",
        is_primary_segment=True,
        scope_name="appendix_1",
    ) is False

def test_owned_excluded_toc_elements_do_not_break_post_toc_preamble_scan():
    """
    Regression:
    owned элементы внутри TOC/excluded zone не должны обрывать leading scan.
    Иначе post-TOC настоящая преамбула никогда не будет достигнута.
    """
    from services.structure._hierarchy_builder._core import (
        _find_leading_unowned_runs,
        _select_preamble_candidate_run,
        _collect_text_from_positions,
    )

    elements = [
        # pre-TOC front matter
        {
            "element_id": "e1",
            "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ ИМУЩЕСТВА",
            "_source_elem_i": 0,
            "_excluded_from_preamble_candidate": False,
            "_preamble_zone": "pre_toc",
        },
        {
            "element_id": "e2",
            "text": "Между",
            "_source_elem_i": 1,
            "_excluded_from_preamble_candidate": False,
            "_preamble_zone": "pre_toc",
        },

        # TOC elements already owned by TOC-rebuild nodes
        {
            "element_id": "e3",
            "text": "3 ПОКУПНАЯ ЦЕНА........4",
            "_source_elem_i": 20,
            "_excluded_from_preamble_candidate": True,
            "_preamble_zone": "in_toc",
        },
        {
            "element_id": "e4",
            "text": "4 ПОРЯДОК ПЕРЕДАЧИ........4",
            "_source_elem_i": 22,
            "_excluded_from_preamble_candidate": True,
            "_preamble_zone": "in_toc",
        },

        # actual post-TOC preamble
        {
            "element_id": "e5",
            "text": "Настоящий Договор купли-продажи имущества заключен между:",
            "_source_elem_i": 46,
            "_excluded_from_preamble_candidate": False,
            "_preamble_zone": "post_toc",
        },
        {
            "element_id": "e6",
            "text": "(1) ООО «ПРОДАВЕЦ», ОГРН 1, ИНН 2, именуемое «Продавец»",
            "_source_elem_i": 47,
            "_excluded_from_preamble_candidate": False,
            "_preamble_zone": "post_toc",
        },
    ]

    # TOC entries owned, post-TOC preamble not owned
    element_to_effective_uid = {
        "e3": "main_contract:3",
        "e4": "main_contract:4",
    }

    def stable_id_resolver(el: dict, pos: int) -> str:
        return el.get("element_id", "")

    runs = _find_leading_unowned_runs(
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        stable_element_id_resolver=stable_id_resolver,
    )

    selected = _select_preamble_candidate_run(
        runs=runs,
        elements=elements,
    )

    selected_text = _collect_text_from_positions(elements, selected)

    assert "Настоящий Договор купли-продажи имущества заключен" in selected_text
    assert "ООО «ПРОДАВЕЦ»" in selected_text
    
