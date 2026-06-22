# tests/unit/mas_queue/test_queue_routing.py
"""
Tests for Celery task queue routing contract.

Invariant: segment classification and enrichment must be on separate queues
to prevent head-of-line blocking.

When classify_document_segments and build_legal_units_enrichment share the
same queue and the same worker, a long segment classification (16+ minutes)
blocks enrichment from starting. This was confirmed in production logs.

These tests protect against accidental re-merging onto the same queue.
"""

import pytest

from mas_queue.celery_app import (
    celery_app,
    QUEUE_HEAVY_LLM_ENRICHMENT,
    QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION,
    QUEUE_HEAVY_LLM_CHECKS,
)


class TestQueueRouting:
    """Verify that heavy LLM tasks are routed to the correct queues."""

    def _get_route(self, task_name: str) -> dict:
        routes = celery_app.conf.task_routes or {}
        return routes.get(task_name, {})

    def test_enrichment_on_heavy_llm_enrichment_queue(self):
        route = self._get_route("workers.build_legal_units_enrichment")
        assert route.get("queue") == QUEUE_HEAVY_LLM_ENRICHMENT, (
            "build_legal_units_enrichment must be on heavy_llm_enrichment queue"
        )

    def test_segment_classification_on_dedicated_queue(self):
        route = self._get_route("workers.classify_document_segments")
        assert route.get("queue") == QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION, (
            "classify_document_segments must be on heavy_llm_segment_classification queue, "
            "not on heavy_llm_enrichment — to prevent head-of-line blocking"
        )

    def test_enrichment_and_classification_on_different_queues(self):
        enrichment_route = self._get_route("workers.build_legal_units_enrichment")
        classification_route = self._get_route("workers.classify_document_segments")

        enrichment_queue = enrichment_route.get("queue")
        classification_queue = classification_route.get("queue")

        assert enrichment_queue is not None
        assert classification_queue is not None
        assert enrichment_queue != classification_queue, (
            "Enrichment and segment classification must be on separate queues. "
            f"Both are currently on '{enrichment_queue}'. "
            "This causes head-of-line blocking: a long segment classification "
            "blocks the enrichment worker."
        )

    def test_queue_constants_are_distinct_strings(self):
        assert QUEUE_HEAVY_LLM_ENRICHMENT != QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION
        assert isinstance(QUEUE_HEAVY_LLM_ENRICHMENT, str)
        assert isinstance(QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION, str)
        assert QUEUE_HEAVY_LLM_ENRICHMENT.strip()
        assert QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION.strip()

    def test_segment_classification_queue_is_declared(self):
        """Verify the new queue is declared in task_queues configuration."""
        declared_queue_names = {
            q.name for q in (celery_app.conf.task_queues or [])
        }
        assert QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION in declared_queue_names, (
            f"Queue '{QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION}' must be declared "
            f"in celery_app.conf.task_queues. "
            f"Declared queues: {declared_queue_names}"
        )

    def test_checks_on_heavy_llm_checks_queue(self):
        """Regression: checks queue must not be on enrichment queue."""
        route = self._get_route("workers.run_single_check")
        assert route.get("queue") == QUEUE_HEAVY_LLM_CHECKS

    def test_all_three_heavy_queues_are_distinct(self):
        """All three heavy worker queues must be distinct strings."""
        queues = {
            QUEUE_HEAVY_LLM_ENRICHMENT,
            QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION,
            QUEUE_HEAVY_LLM_CHECKS,
        }
        assert len(queues) == 3, (
            "All three heavy queues must be distinct. "
            f"Got: enrichment={QUEUE_HEAVY_LLM_ENRICHMENT!r}, "
            f"classification={QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION!r}, "
            f"checks={QUEUE_HEAVY_LLM_CHECKS!r}"
        )


        