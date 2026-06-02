"""
tests/engine/content/test_canonical_chunks.py

Unit tests for canonical chunk infrastructure (Sprint 3).

Тестируют КОНТРАКТ и ИНВАРИАНТЫ системы через актуальный API
FrozenHierarchyNode / ClauseTree / CrossReferenceGraph.
"""

from __future__ import annotations

import uuid

import pytest

from engine.content.chunk_canonicalization import (
    build_sized_chunks_from_leaf,
    calc_position_ratio,
    ensure_clause_metadata,
)
from engine.content.chunk_ids import build_subclause_chunk_id
from services.structure.models import (
    DEFAULT_SCOPE,
    NODE_KIND_LEAF,
    NODE_KIND_SECTION,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_CONTRACT,
    ClauseTree,
    CrossReference,
    CrossReferenceGraph,
    CrossReferenceStats,
    CrossSegmentRef,
    FrozenHierarchyNode,
    generate_scope_name,
    make_effective_uid,
    split_effective_uid,
)


TEST_DOC_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

_STUB_HASH = "aabbccdd11223344"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_leaf(
    effective_uid: str,
    *,
    level: int = 2,
    start_page: int = 1,
    end_page: int = 1,
    own_text: str = "Some text.",
    own_element_ids: tuple[str, ...] = ("e1",),
) -> FrozenHierarchyNode:
    """Создаёт валидный frozen leaf node."""
    scope, raw_uid = effective_uid.split(":", 1)
    subtree_ids = own_element_ids
    return FrozenHierarchyNode(
        effective_uid=effective_uid,
        title="Leaf",
        level=level,
        raw_uid=raw_uid,
        scope=scope,
        node_kind=NODE_KIND_LEAF,
        structural_hash=_STUB_HASH,
        own_element_ids=own_element_ids,
        subtree_element_ids=subtree_ids,
        own_text=own_text,
        subtree_text=own_text,
        start_page=start_page,
        end_page=end_page,
    )


def _make_section(
    effective_uid: str,
    children: tuple[FrozenHierarchyNode, ...],
    *,
    level: int = 1,
    start_page: int = 1,
    end_page: int = 3,
) -> FrozenHierarchyNode:
    """Создаёт frozen section node с children."""
    scope, raw_uid = effective_uid.split(":", 1)
    subtree_ids = tuple(
        eid
        for child in children
        for eid in child.subtree_element_ids
    )
    return FrozenHierarchyNode(
        effective_uid=effective_uid,
        title="Section",
        level=level,
        raw_uid=raw_uid,
        scope=scope,
        node_kind=NODE_KIND_SECTION,
        structural_hash=_STUB_HASH,
        own_element_ids=(),
        subtree_element_ids=subtree_ids,
        own_text=None,
        subtree_text=None,
        start_page=start_page,
        end_page=end_page,
        children=children,
    )


def _empty_graph() -> CrossReferenceGraph:
    return CrossReferenceGraph.from_references(
        document_id="doc-1",
        references=(),
        stats=CrossReferenceStats(
            references_count=0,
            unique_sources_count=0,
            unique_targets_count=0,
        ),
    )


# ── TestEffectiveUidFormat ────────────────────────────────────────────────────

class TestEffectiveUidFormat:
    """КОНТРАКТ: effective_uid = "scope:raw_uid"."""

    def test_roundtrip_property(self) -> None:
        """ИНВАРИАНТ: make -> split -> make даёт тот же результат."""
        test_cases = [
            ("maincontract", "1.1"),
            ("appendix_1", "A.2.1"),
            ("contract_2", "3.14.15.92"),
        ]
        for scope, raw_uid in test_cases:
            uid = make_effective_uid(scope, raw_uid)
            parsed_scope, parsed_raw = split_effective_uid(uid)
            assert parsed_scope == scope
            assert parsed_raw == raw_uid
            assert make_effective_uid(parsed_scope, parsed_raw) == uid

    def test_whitespace_normalization(self) -> None:
        """КОНТРАКТ: пробелы в начале/конце должны удаляться."""
        uid = make_effective_uid(" maincontract ", " 1.1 ")
        assert uid == "maincontract:1.1"
        assert " " not in uid

    def test_rejects_empty_raw_uid(self) -> None:
        """ИНВАРИАНТ: raw_uid не может быть пустым."""
        with pytest.raises(ValueError, match=r"raw_uid must be non-empty"):
            make_effective_uid("maincontract", "")
        with pytest.raises(ValueError, match=r"raw_uid must be non-empty"):
            make_effective_uid("maincontract", "   ")

    def test_rejects_invalid_scope_format(self) -> None:
        """ИНВАРИАНТ: scope должен быть валидным идентификатором."""
        for invalid_scope in ["appendix-1", "appendix 1", "appendix.1"]:
            with pytest.raises(ValueError, match="Invalid scope"):
                make_effective_uid(invalid_scope, "A.1")

    def test_split_rejects_invalid_format(self) -> None:
        """КОНТРАКТ: split требует формат 'scope:raw_uid'."""
        with pytest.raises(ValueError, match=r"Expected canonical.*format"):
            split_effective_uid("maincontract1.2.3")
        with pytest.raises(ValueError, match="effective_uid must be non-empty"):
            split_effective_uid("")
        with pytest.raises(ValueError, match="raw_uid must be non-empty"):
            split_effective_uid("maincontract:")

    def test_preserves_complex_raw_uid(self) -> None:
        """КОНТРАКТ: raw_uid может содержать точки и сложную структуру."""
        uid = make_effective_uid("maincontract", "1.2.3.4.5")
        scope, raw_uid = split_effective_uid(uid)
        assert raw_uid == "1.2.3.4.5"

    def test_rejects_colon_inside_raw_uid(self) -> None:
        """КОНТРАКТ: raw_uid в canonical effective_uid не должен содержать ':'."""
        with pytest.raises(ValueError, match=r"raw_uid must not contain ':'"):
            split_effective_uid("maincontract:1.2:extra_info")

        with pytest.raises(ValueError, match=r"raw_uid must not contain ':'"):
            make_effective_uid("maincontract", "1.2:extra_info")


# ── TestScopeNaming ───────────────────────────────────────────────────────────

class TestScopeNaming:
    """КОНТРАКТ: generate_scope_name формирует canonical имя области."""

    def test_first_contract_is_default_scope(self) -> None:
        assert generate_scope_name(SEGMENT_TYPE_CONTRACT, 0) == DEFAULT_SCOPE

    def test_appendix_numbering_starts_from_1(self) -> None:
        assert generate_scope_name(SEGMENT_TYPE_APPENDIX, 0) == "appendix_1"
        assert generate_scope_name(SEGMENT_TYPE_APPENDIX, 1) == "appendix_2"
        assert generate_scope_name(SEGMENT_TYPE_APPENDIX, 2) == "appendix_3"

    def test_contract_numbering_after_main(self) -> None:
        assert generate_scope_name(SEGMENT_TYPE_CONTRACT, 1) == "contract_2"
        assert generate_scope_name(SEGMENT_TYPE_CONTRACT, 5) == "contract_6"

    def test_generated_scope_is_valid_for_effective_uid(self) -> None:
        for segment_type in [SEGMENT_TYPE_CONTRACT, SEGMENT_TYPE_APPENDIX]:
            for order in range(5):
                scope = generate_scope_name(segment_type, order)
                uid = make_effective_uid(scope, "1.1")
                assert ":" in uid
                assert uid.startswith(scope)


# ── TestFrozenHierarchyNodeInvariants ─────────────────────────────────────────

class TestFrozenHierarchyNodeInvariants:
    """
    ИНВАРИАНТЫ FrozenHierarchyNode (заменяет удалённый ClauseNode).

    1. effective_uid, scope, raw_uid консистентны
    2. child.scope == parent.scope
    3. child.level > parent.level (строгая иерархия)
    4. leaf nodes не имеют детей
    5. section nodes обязаны иметь детей
    6. end_page >= start_page
    """

    def test_scope_consistency_invariant(self) -> None:
        """ИНВАРИАНТ: scope из effective_uid == явно заданный scope."""
        node = _make_leaf("maincontract:1.1")
        assert node.scope == "maincontract"
        assert node.raw_uid == "1.1"

        with pytest.raises(ValueError, match="scope mismatch"):
            FrozenHierarchyNode(
                effective_uid="maincontract:1.1",
                title="Leaf",
                level=2,
                raw_uid="1.1",
                scope="appendix_1",   # несоответствие!
                node_kind=NODE_KIND_LEAF,
                structural_hash=_STUB_HASH,
                own_element_ids=("e1",),
                subtree_element_ids=("e1",),
                start_page=1,
                end_page=1,
            )

    def test_child_scope_must_match_parent(self) -> None:
        """ИНВАРИАНТ: все узлы в одном дереве имеют один scope."""
        child_main = _make_leaf("maincontract:1.1.1", level=3, own_element_ids=("ea",))
        child_appendix = _make_leaf("appendix_1:A.1", level=3, own_element_ids=("eb",))

        with pytest.raises(ValueError, match="scope mismatch"):
            _make_section(
                "maincontract:1.1",
                children=(child_main, child_appendix),  # разные scope!
                level=2,
            )

    def test_strict_level_hierarchy(self) -> None:
        """ИНВАРИАНТ: child.level > parent.level."""
        child_same_level = _make_leaf("maincontract:1.1.1", level=2)

        with pytest.raises(ValueError, match="Child level must be > parent level"):
            _make_section(
                "maincontract:1.1",
                children=(child_same_level,),
                level=2,
            )

    def test_leaf_cannot_have_children(self) -> None:
        """ИНВАРИАНТ: leaf node — конечный узел."""
        child = _make_leaf("maincontract:1.1.1", level=3)

        with pytest.raises(ValueError, match="must not have children"):
            FrozenHierarchyNode(
                effective_uid="maincontract:1.1",
                title="Leaf",
                level=2,
                raw_uid="1.1",
                scope="maincontract",
                node_kind=NODE_KIND_LEAF,
                structural_hash=_STUB_HASH,
                own_element_ids=(),
                subtree_element_ids=("e1",),
                start_page=1,
                end_page=2,
                children=(child,),
            )

    def test_section_must_have_children(self) -> None:
        """ИНВАРИАНТ: section node обязан иметь детей."""
        with pytest.raises(ValueError, match="must have children"):
            FrozenHierarchyNode(
                effective_uid="maincontract:1",
                title="Empty Section",
                level=1,
                raw_uid="1",
                scope="maincontract",
                node_kind=NODE_KIND_SECTION,
                structural_hash=_STUB_HASH,
                own_element_ids=(),
                subtree_element_ids=(),
                start_page=1,
                end_page=1,
                children=(),
            )

    def test_page_range_invariant(self) -> None:
        """ИНВАРИАНТ: end_page >= start_page."""
        with pytest.raises(ValueError, match=r"end_page must be >= .*start_page"):
            FrozenHierarchyNode(
                effective_uid="maincontract:1.1",
                title="Invalid Pages",
                level=2,
                raw_uid="1.1",
                scope="maincontract",
                node_kind=NODE_KIND_LEAF,
                structural_hash=_STUB_HASH,
                own_element_ids=("e1",),
                subtree_element_ids=("e1",),
                start_page=5,
                end_page=3,   # end < start!
            )


# ── TestClauseTreeDuplicateDetection ─────────────────────────────────────────

class TestClauseTreeDuplicateDetection:
    """ИНВАРИАНТ: ClauseTree не содержит дубликаты effective_uid."""

    def test_allows_unique_uids(self) -> None:
        n1 = _make_leaf("maincontract:1.1", own_element_ids=("e1",))
        n2 = _make_leaf("maincontract:1.2", own_element_ids=("e2",))

        tree = ClauseTree(
            document_id="doc-1",
            root=[n1, n2],
            cross_reference_graph=_empty_graph(),
            structure_confidence="MEDIUM",
        )

        assert len(tree.nodes_index) == 2
        assert "maincontract:1.1" in tree.nodes_index
        assert "maincontract:1.2" in tree.nodes_index

    def test_rejects_duplicate_at_root(self) -> None:
        n1 = _make_leaf("maincontract:1.1", own_element_ids=("e1",))
        n2 = _make_leaf("maincontract:1.1", own_element_ids=("e2",))

        with pytest.raises(ValueError, match="duplicate effective_uid"):
            ClauseTree(
                document_id="doc-1",
                root=[n1, n2],
                cross_reference_graph=_empty_graph(),
                structure_confidence="MEDIUM",
            )

    def test_rejects_duplicate_in_hierarchy(self) -> None:
        grandchild = _make_leaf("maincontract:1.1.1", level=3, own_element_ids=("e1",))
        duplicate = _make_leaf("maincontract:1.1.1", level=3, own_element_ids=("e2",))

        child = _make_section(
            "maincontract:1.1",
            children=(grandchild,),
            level=2,
            start_page=1,
            end_page=2,
        )

        parent = _make_section(
            "maincontract:1",
            children=(child, duplicate),
            level=1,
            start_page=1,
            end_page=3,
        )

        with pytest.raises(ValueError, match="duplicate effective_uid"):
            ClauseTree(
                document_id="doc-1",
                root=[parent],
                cross_reference_graph=_empty_graph(),
                structure_confidence="MEDIUM",
            )


# ── TestCanonicalChunkIdGeneration ────────────────────────────────────────────

class TestCanonicalChunkIdGeneration:
    """КОНТРАКТ: build_subclause_chunk_id детерминирован и уникален."""

    def test_deterministic_property(self) -> None:
        id1 = build_subclause_chunk_id(
            doc_id=TEST_DOC_ID,
            effective_uid="maincontract:1.1",
            subchunk_index=0,
        )
        id2 = build_subclause_chunk_id(
            doc_id=TEST_DOC_ID,
            effective_uid="maincontract:1.1",
            subchunk_index=0,
        )
        assert id1 == id2
        assert isinstance(id1, str)
        assert len(id1) > 0

    def test_different_inputs_give_different_ids(self) -> None:
        base_id = build_subclause_chunk_id(
            doc_id=TEST_DOC_ID,
            effective_uid="maincontract:1.1",
            subchunk_index=0,
        )
        assert build_subclause_chunk_id(
            doc_id=TEST_DOC_ID,
            effective_uid="maincontract:1.1",
            subchunk_index=1,
        ) != base_id
        assert build_subclause_chunk_id(
            doc_id=TEST_DOC_ID,
            effective_uid="maincontract:1.2",
            subchunk_index=0,
        ) != base_id
        assert build_subclause_chunk_id(
            doc_id=uuid.UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff"),
            effective_uid="maincontract:1.1",
            subchunk_index=0,
        ) != base_id
        assert build_subclause_chunk_id(
            doc_id=TEST_DOC_ID,
            effective_uid="appendix_1:1.1",
            subchunk_index=0,
        ) != base_id


# ── TestBuildSizedChunksFromLeaf ─────────────────────────────────────────────

class TestBuildSizedChunksFromLeaf:
    """КОНТРАКТ: build_sized_chunks_from_leaf."""

    @staticmethod
    def leaf(effective_uid: str, text: str, **meta: object) -> dict:
        scope, raw_uid = split_effective_uid(effective_uid)
        metadata: dict = {
            "effective_uid": effective_uid,
            "scope": scope,
            "raw_uid": raw_uid,
            "level": 2,
            "path_titles": ["Section", "Clause"],
            "start_page": 1,
            "end_page": 1,
            "node_kind": "leaf",
        }
        metadata.update(meta)
        return {"id": effective_uid, "text": text, "metadata": metadata}

    def test_short_clause_produces_single_subclause(self) -> None:
        result = build_sized_chunks_from_leaf(
            doc_id=TEST_DOC_ID,
            leaf_chunks=[self.leaf("maincontract:1.1", "Short text.")],
            target_tokens=500,
            max_tokens=1000,
            overlap_ratio=0.1,
            total_pages=10,
        )
        assert len(result) == 1
        assert result[0]["metadata"]["chunk_kind"] == "subclause"
        assert result[0]["metadata"]["subchunk_index"] == 0
        assert result[0]["metadata"]["subchunk_count"] == 1

    def test_preserves_effective_uid(self) -> None:
        result = build_sized_chunks_from_leaf(
            doc_id=TEST_DOC_ID,
            leaf_chunks=[self.leaf("maincontract:2.3", "Text")],
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            total_pages=None,
        )
        assert result[0]["metadata"]["effective_uid"] == "maincontract:2.3"

    def test_preserves_scope(self) -> None:
        result = build_sized_chunks_from_leaf(
            doc_id=TEST_DOC_ID,
            leaf_chunks=[self.leaf("appendix_1:A.1", "Text")],
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            total_pages=None,
        )
        assert result[0]["metadata"]["scope"] == "appendix_1"

    def test_skips_chunk_without_effective_uid(self) -> None:
        broken = {"id": "x", "text": "Some text", "metadata": {"scope": "maincontract"}}
        result = build_sized_chunks_from_leaf(
            doc_id=TEST_DOC_ID,
            leaf_chunks=[broken],
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            total_pages=None,
        )
        assert result == []

    def test_skips_empty_text(self) -> None:
        result = build_sized_chunks_from_leaf(
            doc_id=TEST_DOC_ID,
            leaf_chunks=[
                self.leaf("maincontract:1.1", ""),
                self.leaf("maincontract:1.2", "   "),
            ],
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            total_pages=None,
        )
        assert result == []


# ── TestCalcPositionRatio ─────────────────────────────────────────────────────

class TestCalcPositionRatio:
    """КОНТРАКТ: calc_position_ratio."""

    def test_returns_ratio_between_0_and_1(self) -> None:
        ratio = calc_position_ratio(start_page=5, end_page=5, total_pages=10)
        assert 0.0 <= ratio <= 1.0
        assert ratio == pytest.approx(0.5)

    def test_first_page_near_zero(self) -> None:
        ratio = calc_position_ratio(start_page=1, end_page=1, total_pages=10)
        assert ratio == pytest.approx(0.1)

    def test_last_page_is_one(self) -> None:
        ratio = calc_position_ratio(start_page=10, end_page=10, total_pages=10)
        assert ratio == pytest.approx(1.0)

    def test_clamps_above_max(self) -> None:
        assert calc_position_ratio(start_page=20, end_page=20, total_pages=10) == 1.0

    def test_clamps_below_min(self) -> None:
        assert calc_position_ratio(start_page=-5, end_page=-5, total_pages=10) == 0.0

    def test_returns_none_for_missing_data(self) -> None:
        assert calc_position_ratio(start_page=1, end_page=1, total_pages=None) is None
        assert calc_position_ratio(start_page=1, end_page=1, total_pages=0) is None
        assert calc_position_ratio(start_page=None, end_page=None, total_pages=10) is None


# ── TestEnsureClauseMetadata ──────────────────────────────────────────────────

class TestEnsureClauseMetadata:
    """КОНТРАКТ: ensure_clause_metadata нормализует metadata clause chunks."""

    @staticmethod
    def clause_chunk(effective_uid: str, text: str, **meta: object) -> dict:
        scope, raw_uid = split_effective_uid(effective_uid)
        metadata: dict = {
            "effective_uid": effective_uid,
            "scope": scope,
            "raw_uid": raw_uid,
            "path_titles": ["Section", "Clause"],
            "node_kind": "leaf",
        }
        metadata.update(meta)
        return {"id": effective_uid, "text": text, "metadata": metadata}

    def test_normalizes_doc_id(self) -> None:
        chunks = [self.clause_chunk("maincontract:1.1", "Text")]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks)
        assert result[0]["metadata"]["doc_id"] == str(TEST_DOC_ID)

        chunks_with_old = [self.clause_chunk("maincontract:1.1", "Text", doc_id="old-wrong-id")]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks_with_old)
        assert result[0]["metadata"]["doc_id"] == str(TEST_DOC_ID)

    def test_forces_chunk_kind_to_clause(self) -> None:
        chunks = [self.clause_chunk("maincontract:1.1", "Text", chunk_kind="section")]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks)
        assert result[0]["metadata"]["chunk_kind"] == "clause"

    def test_skips_chunks_without_effective_uid(self) -> None:
        chunks = [{"id": "x", "text": "Some text", "metadata": {}}]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks)
        assert result == []

    def test_skips_empty_text(self) -> None:
        chunks = [
            self.clause_chunk("maincontract:1.1", ""),
            self.clause_chunk("maincontract:1.2", "   "),
        ]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks)
        assert result == []

    def test_preserves_node_kind(self) -> None:
        chunks = [self.clause_chunk("maincontract:1.1", "Text", node_kind="section")]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks)
        assert result[0]["metadata"]["node_kind"] == "section"


# ── TestCrossReferenceValidation ──────────────────────────────────────────────

class TestCrossReferenceValidation:
    """ИНВАРИАНТЫ CrossReference."""

    def test_valid_same_scope_reference(self) -> None:
        ref = CrossReference(
            source_effective_uid="maincontract:1.1",
            target_effective_uid="maincontract:1.2",
            reference_text="see clause 1.2",
        )
        assert ref.source_scope == "maincontract"
        assert ref.target_scope == "maincontract"

    def test_valid_cross_scope_reference(self) -> None:
        ref = CrossReference(
            source_effective_uid="maincontract:1.1",
            target_effective_uid="appendix_1:A.2",
            reference_text="see appendix A.2",
        )
        assert ref.source_scope == "maincontract"
        assert ref.target_scope == "appendix_1"

    def test_rejects_empty_fields(self) -> None:
        with pytest.raises(ValueError, match="source_effective_uid must be non-empty"):
            CrossReference(
                source_effective_uid="",
                target_effective_uid="maincontract:1.2",
                reference_text="ref",
            )
        with pytest.raises(ValueError, match="target_effective_uid must be non-empty"):
            CrossReference(
                source_effective_uid="maincontract:1.1",
                target_effective_uid="",
                reference_text="ref",
            )
        with pytest.raises(ValueError, match="reference_text must be non-empty"):
            CrossReference(
                source_effective_uid="maincontract:1.1",
                target_effective_uid="maincontract:1.2",
                reference_text="",
            )

    def test_scope_consistency(self) -> None:
        with pytest.raises(ValueError, match="source_scope mismatch"):
            CrossReference(
                source_effective_uid="maincontract:1.1",
                target_effective_uid="maincontract:1.2",
                source_scope="appendix_1",
                reference_text="ref",
            )
        with pytest.raises(ValueError, match="target_scope mismatch"):
            CrossReference(
                source_effective_uid="maincontract:1.1",
                target_effective_uid="appendix_1:A.2",
                target_scope="maincontract",
                reference_text="ref",
            )


# ── TestCrossSegmentRefValidation ─────────────────────────────────────────────

class TestCrossSegmentRefValidation:
    """ИНВАРИАНТЫ CrossSegmentRef."""

    def test_unresolved_reference(self) -> None:
        ref = CrossSegmentRef(
            source_effective_uid="maincontract:1.1",
            target_raw_uid="A.1",
            target_scope_hint="appendix_1",
            reference_text="see appendix A.1",
        )
        assert ref.resolution_method == "unresolved"

    def test_resolved_reference(self) -> None:
        ref = CrossSegmentRef(
            source_effective_uid="maincontract:1.1",
            target_raw_uid="A.1",
            target_scope_hint="appendix_1",
            target_effective_uid="appendix_1:A.1",
            resolution_confidence=0.9,
            resolution_method="resolved",
            reference_text="see appendix A.1",
        )
        assert ref.target_effective_uid == "appendix_1:A.1"

    def test_confidence_range_validation(self) -> None:
        with pytest.raises(ValueError, match=r"resolution_confidence"):
            CrossSegmentRef(
                source_effective_uid="maincontract:1.1",
                target_raw_uid="A.1",
                target_scope_hint="appendix_1",
                resolution_confidence=1.5,
                reference_text="ref",
            )
        with pytest.raises(ValueError, match=r"resolution_confidence"):
            CrossSegmentRef(
                source_effective_uid="maincontract:1.1",
                target_raw_uid="A.1",
                target_scope_hint="appendix_1",
                resolution_confidence=-0.1,
                reference_text="ref",
            )

    def test_scope_hint_consistency(self) -> None:
        with pytest.raises(ValueError, match="target_scope_hint mismatch"):
            CrossSegmentRef(
                source_effective_uid="maincontract:1.1",
                target_raw_uid="A.1",
                target_scope_hint="maincontract",
                target_effective_uid="appendix_1:A.1",
                reference_text="ref",
            )

