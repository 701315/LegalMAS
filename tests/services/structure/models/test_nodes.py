"""
Golden tests для Phase 1 models.


Покрывают:
  - MutableHierarchyNode creation + validation
  - structural_hash computation + OCR-stability
  - freeze() happy path + без hash → ValueError
  - FrozenHierarchyNode immutability + children=tuple
  - SemanticNodeMetadata полная изоляция от structural nodes
  - CrossReference / CrossSegmentRef validation
"""


from __future__ import annotations


import pytest


from services.structure.models import (
    CrossReference,
    CrossSegmentRef,
    FrozenHierarchyNode,
    MutableHierarchyNode,
    RecoveryInfo,
    SemanticNodeMetadata,
    STRUCTURAL_HASH_VERSION,
    NODE_KIND_LEAF,
    NODE_KIND_SECTION,
    compute_structural_hash,
    freeze,
    structural_hash_version,
)



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def make_leaf(
    uid: str = "main_contract:1.1",
    title: str = "Title",
    level: int = 2,
) -> MutableHierarchyNode:
    return MutableHierarchyNode(effective_uid=uid, title=title, level=level)



def make_section_with_leaf() -> MutableHierarchyNode:
    leaf = make_leaf("main_contract:1.1", level=2)
    leaf.compute_and_set_structural_hash(normalized_path="1.1", sibling_index=0)


    section = MutableHierarchyNode(
        effective_uid="main_contract:1",
        title="Section 1",
        level=1,
        node_kind=NODE_KIND_SECTION,
        children=[leaf],
        start_page=1,
        end_page=5,
    )
    section.compute_and_set_structural_hash(normalized_path="1", sibling_index=0)
    return section



# ---------------------------------------------------------------------------
# MutableHierarchyNode — creation
# ---------------------------------------------------------------------------



class TestMutableHierarchyNodeCreation:


    def test_basic_leaf(self):
        node = make_leaf()
        assert node.effective_uid == "main_contract:1.1"
        assert node.scope == "main_contract"
        assert node.raw_uid == "1.1"
        assert node.level == 2
        assert node.node_kind == NODE_KIND_LEAF
        assert node.children == []
        assert node.structural_hash is None


    def test_structural_hash_not_computed_by_default(self):
        node = make_leaf()
        assert node.structural_hash is None


    def test_no_semantic_fields_on_node(self):
        node = make_leaf()
        assert not hasattr(node, "semantic_node_type")
        assert not hasattr(node, "parse_confidence")
        assert not hasattr(node, "citability_hint")
        assert not hasattr(node, "recovered_via_best_effort")
        assert not hasattr(node, "fallback_reason")


    def test_scope_inferred_from_effective_uid(self):
        node = MutableHierarchyNode(
            effective_uid="appendix_1:2.3",
            title="T",
            level=2,
        )
        assert node.scope == "appendix_1"
        assert node.raw_uid == "2.3"


    def test_explicit_scope_must_match_uid(self):
        with pytest.raises(ValueError, match="scope mismatch"):
            MutableHierarchyNode(
                effective_uid="main_contract:1",
                title="T",
                level=1,
                scope="appendix_1",
            )


    def test_child_level_must_be_greater(self):
        child = MutableHierarchyNode(
            effective_uid="main_contract:1.1",
            title="T",
            level=1,
        )
        with pytest.raises(ValueError, match="Child level must be > parent level"):
            MutableHierarchyNode(
                effective_uid="main_contract:1",
                title="T",
                level=1,
                node_kind=NODE_KIND_SECTION,
                children=[child],
            )


    def test_end_page_must_be_gte_start_page(self):
        with pytest.raises(ValueError, match="end_page must be >= start_page"):
            MutableHierarchyNode(
                effective_uid="main_contract:1",
                title="T",
                level=1,
                start_page=5,
                end_page=3,
            )


    def test_own_element_ids_subset_of_subtree(self):
        with pytest.raises(ValueError, match="subset of subtree_element_ids"):
            MutableHierarchyNode(
                effective_uid="main_contract:1",
                title="T",
                level=1,
                own_element_ids=["e1", "e2"],
                subtree_element_ids=["e1"],
            )



# ---------------------------------------------------------------------------
# structural_hash
# ---------------------------------------------------------------------------



class TestStructuralHash:


    def test_compute_and_set(self):
        node = make_leaf()
        h = node.compute_and_set_structural_hash(normalized_path="1.1", sibling_index=0)
        assert node.structural_hash == h
        assert h.startswith(f"v{STRUCTURAL_HASH_VERSION}:")


    def test_deterministic(self):
        n1 = make_leaf()
        n2 = make_leaf()
        h1 = n1.compute_and_set_structural_hash(normalized_path="1.1", sibling_index=0)
        h2 = n2.compute_and_set_structural_hash(normalized_path="1.1", sibling_index=0)
        assert h1 == h2


    def test_ocr_stability(self):
        """Hash не зависит от title — OCR-variance safe."""
        n1 = MutableHierarchyNode(effective_uid="main_contract:1.1", title="Definitions", level=2)
        n2 = MutableHierarchyNode(effective_uid="main_contract:1.1", title="DEFINITIONS (v2 amended)", level=2)
        h1 = n1.compute_and_set_structural_hash(normalized_path="1.1", sibling_index=0)
        h2 = n2.compute_and_set_structural_hash(normalized_path="1.1", sibling_index=0)
        assert h1 == h2


    def test_differs_by_sibling_index(self):
        n1 = make_leaf("main_contract:1.1")
        n2 = make_leaf("main_contract:1.2")
        h1 = n1.compute_and_set_structural_hash(normalized_path="1.1", sibling_index=0)
        h2 = n2.compute_and_set_structural_hash(normalized_path="1.2", sibling_index=1)
        assert h1 != h2


    def test_differs_by_scope(self):
        n1 = MutableHierarchyNode(effective_uid="main_contract:1", title="T", level=1)
        n2 = MutableHierarchyNode(effective_uid="appendix_1:1", title="T", level=1)
        h1 = n1.compute_and_set_structural_hash(normalized_path="1", sibling_index=0)
        h2 = n2.compute_and_set_structural_hash(normalized_path="1", sibling_index=0)
        assert h1 != h2


    def test_version_extraction(self):
        h = compute_structural_hash(
            normalized_path="1.2.3",
            stable_level=3,
            sibling_index=2,
            scope_id="main_contract",
        )
        assert structural_hash_version(h) == STRUCTURAL_HASH_VERSION


    def test_empty_path_raises(self):
        with pytest.raises(ValueError, match="normalized_path must be non-empty"):
            compute_structural_hash(
                normalized_path="",
                stable_level=1,
                sibling_index=0,
                scope_id="main_contract",
            )


    def test_zero_level_raises(self):
        with pytest.raises(ValueError, match="stable_level must be >= 1"):
            compute_structural_hash(
                normalized_path="1",
                stable_level=0,
                sibling_index=0,
                scope_id="main_contract",
            )



# ---------------------------------------------------------------------------
# freeze()
# ---------------------------------------------------------------------------



class TestFreeze:


    def test_happy_path(self):
        section = make_section_with_leaf()
        frozen = freeze(section)
        assert isinstance(frozen, FrozenHierarchyNode)
        assert frozen.effective_uid == "main_contract:1"
        assert len(frozen.children) == 1
        assert isinstance(frozen.children[0], FrozenHierarchyNode)


    def test_without_hash_raises(self):
        node = make_leaf()
        with pytest.raises(ValueError, match="structural_hash not computed"):
            freeze(node)


    def test_frozen_is_immutable(self):
        section = make_section_with_leaf()
        frozen = freeze(section)
        with pytest.raises((AttributeError, TypeError)):
            frozen.title = "changed"  # type: ignore[misc]


    def test_children_are_tuple(self):
        section = make_section_with_leaf()
        frozen = freeze(section)
        assert isinstance(frozen.children, tuple)
        assert isinstance(frozen.own_element_ids, tuple)
        assert isinstance(frozen.subtree_element_ids, tuple)


    def test_preserves_structural_hash(self):
        section = make_section_with_leaf()
        expected_hash = section.structural_hash
        frozen = freeze(section)
        assert frozen.structural_hash == expected_hash


    def test_no_semantic_fields_on_frozen(self):
        section = make_section_with_leaf()
        frozen = freeze(section)
        assert not hasattr(frozen, "semantic_node_type")
        assert not hasattr(frozen, "parse_confidence")
        assert not hasattr(frozen, "citability_hint")


    def test_to_dict(self):
        section = make_section_with_leaf()
        d = freeze(section).to_dict()
        assert d["effective_uid"] == "main_contract:1"
        assert "structural_hash" in d
        assert isinstance(d["children"], list)
        assert len(d["children"]) == 1



# ---------------------------------------------------------------------------
# SemanticNodeMetadata
# ---------------------------------------------------------------------------



class TestSemanticNodeMetadata:


    def test_basic_creation(self):
        meta = SemanticNodeMetadata(
            effective_uid="main_contract:1.1",
            semantic_node_type="definition_item",
            parse_confidence=0.85,
            citability_hint="high",
        )
        assert meta.semantic_node_type == "definition_item"
        assert meta.parse_confidence == 0.85
        assert meta.citability_hint == "high"


    def test_all_fields_optional(self):
        meta = SemanticNodeMetadata(effective_uid="main_contract:1.1")
        assert meta.semantic_node_type is None
        assert meta.parse_confidence is None
        assert meta.citability_hint is None
        assert meta.recovery_info is None


    def test_invalid_semantic_type_raises(self):
        with pytest.raises(ValueError, match="not valid"):
            SemanticNodeMetadata(
                effective_uid="main_contract:1.1",
                semantic_node_type="nonexistent_type",
            )


    def test_invalid_citability_hint_raises(self):
        with pytest.raises(ValueError, match="not valid"):
            SemanticNodeMetadata(
                effective_uid="main_contract:1.1",
                citability_hint="ultra_high",
            )


    def test_parse_confidence_out_of_range(self):
        with pytest.raises(ValueError, match="must be in"):
            SemanticNodeMetadata(
                effective_uid="main_contract:1.1",
                parse_confidence=1.5,
            )


    def test_with_recovery_info(self):
        info = RecoveryInfo(
            recovered=True,
            strategy="numbering_inference",
            confidence=0.9,
        )
        meta = SemanticNodeMetadata(
            effective_uid="main_contract:1.1",
            recovery_info=info,
        )
        assert meta.recovery_info.recovered is True
        assert meta.recovery_info.strategy == "numbering_inference"


    def test_to_dict(self):
        meta = SemanticNodeMetadata(
            effective_uid="main_contract:1.1",
            semantic_node_type="body_text",
            parse_confidence=0.7,
        )
        d = meta.to_dict()
        assert d["semantic_node_type"] == "body_text"
        assert d["parse_confidence"] == 0.7
        assert d["recovery_info"] is None



# ---------------------------------------------------------------------------
# CrossReference
# ---------------------------------------------------------------------------



class TestCrossReference:


    def test_basic_creation(self):
        ref = CrossReference(
            source_effective_uid="main_contract:1.1",
            target_effective_uid="main_contract:4.2",
            reference_text="see Section 4.2",
        )
        assert ref.source_scope == "main_contract"
        assert ref.target_scope == "main_contract"
        assert ref.source_raw_uid == "1.1"
        assert ref.target_raw_uid == "4.2"


    def test_empty_reference_text_raises(self):
        with pytest.raises(ValueError, match="reference_text must be non-empty"):
            CrossReference(
                source_effective_uid="main_contract:1.1",
                target_effective_uid="main_contract:4.2",
                reference_text="",
            )


    def test_to_dict(self):
        ref = CrossReference(
            source_effective_uid="main_contract:1.1",
            target_effective_uid="main_contract:4.2",
            reference_text="see Section 4.2",
        )
        d = ref.to_dict()
        assert d["source_effective_uid"] == "main_contract:1.1"
        assert d["reference_text"] == "see Section 4.2"



# ---------------------------------------------------------------------------
# CrossSegmentRef
# ---------------------------------------------------------------------------



class TestCrossSegmentRef:


    def test_unresolved(self):
        ref = CrossSegmentRef(
            source_effective_uid="main_contract:7.1",
            target_raw_uid="annex_a",
            target_scope_hint="appendix_1",
        )
        assert ref.target_effective_uid is None
        assert ref.resolution_method == "unresolved"


    def test_resolved(self):
        ref = CrossSegmentRef(
            source_effective_uid="main_contract:7.1",
            target_effective_uid="appendix_1:annex_a",
            resolution_confidence=0.95,
            resolution_method="lexical_match",
        )
        assert ref.target_effective_uid == "appendix_1:annex_a"
        assert ref.resolution_confidence == 0.95
        assert ref.resolution_method == "lexical_match"
        # target_scope_hint не инферируется автоматически — передаётся только явно
        assert ref.target_scope_hint is None


    def test_resolved_with_explicit_scope_hint(self):
        ref = CrossSegmentRef(
            source_effective_uid="main_contract:7.1",
            target_effective_uid="appendix_1:annex_a",
            target_scope_hint="appendix_1",
            resolution_confidence=0.95,
            resolution_method="lexical_match",
        )
        assert ref.target_scope_hint == "appendix_1"
        assert ref.target_effective_uid == "appendix_1:annex_a"


    def test_scope_hint_mismatch_with_target_uid_raises(self):
        with pytest.raises(ValueError, match="target_scope_hint mismatch"):
            CrossSegmentRef(
                source_effective_uid="main_contract:7.1",
                target_effective_uid="appendix_1:annex_a",
                target_scope_hint="main_contract",  # конфликт с target_effective_uid
            )


    def test_confidence_out_of_range(self):
        with pytest.raises(ValueError, match="must be in"):
            CrossSegmentRef(
                source_effective_uid="main_contract:7.1",
                resolution_confidence=1.5,
            )

