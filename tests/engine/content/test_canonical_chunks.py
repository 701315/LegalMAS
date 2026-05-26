"""
tests/engine/content/test_canonical_chunks.py

Unit tests for canonical chunk infrastructure (Sprint 3).

Эти тесты проверяют КОНТРАКТ и ИНВАРИАНТЫ системы,
а не конкретную реализацию [web:959][web:960].
"""
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
    ClauseNode,
    ClauseTree,
    CrossReference,
    CrossSegmentRef,
    generate_scope_name,
    make_effective_uid,
    split_effective_uid,
)


TEST_DOC_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


class TestEffectiveUidFormat:
    """
    КОНТРАКТ: effective_uid = "scope:raw_uid"
    - scope: валидный идентификатор области (латиница, цифры, подчёркивания)
    - raw_uid: непустая строка, идентификатор клаузы внутри области
    - разделитель: ровно один символ ':'
    
    ИНВАРИАНТЫ:
    - make_effective_uid + split_effective_uid должны быть обратимы (roundtrip)
    - пустой raw_uid недопустим
    - невалидный scope недопустим
    """
    
    def test_roundtrip_property(self):
        """ИНВАРИАНТ: make -> split -> make даёт тот же результат [web:959]"""
        test_cases = [
            ("maincontract", "1.1"),
            ("appendix_1", "A.2.1"),
            ("contract_2", "3.14.15.92"),
        ]
        
        for scope, raw_uid in test_cases:
            uid = make_effective_uid(scope, raw_uid)
            parsed_scope, parsed_raw = split_effective_uid(uid)
            
            # Roundtrip property
            assert parsed_scope == scope
            assert parsed_raw == raw_uid
            assert make_effective_uid(parsed_scope, parsed_raw) == uid
    
    def test_whitespace_normalization(self):
        """КОНТРАКТ: пробелы в начале/конце должны удаляться [web:959]"""
        uid = make_effective_uid(" maincontract ", " 1.1 ")
        assert uid == "maincontract:1.1"
        assert " " not in uid
    
    def test_rejects_empty_raw_uid(self):
        """ИНВАРИАНТ: raw_uid не может быть пустым [web:959]"""
        with pytest.raises(ValueError, match=r"raw_uid must be non-empty"):
            make_effective_uid("maincontract", "")
        
        with pytest.raises(ValueError, match=r"raw_uid must be non-empty"):
            make_effective_uid("maincontract", "   ")
    
    def test_rejects_invalid_scope_format(self):
        """ИНВАРИАНТ: scope должен быть валидным идентификатором [web:959]"""
        invalid_scopes = [
            "appendix-1",      # дефис недопустим
            "appendix 1",      # пробел недопустим
            "appendix.1",      # точка недопустима
        ]
        
        for invalid_scope in invalid_scopes:
            with pytest.raises(ValueError, match="Invalid scope"):
                make_effective_uid(invalid_scope, "A.1")
    
    def test_split_rejects_invalid_format(self):
        """КОНТРАКТ: split требует формат 'scope:raw_uid' [web:959]"""
        with pytest.raises(ValueError, match=r"Expected canonical.*format"):
            split_effective_uid("maincontract1.2.3")  # нет разделителя
        
        with pytest.raises(ValueError, match="effective_uid must be non-empty"):
            split_effective_uid("")
        
        with pytest.raises(ValueError, match="must contain non-empty raw uid"):
            split_effective_uid("maincontract:")  # пустой raw_uid
    
    def test_preserves_complex_raw_uid(self):
        """КОНТРАКТ: raw_uid может содержать точки и сложную структуру [web:959]"""
        uid = make_effective_uid("maincontract", "1.2.3.4.5")
        scope, raw_uid = split_effective_uid(uid)
        assert raw_uid == "1.2.3.4.5"
    
    def test_handles_colon_in_raw_uid(self):
        """КРАЕВОЙ СЛУЧАЙ: если raw_uid сам содержит ':', split берёт первый ':' [web:959]"""
        uid = "maincontract:1.2:extra_info"
        scope, raw_uid = split_effective_uid(uid)
        assert scope == "maincontract"
        assert raw_uid == "1.2:extra_info"  # всё после первого ':'


class TestScopeNaming:
    """
    КОНТРАКТ: generate_scope_name формирует canonical имя области
    - contract, order=0 -> "maincontract" (DEFAULT_SCOPE)
    - contract, order=N -> "contract_{N+1}"
    - appendix, order=N -> "appendix_{N+1}"
    
    ИНВАРИАНТ: имя должно быть валидным для make_effective_uid
    """
    
    def test_first_contract_is_default_scope(self):
        """КОНТРАКТ: первый contract всегда maincontract [web:959]"""
        assert generate_scope_name(SEGMENT_TYPE_CONTRACT, 0) == DEFAULT_SCOPE
    
    def test_appendix_numbering_starts_from_1(self):
        """КОНТРАКТ: appendix нумеруются с 1, даже если order=0 [web:959]"""
        assert generate_scope_name(SEGMENT_TYPE_APPENDIX, 0) == "appendix_1"
        assert generate_scope_name(SEGMENT_TYPE_APPENDIX, 1) == "appendix_2"
        assert generate_scope_name(SEGMENT_TYPE_APPENDIX, 2) == "appendix_3"
    
    def test_contract_numbering_after_main(self):
        """КОНТРАКТ: последующие contracts нумеруются с 2 [web:959]"""
        assert generate_scope_name(SEGMENT_TYPE_CONTRACT, 1) == "contract_2"
        assert generate_scope_name(SEGMENT_TYPE_CONTRACT, 5) == "contract_6"
    
    def test_generated_scope_is_valid_for_effective_uid(self):
        """ИНВАРИАНТ: сгенерированный scope должен работать в make_effective_uid [web:959]"""
        for segment_type in [SEGMENT_TYPE_CONTRACT, SEGMENT_TYPE_APPENDIX]:
            for order in range(5):
                scope = generate_scope_name(segment_type, order)
                
                # Не должно кидать ValueError
                uid = make_effective_uid(scope, "1.1")
                assert ":" in uid
                assert uid.startswith(scope)


class TestClauseNodeInvariants:
    """
    ИНВАРИАНТЫ ClauseNode (как в реальном документе):
    1. effective_uid, scope, raw_uid должны быть консистентны
    2. child.scope == parent.scope (все узлы одного дерева в одной области)
    3. child.level > parent.level (строгая иерархия)
    4. leaf nodes не имеют детей
    5. section nodes обязаны иметь детей
    6. end_page >= start_page
    """
    
    @staticmethod
    def make_leaf(effective_uid: str, **kwargs) -> ClauseNode:
        """Фабрика для создания валидного leaf node [web:960]"""
        defaults = dict(
            title="Leaf",
            level=2,
            node_kind=NODE_KIND_LEAF,
            own_element_ids=["e1"],
            subtree_element_ids=["e1"],
            own_text="Some text",
            subtree_text="Some text",
            start_page=1,
            end_page=1,
        )
        defaults.update(kwargs)
        return ClauseNode(effective_uid=effective_uid, **defaults)
    
    def test_scope_consistency_invariant(self):
        """ИНВАРИАНТ: scope из effective_uid == явно заданный scope [web:959]"""
        node = self.make_leaf("maincontract:1.1", scope="maincontract")
        assert node.scope == "maincontract"
        assert node.raw_uid == "1.1"
        
        # Нарушение инварианта
        with pytest.raises(ValueError, match="scope mismatch"):
            self.make_leaf("maincontract:1.1", scope="appendix_1")
    
    def test_child_scope_must_match_parent(self):
        """ИНВАРИАНТ: все узлы в одном дереве имеют один scope [web:959]"""
        child_main = self.make_leaf("maincontract:1.1.1", level=3)
        child_appendix = self.make_leaf("appendix_1:A.1", level=3)
        
        # Попытка смешать разные scope
        with pytest.raises(ValueError, match="child scope mismatch"):
            ClauseNode(
                effective_uid="maincontract:1.1",
                title="Parent",
                level=2,
                node_kind=NODE_KIND_SECTION,
                own_element_ids=[],
                subtree_element_ids=["e1"],
                start_page=1,
                end_page=2,
                children=[child_main, child_appendix],  # разные scope!
            )
    
    def test_strict_level_hierarchy(self):
        """ИНВАРИАНТ: child.level > parent.level (строго) [web:959]"""
        # Нарушение: child того же уровня
        child_same_level = self.make_leaf("maincontract:1.1.1", level=2)
        
        with pytest.raises(ValueError, match="child level must be greater"):
            ClauseNode(
                effective_uid="maincontract:1.1",
                title="Parent",
                level=2,
                node_kind=NODE_KIND_SECTION,
                own_element_ids=[],
                subtree_element_ids=["e1"],
                start_page=1,
                end_page=2,
                children=[child_same_level],
            )
    
    def test_leaf_cannot_have_children(self):
        """ИНВАРИАНТ: leaf node — конечный узел [web:959]"""
        child = self.make_leaf("maincontract:1.1.1", level=3)
        
        with pytest.raises(ValueError, match="'leaf' must not have children"):
            self.make_leaf("maincontract:1.1", level=2, children=[child])
    
    def test_section_must_have_children(self):
        """ИНВАРИАНТ: section node обязан иметь детей [web:959]"""
        with pytest.raises(ValueError, match="'section' must have children"):
            ClauseNode(
                effective_uid="maincontract:1",
                title="Empty Section",
                level=1,
                node_kind=NODE_KIND_SECTION,
                own_element_ids=[],
                subtree_element_ids=[],
                start_page=1,
                end_page=1,
                children=[],  # пустой список
            )
    
    def test_page_range_invariant(self):
        """ИНВАРИАНТ: end_page >= start_page [web:959]"""
        with pytest.raises(ValueError, match=r"end_page must be >= .*start_page"):
            ClauseNode(
                effective_uid="maincontract:1.1",
                title="Invalid Pages",
                level=2,
                node_kind=NODE_KIND_LEAF,
                own_element_ids=["e1"],
                subtree_element_ids=["e1"],
                start_page=5,
                end_page=3,  # end < start!
            )


class TestClauseTreeDuplicateDetection:
    """
    ИНВАРИАНТ: ClauseTree не может содержать дубликаты effective_uid
    
    Это критично для canonical identity — каждая клауза в документе
    должна иметь уникальный идентификатор [web:959].
    """
    
    @staticmethod
    def simple_leaf(effective_uid: str, title: str) -> ClauseNode:
        """Фабрика для минимального leaf node [web:960]"""
        return ClauseNode(
            effective_uid=effective_uid,
            title=title,
            level=2,
            node_kind=NODE_KIND_LEAF,
            own_element_ids=[f"{title}-e"],
            subtree_element_ids=[f"{title}-e"],
            own_text=title,
            subtree_text=title,
            start_page=1,
            end_page=1,
        )
    
    def test_allows_unique_uids(self):
        """КОНТРАКТ: уникальные uid допустимы [web:959]"""
        n1 = self.simple_leaf("maincontract:1.1", "Clause 1.1")
        n2 = self.simple_leaf("maincontract:1.2", "Clause 1.2")
        
        tree = ClauseTree(
            document_id="doc-1",
            root=[n1, n2],
            references_index=[],
            structure_confidence="MEDIUM",
        )
        
        assert len(tree.nodes_index) == 2
        assert "maincontract:1.1" in tree.nodes_index
        assert "maincontract:1.2" in tree.nodes_index
    
    def test_rejects_duplicate_at_root(self):
        """ИНВАРИАНТ: дубликаты на верхнем уровне недопустимы [web:959]"""
        n1 = self.simple_leaf("maincontract:1.1", "First")
        n2 = self.simple_leaf("maincontract:1.1", "Second")  # тот же uid!
        
        with pytest.raises(ValueError, match="duplicate effective_uid"):
            ClauseTree(
                document_id="doc-1",
                root=[n1, n2],
                references_index=[],
                structure_confidence="MEDIUM",
            )
    
    def test_rejects_duplicate_in_hierarchy(self):
        """ИНВАРИАНТ: дубликаты в глубокой иерархии недопустимы [web:959]"""
        # Правильная иерархия уровней: 1 -> 2 -> 3
        grandchild = self.simple_leaf("maincontract:1.1.1", "Grandchild")
        grandchild.level = 3
        
        child = ClauseNode(
            effective_uid="maincontract:1.1",
            title="Child",
            level=2,
            node_kind=NODE_KIND_SECTION,
            own_element_ids=[],
            subtree_element_ids=["Grandchild-e"],
            start_page=1,
            end_page=2,
            children=[grandchild],
        )
        
        # Дубликат grandchild на том же уровне
        duplicate = self.simple_leaf("maincontract:1.1.1", "Duplicate")
        duplicate.level = 3
        
        parent = ClauseNode(
            effective_uid="maincontract:1",
            title="Parent",
            level=1,
            node_kind=NODE_KIND_SECTION,
            own_element_ids=[],
            subtree_element_ids=["Grandchild-e", "Duplicate-e"],
            start_page=1,
            end_page=3,
            children=[child, duplicate],
        )
        
        with pytest.raises(ValueError, match="duplicate effective_uid"):
            ClauseTree(
                document_id="doc-1",
                root=[parent],
                references_index=[],
                structure_confidence="MEDIUM",
            )


class TestCanonicalChunkIdGeneration:
    """
    КОНТРАКТ: build_subclause_chunk_id должен создавать:
    - уникальный ID для каждой комбинации (doc_id, effective_uid, subchunk_index)
    - детерминированный (одинаковые входы -> одинаковый ID)
    - разный для разных входов
    """
    
    def test_deterministic_property(self):
        """ИНВАРИАНТ: одинаковые входы -> одинаковый результат [web:959]"""
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
    
    def test_different_inputs_give_different_ids(self):
        """ИНВАРИАНТ: разные входы -> разные ID [web:959]"""
        base_id = build_subclause_chunk_id(
            doc_id=TEST_DOC_ID,
            effective_uid="maincontract:1.1",
            subchunk_index=0,
        )
        
        # Разный subchunk_index
        id_diff_index = build_subclause_chunk_id(
            doc_id=TEST_DOC_ID,
            effective_uid="maincontract:1.1",
            subchunk_index=1,
        )
        assert id_diff_index != base_id
        
        # Разный effective_uid
        id_diff_uid = build_subclause_chunk_id(
            doc_id=TEST_DOC_ID,
            effective_uid="maincontract:1.2",
            subchunk_index=0,
        )
        assert id_diff_uid != base_id
        
        # Разный doc_id
        id_diff_doc = build_subclause_chunk_id(
            doc_id=uuid.UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff"),
            effective_uid="maincontract:1.1",
            subchunk_index=0,
        )
        assert id_diff_doc != base_id
        
        # Разный scope в effective_uid
        id_diff_scope = build_subclause_chunk_id(
            doc_id=TEST_DOC_ID,
            effective_uid="appendix_1:1.1",
            subchunk_index=0,
        )
        assert id_diff_scope != base_id


class TestBuildSizedChunksFromLeaf:
    """
    КОНТРАКТ: build_sized_chunks_from_leaf должен:
    1. Разбить длинные clause на subclause по token limits
    2. Оставить короткие clause как single subclause
    3. Пропустить chunks без effective_uid или с пустым текстом
    4. Сохранить все metadata поля из исходного chunk
    5. Установить chunk_kind="subclause" для всех выходных chunks
    """
    
    @staticmethod
    def leaf(effective_uid: str, text: str, **meta):
        """Фабрика для clause chunk [web:960]"""
        scope, raw_uid = split_effective_uid(effective_uid)
        metadata = {
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
    
    def test_short_clause_produces_single_subclause(self):
        """КОНТРАКТ: короткая clause -> одна subclause [web:959]"""
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
    
    def test_preserves_effective_uid(self):
        """ИНВАРИАНТ: effective_uid передаётся из clause в subclause [web:959]"""
        result = build_sized_chunks_from_leaf(
            doc_id=TEST_DOC_ID,
            leaf_chunks=[self.leaf("maincontract:2.3", "Text")],
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            total_pages=None,
        )
        
        assert result[0]["metadata"]["effective_uid"] == "maincontract:2.3"
    
    def test_preserves_scope(self):
        """ИНВАРИАНТ: scope передаётся из clause в subclause [web:959]"""
        result = build_sized_chunks_from_leaf(
            doc_id=TEST_DOC_ID,
            leaf_chunks=[self.leaf("appendix_1:A.1", "Text")],
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            total_pages=None,
        )
        
        assert result[0]["metadata"]["scope"] == "appendix_1"
    
    def test_skips_chunk_without_effective_uid(self):
        """КОНТРАКТ: chunk без effective_uid пропускается [web:959]"""
        broken_chunk = {
            "id": "x",
            "text": "Some text",
            "metadata": {"scope": "maincontract"},  # нет effective_uid!
        }
        
        result = build_sized_chunks_from_leaf(
            doc_id=TEST_DOC_ID,
            leaf_chunks=[broken_chunk],
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            total_pages=None,
        )
        
        assert result == []
    
    def test_skips_empty_text(self):
        """КОНТРАКТ: chunk с пустым текстом пропускается [web:959]"""
        result = build_sized_chunks_from_leaf(
            doc_id=TEST_DOC_ID,
            leaf_chunks=[
                self.leaf("maincontract:1.1", ""),
                self.leaf("maincontract:1.2", "   "),
                self.leaf("maincontract:1.3", "\n\t"),
            ],
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            total_pages=None,
        )
        
        assert result == []


class TestCalcPositionRatio:
    """
    КОНТРАКТ: calc_position_ratio вычисляет относительную позицию clause в документе
    - Возвращает float от 0.0 до 1.0
    - Использует mid-point между start_page и end_page
    - Возвращает None если недостаточно данных
    - Clamps значения в диапазон [0.0, 1.0]
    """
    
    def test_returns_ratio_between_0_and_1(self):
        """ИНВАРИАНТ: результат в диапазоне [0.0, 1.0] [web:959]"""
        ratio = calc_position_ratio(start_page=5, end_page=5, total_pages=10)
        assert 0.0 <= ratio <= 1.0
        assert ratio == pytest.approx(0.5)
    
    def test_first_page_near_zero(self):
        """КОНТРАКТ: первая страница -> низкий ratio [web:959]"""
        ratio = calc_position_ratio(start_page=1, end_page=1, total_pages=10)
        assert ratio == pytest.approx(0.1)
    
    def test_last_page_is_one(self):
        """КОНТРАКТ: последняя страница -> ratio = 1.0 [web:959]"""
        ratio = calc_position_ratio(start_page=10, end_page=10, total_pages=10)
        assert ratio == pytest.approx(1.0)
    
    def test_clamps_above_max(self):
        """ИНВАРИАНТ: значения > 1.0 обрезаются [web:959]"""
        ratio = calc_position_ratio(start_page=20, end_page=20, total_pages=10)
        assert ratio == 1.0
    
    def test_clamps_below_min(self):
        """ИНВАРИАНТ: значения < 0.0 обрезаются [web:959]"""
        ratio = calc_position_ratio(start_page=-5, end_page=-5, total_pages=10)
        assert ratio == 0.0
    
    def test_returns_none_for_missing_data(self):
        """КОНТРАКТ: None при недостаточных данных [web:959]"""
        assert calc_position_ratio(start_page=1, end_page=1, total_pages=None) is None
        assert calc_position_ratio(start_page=1, end_page=1, total_pages=0) is None
        assert calc_position_ratio(start_page=None, end_page=None, total_pages=10) is None


class TestEnsureClauseMetadata:
    """
    КОНТРАКТ: ensure_clause_metadata нормализует metadata clause chunks
    
    ВАЖНО: это НОРМАЛИЗАТОР, а не просто "заполнитель пробелов".
    Он приводит chunks к canonical виду для данного документа [web:960].
    
    Ожидаемое поведение:
    1. Устанавливает doc_id из аргумента (ВСЕГДА, даже если есть старый)
    2. Устанавливает chunk_kind="clause" (ВСЕГДА)
    3. Пропускает chunks без effective_uid или с пустым текстом
    4. Сохраняет остальные поля как есть
    """
    
    @staticmethod
    def clause_chunk(effective_uid: str, text: str, **meta):
        """Фабрика для clause chunk [web:960]"""
        scope, raw_uid = split_effective_uid(effective_uid)
        metadata = {
            "effective_uid": effective_uid,
            "scope": scope,
            "raw_uid": raw_uid,
            "path_titles": ["Section", "Clause"],
            "node_kind": "leaf",
        }
        metadata.update(meta)
        return {"id": effective_uid, "text": text, "metadata": metadata}
    
    def test_normalizes_doc_id(self):
        """КОНТРАКТ: doc_id ВСЕГДА устанавливается из аргумента [web:959][web:960]"""
        # Случай 1: doc_id отсутствует
        chunks = [self.clause_chunk("maincontract:1.1", "Text")]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks)
        assert result[0]["metadata"]["doc_id"] == str(TEST_DOC_ID)
        
        # Случай 2: doc_id присутствует, но другой
        # ОЖИДАНИЕ: нормализатор должен заменить на правильный
        chunks_with_old_id = [
            self.clause_chunk("maincontract:1.1", "Text", doc_id="old-wrong-id")
        ]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks_with_old_id)
        
        # Нормализатор ДОЛЖЕН установить правильный doc_id
        assert result[0]["metadata"]["doc_id"] == str(TEST_DOC_ID)
    
    def test_forces_chunk_kind_to_clause(self):
        """КОНТРАКТ: chunk_kind ВСЕГДА устанавливается в "clause" [web:959]"""
        chunks = [
            self.clause_chunk("maincontract:1.1", "Text", chunk_kind="section")
        ]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks)
        assert result[0]["metadata"]["chunk_kind"] == "clause"
    
    def test_skips_chunks_without_effective_uid(self):
        """КОНТРАКТ: chunks без effective_uid пропускаются [web:959]"""
        chunks = [
            {"id": "x", "text": "Some text", "metadata": {}},
        ]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks)
        assert result == []
    
    def test_skips_empty_text(self):
        """КОНТРАКТ: chunks с пустым текстом пропускаются [web:959]"""
        chunks = [
            self.clause_chunk("maincontract:1.1", ""),
            self.clause_chunk("maincontract:1.2", "   "),
        ]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks)
        assert result == []
    
    def test_preserves_node_kind(self):
        """КОНТРАКТ: node_kind сохраняется [web:959]"""
        chunks = [
            self.clause_chunk("maincontract:1.1", "Text", node_kind="section")
        ]
        result = ensure_clause_metadata(doc_id=TEST_DOC_ID, leaf_chunks=chunks)
        assert result[0]["metadata"]["node_kind"] == "section"


class TestCrossReferenceValidation:
    """
    ИНВАРИАНТЫ CrossReference:
    1. source_effective_uid и target_effective_uid не могут быть пустыми
    2. reference_text не может быть пустым
    3. явно заданный scope должен совпадать с scope из effective_uid
    """
    
    def test_valid_same_scope_reference(self):
        """КОНТРАКТ: ссылка внутри одной области валидна [web:959]"""
        ref = CrossReference(
            source_effective_uid="maincontract:1.1",
            target_effective_uid="maincontract:1.2",
            reference_text="see clause 1.2",
        )
        assert ref.source_scope == "maincontract"
        assert ref.target_scope == "maincontract"
    
    def test_valid_cross_scope_reference(self):
        """КОНТРАКТ: ссылка между областями валидна [web:959]"""
        ref = CrossReference(
            source_effective_uid="maincontract:1.1",
            target_effective_uid="appendix_1:A.2",
            reference_text="see appendix A.2",
        )
        assert ref.source_scope == "maincontract"
        assert ref.target_scope == "appendix_1"
    
    def test_rejects_empty_fields(self):
        """ИНВАРИАНТ: все обязательные поля должны быть непустыми [web:959]"""
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
    
    def test_scope_consistency(self):
        """ИНВАРИАНТ: явно заданный scope должен совпадать с scope из uid [web:959]"""
        with pytest.raises(ValueError, match="source_scope mismatch"):
            CrossReference(
                source_effective_uid="maincontract:1.1",
                target_effective_uid="maincontract:1.2",
                source_scope="appendix_1",  # несоответствие!
                reference_text="ref",
            )
        
        with pytest.raises(ValueError, match="target_scope mismatch"):
            CrossReference(
                source_effective_uid="maincontract:1.1",
                target_effective_uid="appendix_1:A.2",
                target_scope="maincontract",  # несоответствие!
                reference_text="ref",
            )


class TestCrossSegmentRefValidation:
    """
    ИНВАРИАНТЫ CrossSegmentRef:
    1. resolution_confidence должна быть в диапазоне [0.0, 1.0]
    2. target_scope_hint должен совпадать с scope из target_effective_uid
    3. source_effective_uid обязателен
    """
    
    def test_unresolved_reference(self):
        """КОНТРАКТ: unresolved ссылка имеет resolution_method="unresolved" [web:959]"""
        ref = CrossSegmentRef(
            source_effective_uid="maincontract:1.1",
            target_raw_uid="A.1",
            target_scope_hint="appendix_1",
            reference_text="see appendix A.1",
        )
        assert ref.resolution_method == "unresolved"
    
    def test_resolved_reference(self):
        """КОНТРАКТ: resolved ссылка имеет target_effective_uid [web:959]"""
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
    
    def test_confidence_range_validation(self):
        """ИНВАРИАНТ: confidence в диапазоне [0.0, 1.0] [web:959]"""
        with pytest.raises(ValueError, match=r"resolution_confidence"):
            CrossSegmentRef(
                source_effective_uid="maincontract:1.1",
                target_raw_uid="A.1",
                target_scope_hint="appendix_1",
                resolution_confidence=1.5,  # > 1.0
                reference_text="ref",
            )
        
        with pytest.raises(ValueError, match=r"resolution_confidence"):
            CrossSegmentRef(
                source_effective_uid="maincontract:1.1",
                target_raw_uid="A.1",
                target_scope_hint="appendix_1",
                resolution_confidence=-0.1,  # < 0.0
                reference_text="ref",
            )
    
    def test_scope_hint_consistency(self):
        """ИНВАРИАНТ: target_scope_hint должен совпадать с scope из target_effective_uid [web:959]"""
        with pytest.raises(ValueError, match="target_scope_hint mismatch"):
            CrossSegmentRef(
                source_effective_uid="maincontract:1.1",
                target_raw_uid="A.1",
                target_scope_hint="maincontract",
                target_effective_uid="appendix_1:A.1",  # несоответствие!
                reference_text="ref",
            )

