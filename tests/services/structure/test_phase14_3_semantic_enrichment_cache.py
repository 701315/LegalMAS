"""
Phase 14.3.A — Semantic Enrichment LLM Response Cache.

Покрытие:
- sync path reuse внутри одного document_version
- async path reuse внутри одного document_version
- cache isolation между разными document_version
- invalid response не кэшируется
- cache bypass если document_version_id отсутствует
- cache bypass если feature flag выключен
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.structure.semantic_enrichment._cache import (
    get_semantic_enrichment_response_cache,
)
from services.structure.semantic_enrichment._types import SemanticEnrichmentPolicy


def _make_unit(unit_id: str = "unit-1") -> SimpleNamespace:
    return SimpleNamespace(
        unit_id=unit_id,
        raw_uid="1",
        title="Payments",
        own_text="Payment shall be made within 30 days.",
        subtree_text="Payment shall be made within 30 days.",
        unit_type=SimpleNamespace(value="unknown"),
        clause_function=SimpleNamespace(value="unknown"),
        topic_tags=[],
        citability=SimpleNamespace(citability_band="medium"),
        scope="main",
        level=1,
        node_kind="clause",
        semantic_node_type="clause",
        recovered_via_best_effort=False,
    )


@pytest.fixture(autouse=True)
def _reset_cache_and_settings():
    from core.config import settings

    cache = get_semantic_enrichment_response_cache()
    cache.clear()

    old_enabled = settings.SEMANTIC_ENRICHMENT_CACHE_ENABLED
    old_ttl = settings.SEMANTIC_ENRICHMENT_CACHE_TTL_SECONDS
    old_max_items = settings.SEMANTIC_ENRICHMENT_CACHE_MAX_ITEMS

    settings.SEMANTIC_ENRICHMENT_CACHE_ENABLED = True
    settings.SEMANTIC_ENRICHMENT_CACHE_TTL_SECONDS = 3600
    settings.SEMANTIC_ENRICHMENT_CACHE_MAX_ITEMS = 100

    yield

    settings.SEMANTIC_ENRICHMENT_CACHE_ENABLED = old_enabled
    settings.SEMANTIC_ENRICHMENT_CACHE_TTL_SECONDS = old_ttl
    settings.SEMANTIC_ENRICHMENT_CACHE_MAX_ITEMS = old_max_items

    cache.clear()


class TestSemanticEnrichmentCacheSync:
    def test_same_document_version_hits_cache(self):
        from services.structure.semantic_enrichment._enricher import enrich_single_unit

        unit = _make_unit()
        policy = SemanticEnrichmentPolicy()
        proposal = MagicMock(confidence=0.91)
        enrichment = MagicMock()
        enrichment.status = MagicMock(value="applied")
        enrichment.applied_fields = ["unit_type"]

        with patch(
            "services.structure.semantic_enrichment._enricher.is_unit_eligible_for_enrichment",
            return_value=(True, None),
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt",
                return_value="PROMPT_A",
            ):
                with patch(
                    "services.structure.semantic_enrichment._enricher.call_semantic_enrichment_llm",
                    return_value=('{"ok": true}', {}),
                ) as mock_llm:
                    with patch(
                        "services.structure.semantic_enrichment._enricher.parse_llm_enrichment_response",
                        return_value=proposal,
                    ):
                        with patch(
                            "services.structure.semantic_enrichment._enricher.apply_enrichment_policy",
                            return_value=enrichment,
                        ):
                            enrich_single_unit(
                                unit=unit,
                                previous_unit=None,
                                next_unit=None,
                                all_units=[unit],
                                policy=policy,
                                document_id="doc-1",
                                document_version_id="ver-1",
                            )
                            enrich_single_unit(
                                unit=unit,
                                previous_unit=None,
                                next_unit=None,
                                all_units=[unit],
                                policy=policy,
                                document_id="doc-1",
                                document_version_id="ver-1",
                            )

        assert mock_llm.call_count == 1

    def test_different_document_version_does_not_hit_cache(self):
        from services.structure.semantic_enrichment._enricher import enrich_single_unit

        unit = _make_unit()
        policy = SemanticEnrichmentPolicy()
        proposal = MagicMock(confidence=0.91)
        enrichment = MagicMock()
        enrichment.status = MagicMock(value="applied")
        enrichment.applied_fields = ["unit_type"]

        with patch(
            "services.structure.semantic_enrichment._enricher.is_unit_eligible_for_enrichment",
            return_value=(True, None),
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt",
                return_value="PROMPT_A",
            ):
                with patch(
                    "services.structure.semantic_enrichment._enricher.call_semantic_enrichment_llm",
                    return_value=('{"ok": true}', {}),
                ) as mock_llm:
                    with patch(
                        "services.structure.semantic_enrichment._enricher.parse_llm_enrichment_response",
                        return_value=proposal,
                    ):
                        with patch(
                            "services.structure.semantic_enrichment._enricher.apply_enrichment_policy",
                            return_value=enrichment,
                        ):
                            enrich_single_unit(
                                unit=unit,
                                previous_unit=None,
                                next_unit=None,
                                all_units=[unit],
                                policy=policy,
                                document_id="doc-1",
                                document_version_id="ver-1",
                            )
                            enrich_single_unit(
                                unit=unit,
                                previous_unit=None,
                                next_unit=None,
                                all_units=[unit],
                                policy=policy,
                                document_id="doc-1",
                                document_version_id="ver-2",
                            )

        assert mock_llm.call_count == 2

    def test_invalid_response_is_not_cached(self):
        from services.structure.semantic_enrichment._enricher import enrich_single_unit

        unit = _make_unit()
        policy = SemanticEnrichmentPolicy()

        with patch(
            "services.structure.semantic_enrichment._enricher.is_unit_eligible_for_enrichment",
            return_value=(True, None),
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt",
                return_value="PROMPT_A",
            ):
                with patch(
                    "services.structure.semantic_enrichment._enricher.call_semantic_enrichment_llm",
                    return_value=("not valid", {}),
                ) as mock_llm:
                    with patch(
                        "services.structure.semantic_enrichment._enricher.parse_llm_enrichment_response",
                        return_value=None,
                    ):
                        enrich_single_unit(
                            unit=unit,
                            previous_unit=None,
                            next_unit=None,
                            all_units=[unit],
                            policy=policy,
                            document_id="doc-1",
                            document_version_id="ver-1",
                        )
                        enrich_single_unit(
                            unit=unit,
                            previous_unit=None,
                            next_unit=None,
                            all_units=[unit],
                            policy=policy,
                            document_id="doc-1",
                            document_version_id="ver-1",
                        )

        assert mock_llm.call_count == 2

    def test_missing_document_version_bypasses_cache(self):
        from services.structure.semantic_enrichment._enricher import enrich_single_unit

        unit = _make_unit()
        policy = SemanticEnrichmentPolicy()
        proposal = MagicMock(confidence=0.91)
        enrichment = MagicMock()
        enrichment.status = MagicMock(value="applied")
        enrichment.applied_fields = ["unit_type"]

        with patch(
            "services.structure.semantic_enrichment._enricher.is_unit_eligible_for_enrichment",
            return_value=(True, None),
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt",
                return_value="PROMPT_A",
            ):
                with patch(
                    "services.structure.semantic_enrichment._enricher.call_semantic_enrichment_llm",
                    return_value=('{"ok": true}', {}),
                ) as mock_llm:
                    with patch(
                        "services.structure.semantic_enrichment._enricher.parse_llm_enrichment_response",
                        return_value=proposal,
                    ):
                        with patch(
                            "services.structure.semantic_enrichment._enricher.apply_enrichment_policy",
                            return_value=enrichment,
                        ):
                            enrich_single_unit(
                                unit=unit,
                                previous_unit=None,
                                next_unit=None,
                                all_units=[unit],
                                policy=policy,
                                document_id="doc-1",
                                document_version_id=None,
                            )
                            enrich_single_unit(
                                unit=unit,
                                previous_unit=None,
                                next_unit=None,
                                all_units=[unit],
                                policy=policy,
                                document_id="doc-1",
                                document_version_id=None,
                            )

        assert mock_llm.call_count == 2

    def test_disabled_cache_bypasses_reuse(self):
        from core.config import settings
        from services.structure.semantic_enrichment._enricher import enrich_single_unit

        settings.SEMANTIC_ENRICHMENT_CACHE_ENABLED = False

        unit = _make_unit()
        policy = SemanticEnrichmentPolicy()
        proposal = MagicMock(confidence=0.91)
        enrichment = MagicMock()
        enrichment.status = MagicMock(value="applied")
        enrichment.applied_fields = ["unit_type"]

        with patch(
            "services.structure.semantic_enrichment._enricher.is_unit_eligible_for_enrichment",
            return_value=(True, None),
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt",
                return_value="PROMPT_A",
            ):
                with patch(
                    "services.structure.semantic_enrichment._enricher.call_semantic_enrichment_llm",
                    return_value=('{"ok": true}', {}),
                ) as mock_llm:
                    with patch(
                        "services.structure.semantic_enrichment._enricher.parse_llm_enrichment_response",
                        return_value=proposal,
                    ):
                        with patch(
                            "services.structure.semantic_enrichment._enricher.apply_enrichment_policy",
                            return_value=enrichment,
                        ):
                            enrich_single_unit(
                                unit=unit,
                                previous_unit=None,
                                next_unit=None,
                                all_units=[unit],
                                policy=policy,
                                document_id="doc-1",
                                document_version_id="ver-1",
                            )
                            enrich_single_unit(
                                unit=unit,
                                previous_unit=None,
                                next_unit=None,
                                all_units=[unit],
                                policy=policy,
                                document_id="doc-1",
                                document_version_id="ver-1",
                            )

        assert mock_llm.call_count == 2


class TestSemanticEnrichmentCacheAsync:
    @pytest.mark.asyncio
    async def test_async_same_document_version_hits_cache(self):
        from services.structure.semantic_enrichment._enricher import (
            enrich_single_unit_async,
        )

        unit = _make_unit()
        policy = SemanticEnrichmentPolicy()
        proposal = MagicMock(confidence=0.91)
        enrichment = MagicMock()
        enrichment.status = MagicMock(value="applied")
        enrichment.applied_fields = ["unit_type"]

        with patch(
            "services.structure.semantic_enrichment._enricher.is_unit_eligible_for_enrichment",
            return_value=(True, None),
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt",
                return_value="PROMPT_A",
            ):
                with patch(
                    "services.structure.semantic_enrichment._llm_client.call_semantic_enrichment_llm_async",
                    new_callable=AsyncMock,
                    return_value=('{"ok": true}', {}),
                ) as mock_llm_async:
                    with patch(
                        "services.structure.semantic_enrichment._enricher.parse_llm_enrichment_response",
                        return_value=proposal,
                    ):
                        with patch(
                            "services.structure.semantic_enrichment._enricher.apply_enrichment_policy",
                            return_value=enrichment,
                        ):
                            await enrich_single_unit_async(
                                unit=unit,
                                previous_unit=None,
                                next_unit=None,
                                all_units=[unit],
                                policy=policy,
                                document_id="doc-1",
                                document_version_id="ver-1",
                            )
                            await enrich_single_unit_async(
                                unit=unit,
                                previous_unit=None,
                                next_unit=None,
                                all_units=[unit],
                                policy=policy,
                                document_id="doc-1",
                                document_version_id="ver-1",
                            )

        assert mock_llm_async.await_count == 1

        