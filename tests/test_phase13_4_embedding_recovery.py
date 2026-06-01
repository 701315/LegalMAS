# tests/test_phase13_4_embedding_recovery.py

"""
Phase 13.4 — Unit tests for EmbeddingRecoveryEngine.

Все тесты используют mock EmbeddingService — реальная модель не загружается.
Маркер: без специальных markers, входит в обычный pytest run.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from services.structure._hierarchy_builder._embedding_recovery import (
    EmbeddingRecoveryEngine,
    EmbeddingRecoveryResult,
    _build_candidate_pool,
    _cosine_similarity,
    _get_node_text,
    _is_best_effort_orphan,
)
from services.structure._models._recovery import (
    CandidateWindow,
    RecoveryStrategyType,
)
from services.structure.models import MutableHierarchyNode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_node(
    uid: str,
    *,
    level: int = 1,
    page: int = 1,
    title: str = "",
    own_text: str = "",
    best_effort: bool = False,
    children: list | None = None,
    scope: str = "global",
) -> MutableHierarchyNode:
    """
    Фабрика MutableHierarchyNode для тестов.

    effective_uid строится в формате 'scope:raw_uid', который требует
    MutableHierarchyNode.__post_init__ → split_effective_uid().
    """
    effective_uid = f"{scope}:{uid}"
    node = MutableHierarchyNode(
        effective_uid=effective_uid,
        raw_uid=uid,
        scope=scope,
        title=title or uid,
        level=level,
        start_page=page,
        end_page=page,
        node_origin="semantic_heading",
        content_mode="full_text",
        citability="medium",
        diagnostics={},
    )
    node.own_text = own_text
    node.children = children or []
    if best_effort:
        node.diagnostics["recovered_via_best_effort"] = True
    return node


def _nodes(*nodes: MutableHierarchyNode) -> dict[str, MutableHierarchyNode]:
    """
    Строит dict keyed by effective_uid — точно как реальный pipeline.

    Использовать во всех тестах вместо ручного {"uid": node},
    чтобы uid_to_idx в EmbeddingRecoveryEngine находил ноды корректно.
    """
    return {n.effective_uid: n for n in nodes}


def _make_engine(
    *,
    enabled: bool = True,
    threshold: float = 0.72,
    max_page_distance: int = 3,
    max_level_delta: int = 2,
) -> EmbeddingRecoveryEngine:
    window = CandidateWindow(
        max_page_distance=max_page_distance,
        max_level_delta=max_level_delta,
    )
    return EmbeddingRecoveryEngine(
        enabled=enabled,
        threshold=threshold,
        window=window,
    )


def _mock_embed_service(vectors: dict[str, np.ndarray]):
    """
    Создаёт mock EmbeddingService.

    vectors: {title_substring: vector} — матчит по вхождению в текст ноды.
    Если текст не совпал ни с одним ключом — возвращает нулевой вектор.
    """
    svc = MagicMock()
    svc.is_enabled = True

    def _encode(texts: list[str]) -> np.ndarray:
        result = []
        for text in texts:
            vec = None
            for key, v in vectors.items():
                if key in text:
                    vec = v
                    break
            if vec is None:
                vec = np.zeros(4)
            result.append(vec)
        return np.array(result)

    svc.encode.side_effect = _encode
    return svc


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_is_best_effort_orphan_true(self):
        node = _make_node("x", best_effort=True)
        assert _is_best_effort_orphan(node) is True

    def test_is_best_effort_orphan_false(self):
        node = _make_node("x", best_effort=False)
        assert _is_best_effort_orphan(node) is False

    def test_get_node_text_title_only(self):
        node = _make_node("x", title="Payment Terms")
        assert _get_node_text(node) == "Payment Terms"

    def test_get_node_text_title_and_own_text(self):
        node = _make_node("x", title="Sec 1", own_text="A" * 300)
        text = _get_node_text(node)
        assert text.startswith("Sec 1")
        # title + space + не более 200 символов own_text
        assert len(text) <= len("Sec 1") + 1 + 200

    def test_cosine_similarity_identical(self):
        v = np.array([1.0, 0.0, 0.0, 0.0])
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_similarity_zero_vector(self):
        a = np.zeros(4)
        b = np.array([1.0, 0.0, 0.0, 0.0])
        assert _cosine_similarity(a, b) == 0.0


# ---------------------------------------------------------------------------
# Unit tests: candidate pool
# ---------------------------------------------------------------------------

class TestCandidatePool:
    def _window(self) -> CandidateWindow:
        return CandidateWindow(max_page_distance=5, max_level_delta=3)

    def test_excludes_self(self):
        orphan = _make_node("orphan", level=2, page=1)
        node_map = _nodes(orphan)
        result = _build_candidate_pool(node_map, orphan.effective_uid, 2, 1, self._window())
        assert result == []

    def test_excludes_best_effort_nodes(self):
        orphan = _make_node("orphan", level=2, page=1, best_effort=True)
        other = _make_node("other", level=1, page=1, best_effort=True)
        node_map = _nodes(orphan, other)
        result = _build_candidate_pool(node_map, orphan.effective_uid, 2, 1, self._window())
        assert result == []

    def test_excludes_same_or_lower_level(self):
        orphan = _make_node("orphan", level=2, page=1)
        peer = _make_node("peer", level=2, page=1)
        child = _make_node("child", level=3, page=1)
        node_map = _nodes(orphan, peer, child)
        result = _build_candidate_pool(node_map, orphan.effective_uid, 2, 1, self._window())
        assert result == []

    def test_respects_page_distance(self):
        orphan = _make_node("orphan", level=2, page=10)
        far_parent = _make_node("far", level=1, page=1)  # distance=9 > max=3
        node_map = _nodes(orphan, far_parent)
        window = CandidateWindow(max_page_distance=3, max_level_delta=2)
        result = _build_candidate_pool(node_map, orphan.effective_uid, 2, 10, window)
        assert result == []

    def test_includes_valid_candidate(self):
        orphan = _make_node("orphan", level=2, page=2)
        parent = _make_node("parent", level=1, page=1)  # distance=1, delta=1
        node_map = _nodes(orphan, parent)
        window = CandidateWindow(max_page_distance=3, max_level_delta=2)
        result = _build_candidate_pool(node_map, orphan.effective_uid, 2, 2, window)
        assert len(result) == 1
        assert result[0].effective_uid == parent.effective_uid


# ---------------------------------------------------------------------------
# Unit tests: EmbeddingRecoveryEngine
# ---------------------------------------------------------------------------

class TestEmbeddingRecoveryEngine:
    def test_disabled_returns_empty_result(self):
        engine = _make_engine(enabled=False)
        orphan = _make_node("orphan", best_effort=True)
        node_map = _nodes(orphan)
        result = engine.recover(node_map, document_id="doc1")
        assert isinstance(result, EmbeddingRecoveryResult)
        assert result.recovered_count == 0
        # disabled=False т.к. engine выходит до проверки orphans
        assert result.disabled_count == 0

    def test_no_orphans_returns_empty_result(self):
        engine = _make_engine()
        normal = _make_node("n1", best_effort=False)
        node_map = _nodes(normal)
        with patch.object(engine, "_get_embedding_service") as mock_svc:
            result = engine.recover(node_map, document_id="doc1")
        # encode не должен вызываться если нет orphans
        mock_svc.assert_not_called()
        assert result.recovered_count == 0

    def test_service_disabled_returns_disabled_count(self):
        engine = _make_engine()
        orphan = _make_node("orphan", level=2, best_effort=True)
        node_map = _nodes(orphan)
        mock_svc = MagicMock()
        mock_svc.is_enabled = False
        with patch.object(engine, "_get_embedding_service", return_value=mock_svc):
            result = engine.recover(node_map, document_id="doc1")
        assert result.disabled_count == 1
        assert result.recovered_count == 0

    def test_encode_failure_is_isolated(self):
        engine = _make_engine()
        orphan = _make_node("orphan", level=2, best_effort=True)
        node_map = _nodes(orphan)
        mock_svc = MagicMock()
        mock_svc.is_enabled = True
        mock_svc.encode.side_effect = RuntimeError("GPU OOM")
        with patch.object(engine, "_get_embedding_service", return_value=mock_svc):
            result = engine.recover(node_map, document_id="doc1")
        # pipeline не упал, ошибка изолирована
        assert result.error_count == 1
        assert result.recovered_count == 0

    def test_below_threshold_skipped(self):
        engine = _make_engine(threshold=0.90)
        orphan = _make_node("orphan", level=2, page=1, title="orphan", best_effort=True)
        parent = _make_node("parent", level=1, page=1, title="parent")
        node_map = _nodes(orphan, parent)
        # cos([1,0,0,0], [0.5, 0.866, 0, 0]) ≈ 0.5 < 0.90
        vecs = {
            "orphan": np.array([1.0, 0.0, 0.0, 0.0]),
            "parent": np.array([0.5, 0.866, 0.0, 0.0]),
        }
        mock_svc = _mock_embed_service(vecs)
        with patch.object(engine, "_get_embedding_service", return_value=mock_svc):
            result = engine.recover(node_map, document_id="doc1")
        assert result.recovered_count == 0
        assert result.skipped_count == 1

    def test_successful_recovery(self):
        engine = _make_engine(threshold=0.72)
        orphan = _make_node("orphan", level=2, page=1, title="orphan", best_effort=True)
        parent = _make_node("parent", level=1, page=1, title="parent")
        node_map = _nodes(orphan, parent)
        # одинаковые векторы → similarity = 1.0 >> 0.72
        v = np.array([1.0, 0.0, 0.0, 0.0])
        mock_svc = _mock_embed_service({"orphan": v, "parent": v})
        with patch.object(engine, "_get_embedding_service", return_value=mock_svc):
            result = engine.recover(node_map, document_id="doc1")
        assert result.recovered_count == 1
        assert len(result.decisions) == 1
        assert result.decisions[0].recovered is True
        assert result.decisions[0].strategy_used == RecoveryStrategyType.EMBEDDINGS

    def test_orphan_added_as_child_of_parent(self):
        engine = _make_engine(threshold=0.72)
        orphan = _make_node("orphan", level=2, page=1, title="orphan", best_effort=True)
        parent = _make_node("parent", level=1, page=1, title="parent")
        node_map = _nodes(orphan, parent)
        v = np.array([1.0, 0.0, 0.0, 0.0])
        mock_svc = _mock_embed_service({"orphan": v, "parent": v})
        with patch.object(engine, "_get_embedding_service", return_value=mock_svc):
            engine.recover(node_map, document_id="doc1")
        assert orphan in parent.children

    def test_diagnostics_updated_after_recovery(self):
        engine = _make_engine(threshold=0.72)
        orphan = _make_node("orphan", level=2, page=1, title="orphan", best_effort=True)
        parent = _make_node("parent", level=1, page=1, title="parent")
        node_map = _nodes(orphan, parent)
        v = np.array([1.0, 0.0, 0.0, 0.0])
        mock_svc = _mock_embed_service({"orphan": v, "parent": v})
        with patch.object(engine, "_get_embedding_service", return_value=mock_svc):
            engine.recover(node_map, document_id="doc1")
        assert orphan.diagnostics.get("recovered_via_best_effort") is False
        assert orphan.diagnostics.get("recovered_via_embedding") is True
        # parent_uid в diagnostics — это effective_uid ("global:parent")
        assert orphan.diagnostics.get("embedding_recovery_parent_uid") == parent.effective_uid
        assert "embedding_recovery_confidence" in orphan.diagnostics

    def test_best_effort_node_cannot_be_parent(self):
        engine = _make_engine(threshold=0.72)
        orphan1 = _make_node("orphan1", level=2, page=1, title="orphan1", best_effort=True)
        orphan2 = _make_node("orphan2", level=3, page=1, title="orphan2", best_effort=True)
        node_map = _nodes(orphan1, orphan2)
        v = np.array([1.0, 0.0, 0.0, 0.0])
        mock_svc = _mock_embed_service({"orphan1": v, "orphan2": v})
        with patch.object(engine, "_get_embedding_service", return_value=mock_svc):
            result = engine.recover(node_map, document_id="doc1")
        # ни один best_effort node не может стать parent другого
        assert result.recovered_count == 0

    def test_window_constraint_respected(self):
        engine = _make_engine(threshold=0.72, max_page_distance=2)
        orphan = _make_node("orphan", level=2, page=10, title="orphan", best_effort=True)
        far_parent = _make_node("far", level=1, page=1, title="far")  # distance=9 > 2
        node_map = _nodes(orphan, far_parent)
        v = np.array([1.0, 0.0, 0.0, 0.0])
        mock_svc = _mock_embed_service({"orphan": v, "far": v})
        with patch.object(engine, "_get_embedding_service", return_value=mock_svc):
            result = engine.recover(node_map, document_id="doc1")
        assert result.recovered_count == 0
        assert result.skipped_count == 1

    def test_result_to_dict(self):
        result = EmbeddingRecoveryResult(
            recovered_count=2,
            skipped_count=1,
            disabled_count=0,
            error_count=0,
        )
        d = result.to_dict()
        assert d["recovered_count"] == 2
        assert d["skipped_count"] == 1
        assert "disabled_count" in d
        assert "error_count" in d


