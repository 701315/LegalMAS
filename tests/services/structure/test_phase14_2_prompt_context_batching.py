"""
Phase 14.2.A — Safe Prompt Context Batching.

Покрытие:
- build_semantic_enrichment_prompt_context() строит segment-scoped invariants
- _build_heading_path() с precomputed uid_to_title даёт тот же результат
- build_semantic_enrichment_prompt() с prompt_context даёт IDENTICAL prompt
- sync enricher строит prompt_context один раз на snapshot
- async enricher строит prompt_context один раз на snapshot

Важно:
- Это НЕ true multi-unit LLM batching.
- Мы оптимизируем только preparation layer, сохраняя per-unit LLM calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.structure.semantic_enrichment._policy import (
    build_skipped_enrichment,
)
from services.structure.semantic_enrichment._prompting import (
    _build_heading_path,
    build_semantic_enrichment_prompt,
    build_semantic_enrichment_prompt_context,
)


def _make_unit(
    *,
    unit_id: str,
    raw_uid: str,
    title: str,
    own_text: str,
    level: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        unit_id=unit_id,
        raw_uid=raw_uid,
        title=title,
        own_text=own_text,
        subtree_text=own_text,
        unit_type=SimpleNamespace(value="unknown"),
        clause_function=SimpleNamespace(value="unknown"),
        topic_tags=[],
        citability=SimpleNamespace(citability_band="medium"),
        scope="main",
        level=level,
        node_kind="clause",
        semantic_node_type="clause",
        recovered_via_best_effort=False,
    )


def _make_snapshot(units: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(
        document_id="doc-14-2",
        document_version_id="ver-14-2",
        segment_id="seg-14-2",
        segment_type="main",
        segment_order=0,
        is_primary_segment=True,
        units=units,
    )


class TestPromptContextBuilder:
    def test_build_prompt_context_contains_expected_fields(self):
        units = [
            _make_unit(
                unit_id="u1",
                raw_uid="7",
                title="Платежи",
                own_text="Раздел о платежах.",
            ),
            _make_unit(
                unit_id="u2",
                raw_uid="7.2",
                title="Порядок оплаты",
                own_text="Оплата в течение 30 дней.",
                level=2,
            ),
        ]

        ctx = build_semantic_enrichment_prompt_context(units)

        assert isinstance(ctx.allowed_unit_types_json, str)
        assert isinstance(ctx.allowed_clause_functions_json, str)
        assert isinstance(ctx.clause_function_ontology_json, str)
        assert isinstance(ctx.allowed_topics_json, str)

        assert ctx.uid_to_title["7"] == "Платежи"
        assert ctx.uid_to_title["7.2"] == "Порядок оплаты"

    def test_heading_path_precomputed_map_matches_legacy_path(self):
        units = [
            _make_unit(
                unit_id="u1",
                raw_uid="7",
                title="Платежи",
                own_text="Раздел о платежах.",
            ),
            _make_unit(
                unit_id="u2",
                raw_uid="7.2",
                title="Порядок оплаты",
                own_text="Оплата в течение 30 дней.",
                level=2,
            ),
            _make_unit(
                unit_id="u3",
                raw_uid="7.2.1",
                title="Срок платежа",
                own_text="Покупатель оплачивает в течение 30 дней.",
                level=3,
            ),
        ]

        ctx = build_semantic_enrichment_prompt_context(units)
        target = units[2]

        legacy_path = _build_heading_path(target, all_units=units)
        optimized_path = _build_heading_path(target, uid_to_title=ctx.uid_to_title)

        assert optimized_path == legacy_path

    def test_prompt_with_context_is_identical_to_legacy_prompt(self):
        units = [
            _make_unit(
                unit_id="u1",
                raw_uid="7",
                title="Платежи",
                own_text="Раздел о платежах.",
            ),
            _make_unit(
                unit_id="u2",
                raw_uid="7.2",
                title="Порядок оплаты",
                own_text="Оплата в течение 30 дней.",
                level=2,
            ),
        ]

        ctx = build_semantic_enrichment_prompt_context(units)

        legacy_prompt = build_semantic_enrichment_prompt(
            unit=units[1],
            previous_unit=units[0],
            next_unit=None,
            all_units=units,
        )

        optimized_prompt = build_semantic_enrichment_prompt(
            unit=units[1],
            previous_unit=units[0],
            next_unit=None,
            all_units=units,
            prompt_context=ctx,
        )

        assert optimized_prompt == legacy_prompt


class TestEnricherPromptContextBatching:
    def test_sync_enricher_builds_context_once_per_snapshot(self):
        from services.structure.semantic_enrichment._enricher import enrich_legal_units

        units = [
            _make_unit(
                unit_id="u1",
                raw_uid="1",
                title="Definitions",
                own_text="Definitions section.",
            ),
            _make_unit(
                unit_id="u2",
                raw_uid="2",
                title="Payments",
                own_text="Payment shall be made in 30 days.",
            ),
            _make_unit(
                unit_id="u3",
                raw_uid="3",
                title="Liability",
                own_text="Liability is limited.",
            ),
        ]
        snapshot = _make_snapshot(units)

        fake_context = MagicMock()

        def _fake_enrich_single(*, unit, policy, **kwargs):
            return build_skipped_enrichment(unit, policy=policy, reason="test_skip")

        with patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=True,
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt_context",
                return_value=fake_context,
            ) as mock_build_context:
                with patch(
                    "services.structure.semantic_enrichment._enricher.enrich_single_unit",
                    side_effect=_fake_enrich_single,
                ) as mock_single:
                    result = enrich_legal_units(snapshot)

        assert len(result.enrichments) == 3
        mock_build_context.assert_called_once_with(units)
        assert mock_single.call_count == 3

        for call in mock_single.call_args_list:
            assert call.kwargs["prompt_context"] is fake_context

    def test_sync_enricher_does_not_build_context_when_llm_unavailable(self):
        from services.structure.semantic_enrichment._enricher import enrich_legal_units

        units = [
            _make_unit(
                unit_id="u1",
                raw_uid="1",
                title="Payments",
                own_text="Payment text.",
            ),
        ]
        snapshot = _make_snapshot(units)

        with patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=False,
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt_context",
            ) as mock_build_context:
                result = enrich_legal_units(snapshot)

        assert len(result.enrichments) == 1
        mock_build_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_enricher_builds_context_once_per_snapshot(self):
        from services.structure.semantic_enrichment._enricher import enrich_legal_units_async

        units = [
            _make_unit(
                unit_id="u1",
                raw_uid="1",
                title="Definitions",
                own_text="Definitions section.",
            ),
            _make_unit(
                unit_id="u2",
                raw_uid="2",
                title="Payments",
                own_text="Payment shall be made in 30 days.",
            ),
        ]
        snapshot = _make_snapshot(units)

        fake_context = MagicMock()

        async def _fake_enrich_single_async(*, unit, policy, **kwargs):
            return build_skipped_enrichment(unit, policy=policy, reason="test_skip")

        with patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=True,
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt_context",
                return_value=fake_context,
            ) as mock_build_context:
                with patch(
                    "services.structure.semantic_enrichment._enricher.enrich_single_unit_async",
                    new_callable=AsyncMock,
                    side_effect=_fake_enrich_single_async,
                ) as mock_single_async:
                    result = await enrich_legal_units_async(snapshot)

        assert len(result.enrichments) == 2
        mock_build_context.assert_called_once_with(units)
        assert mock_single_async.await_count == 2

        for call in mock_single_async.call_args_list:
            assert call.kwargs["prompt_context"] is fake_context

    @pytest.mark.asyncio
    async def test_async_enricher_does_not_build_context_when_llm_unavailable(self):
        from services.structure.semantic_enrichment._enricher import enrich_legal_units_async

        units = [
            _make_unit(
                unit_id="u1",
                raw_uid="1",
                title="Payments",
                own_text="Payment text.",
            ),
        ]
        snapshot = _make_snapshot(units)

        with patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=False,
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt_context",
            ) as mock_build_context:
                result = await enrich_legal_units_async(snapshot)

        assert len(result.enrichments) == 1
        mock_build_context.assert_not_called()


        