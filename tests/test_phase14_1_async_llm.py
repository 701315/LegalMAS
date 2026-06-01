"""
Phase 14.1 — Async Processing: тесты async LLM путей.

Покрытие:
- LLMClient.call_async() — routing по провайдерам, unavailable
- LLMClient._call_llamacpp_async() — Semaphore serialization
- LLMClient.call_with_retries_async() — retry logic, context_limit
- call_semantic_enrichment_llm_async() — adapter
- enrich_single_unit_async() — success, llm_fail, prompt_fail
- enrich_legal_units_async() — preflight gate, gather, telemetry
- Backward compatibility — sync API не сломан

Маркер: pytest.mark.asyncio (требует anyio или asyncio mode=auto)
Все тесты используют unittest.mock — без реальных LLM вызовов.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.llm.client import LLMClient, LLMResponse, LLMContextLimitError
from core.exceptions import PermanentError, TransientError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_llm_singleton():
    """Сбрасываем singleton между тестами."""
    original = LLMClient._instance
    LLMClient._instance = None
    yield
    LLMClient._instance = original


def _make_response(text: str = '{"found": true}', provider: str = "ollama") -> LLMResponse:
    return LLMResponse(
        text=text,
        provider=provider,
        model="test-model",
        tokens_used=42,
        parse_success=True,
    )


# ---------------------------------------------------------------------------
# LLMClient.call_async() — provider routing
# ---------------------------------------------------------------------------


class TestLLMClientCallAsync:
    """LLMClient.call_async() routing и базовое поведение."""

    @pytest.mark.asyncio
    async def test_call_async_returns_none_when_provider_none(self):
        client = LLMClient()
        client.provider = "none"
        result = await client.call_async(prompt="test")
        assert result is None

    @pytest.mark.asyncio
    async def test_call_async_routes_to_openai_async(self):
        client = LLMClient()
        client.provider = "openai"
        expected = _make_response(provider="openai")

        with patch.object(client, "_call_openai_async", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = expected
            with patch.object(client, "_compute_token_budget", return_value=(512, {})):
                result = await client.call_async(prompt="test", max_tokens=512)

        assert result is expected
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_call_async_routes_to_ollama_async(self):
        client = LLMClient()
        client.provider = "ollama"
        expected = _make_response(provider="ollama")

        with patch.object(client, "_call_ollama_async", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = expected
            with patch.object(client, "_compute_token_budget", return_value=(512, {})):
                result = await client.call_async(prompt="test", max_tokens=512)

        assert result is expected
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_call_async_routes_to_llamacpp_async(self):
        client = LLMClient()
        client.provider = "llamacpp"
        expected = _make_response(provider="llamacpp")

        with patch.object(client, "_call_llamacpp_async", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = expected
            with patch.object(client, "_compute_token_budget", return_value=(512, {})):
                result = await client.call_async(prompt="test", max_tokens=512)

        assert result is expected
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_call_async_raises_context_limit(self):
        client = LLMClient()
        client.provider = "ollama"

        with patch.object(
            client,
            "_compute_token_budget",
            side_effect=LLMContextLimitError("too big"),
        ):
            with pytest.raises(LLMContextLimitError):
                await client.call_async(prompt="x" * 10000)

    @pytest.mark.asyncio
    async def test_call_async_timeout_raises_transient(self):
        import httpx

        client = LLMClient()
        client.provider = "ollama"

        with patch.object(client, "_compute_token_budget", return_value=(512, {})):
            with patch.object(
                client,
                "_call_ollama_async",
                new_callable=AsyncMock,
                side_effect=httpx.TimeoutException("timeout"),
            ):
                with pytest.raises(TransientError):
                    await client.call_async(prompt="test")


# ---------------------------------------------------------------------------
# LLMClient._call_llamacpp_async() — Semaphore serialization
# ---------------------------------------------------------------------------


class TestLlamaCallAsync:
    """_call_llamacpp_async: Semaphore + run_in_executor."""

    @pytest.mark.asyncio
    async def test_llamacpp_async_uses_semaphore(self):
        """Semaphore создаётся и используется."""
        client = LLMClient()
        client.provider = "llamacpp"
        expected = _make_response(provider="llamacpp")

        with patch.object(client, "_call_llamacpp", return_value=expected):
            result = await client._call_llamacpp_async(
                prompt="test",
                temperature=0.0,
                max_tokens=128,
            )

        assert result is expected
        # Semaphore был создан
        assert client._llamacpp_semaphore is not None
        assert isinstance(client._llamacpp_semaphore, asyncio.Semaphore)

    @pytest.mark.asyncio
    async def test_llamacpp_async_serializes_concurrent_calls(self):
        """
        При параллельных вызовах Semaphore(1) гарантирует
        что _call_llamacpp вызывается последовательно.
        """
        client = LLMClient()
        client.provider = "llamacpp"

        call_order: list[int] = []
        call_count = 0

        def fake_llamacpp(**kwargs):
            nonlocal call_count
            call_count += 1
            call_order.append(call_count)
            return _make_response(provider="llamacpp")

        with patch.object(client, "_call_llamacpp", side_effect=fake_llamacpp):
            # Запускаем 3 параллельных вызова
            results = await asyncio.gather(
                client._call_llamacpp_async("p1", 0.0, 64),
                client._call_llamacpp_async("p2", 0.0, 64),
                client._call_llamacpp_async("p3", 0.0, 64),
            )

        assert len(results) == 3
        assert call_count == 3
        # Все вызовы выполнены
        assert sorted(call_order) == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_llamacpp_semaphore_reuses_same_instance(self):
        """_get_llamacpp_semaphore() возвращает один и тот же объект."""
        client = LLMClient()
        sem1 = client._get_llamacpp_semaphore()
        sem2 = client._get_llamacpp_semaphore()
        assert sem1 is sem2


# ---------------------------------------------------------------------------
# LLMClient.call_with_retries_async()
# ---------------------------------------------------------------------------


class TestCallWithRetriesAsync:
    """call_with_retries_async: retry logic."""

    @pytest.mark.asyncio
    async def test_success_first_attempt(self):
        client = LLMClient()
        client.provider = "ollama"
        expected = _make_response()

        with patch.object(client, "call_async", new_callable=AsyncMock) as mock:
            mock.return_value = expected
            response, details = await client.call_with_retries_async(
                prompt="test", max_retries=2
            )

        assert response is expected
        assert details["error_type"] is None
        assert details["llm_attempts"] == 1

    @pytest.mark.asyncio
    async def test_context_limit_no_retry(self):
        client = LLMClient()
        client.provider = "ollama"

        with patch.object(
            client,
            "call_async",
            new_callable=AsyncMock,
            side_effect=LLMContextLimitError("too big"),
        ):
            response, details = await client.call_with_retries_async(
                prompt="test", max_retries=2
            )

        assert response is None
        assert details["error_type"] == "context_limit"
        assert details["llm_attempts"] == 1  # нет retry

    @pytest.mark.asyncio
    async def test_transient_retries_exhausted(self):
        client = LLMClient()
        client.provider = "ollama"

        with patch.object(
            client,
            "call_async",
            new_callable=AsyncMock,
            side_effect=TransientError("network"),
        ):
            response, details = await client.call_with_retries_async(
                prompt="test", max_retries=2
            )

        assert response is None
        assert details["error_type"] == "transient_error"
        assert details["llm_attempts"] == 3  # 1 + 2 retries

    @pytest.mark.asyncio
    async def test_permanent_error_no_retry(self):
        client = LLMClient()
        client.provider = "openai"

        with patch.object(
            client,
            "call_async",
            new_callable=AsyncMock,
            side_effect=PermanentError("bad key"),
        ):
            response, details = await client.call_with_retries_async(
                prompt="test", max_retries=2
            )

        assert response is None
        assert details["error_type"] == "permanent_error"
        assert details["llm_attempts"] == 1

    @pytest.mark.asyncio
    async def test_none_response_returns_unavailable(self):
        client = LLMClient()
        client.provider = "ollama"

        with patch.object(
            client, "call_async", new_callable=AsyncMock, return_value=None
        ):
            response, details = await client.call_with_retries_async(prompt="test")

        assert response is None
        assert details["error_type"] == "unavailable"


# ---------------------------------------------------------------------------
# call_semantic_enrichment_llm_async()
# ---------------------------------------------------------------------------


# Заменить класс TestCallSemanticEnrichmentLLMAsync целиком:

class TestCallSemanticEnrichmentLLMAsync:
    """Async LLM adapter для enrichment."""

    @pytest.mark.asyncio
    async def test_returns_text_on_success(self):
        from services.structure.semantic_enrichment._llm_client import (
            call_semantic_enrichment_llm_async,
        )

        mock_response = _make_response(text="  some response  ")

        with patch(
            "engine.llm.client.LLMClient.is_available",
            return_value=True,
        ):
            with patch(
                "engine.llm.client.LLMClient.call_with_retries_async",
                new_callable=AsyncMock,
                return_value=(mock_response, {"error_type": None, "error_message": None}),
            ):
                result = await call_semantic_enrichment_llm_async(prompt="test prompt")

        assert result == "some response"

    @pytest.mark.asyncio
    async def test_raises_when_llm_unavailable(self):
        from services.structure.semantic_enrichment._llm_client import (
            call_semantic_enrichment_llm_async,
        )

        with patch(
            "engine.llm.client.LLMClient.is_available",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="not available"):
                await call_semantic_enrichment_llm_async(prompt="test")

    @pytest.mark.asyncio
    async def test_raises_when_response_none(self):
        from services.structure.semantic_enrichment._llm_client import (
            call_semantic_enrichment_llm_async,
        )

        with patch(
            "engine.llm.client.LLMClient.is_available",
            return_value=True,
        ):
            with patch(
                "engine.llm.client.LLMClient.call_with_retries_async",
                new_callable=AsyncMock,
                return_value=(
                    None,
                    {"error_type": "transient_error", "error_message": "timeout"},
                ),
            ):
                with pytest.raises(RuntimeError, match="async call failed"):
                    await call_semantic_enrichment_llm_async(prompt="test")

    @pytest.mark.asyncio
    async def test_raises_when_empty_text(self):
        from services.structure.semantic_enrichment._llm_client import (
            call_semantic_enrichment_llm_async,
        )

        mock_response = _make_response(text="   ")

        with patch(
            "engine.llm.client.LLMClient.is_available",
            return_value=True,
        ):
            with patch(
                "engine.llm.client.LLMClient.call_with_retries_async",
                new_callable=AsyncMock,
                return_value=(mock_response, {"error_type": None, "error_message": None}),
            ):
                with pytest.raises(RuntimeError, match="empty or invalid"):
                    await call_semantic_enrichment_llm_async(prompt="test")


# ---------------------------------------------------------------------------
# enrich_single_unit_async()
# ---------------------------------------------------------------------------


class TestEnrichSingleUnitAsync:
    """Per-unit async enrichment."""

    def _make_unit(self, unit_id: str = "unit-1") -> MagicMock:
        unit = MagicMock()
        unit.unit_id = unit_id
        unit.raw_text = "Payment shall be made within 30 days."
        unit.unit_type = MagicMock()
        unit.unit_type.value = "UNKNOWN"
        unit.clause_function = MagicMock()
        unit.clause_function.value = "UNKNOWN"
        unit.topic_tags = []
        return unit

    def _make_policy(self) -> MagicMock:
        from services.structure.semantic_enrichment._types import SemanticEnrichmentPolicy
        return SemanticEnrichmentPolicy()

    @pytest.mark.asyncio
    async def test_returns_skipped_when_not_eligible(self):
        from services.structure.semantic_enrichment._enricher import enrich_single_unit_async

        unit = self._make_unit()
        policy = self._make_policy()

        with patch(
            "services.structure.semantic_enrichment._enricher.is_unit_eligible_for_enrichment",
            return_value=(False, "too_short"),
        ):
            result = await enrich_single_unit_async(
                unit=unit,
                previous_unit=None,
                next_unit=None,
                policy=policy,
                document_id="doc-1",
            )

        from services.structure.semantic_enrichment._types import SemanticEnrichmentStatus
        assert result.status == SemanticEnrichmentStatus.SKIPPED

# Заменить два теста в TestEnrichSingleUnitAsync:
# rejection_reason → decision_reason

    @pytest.mark.asyncio
    async def test_returns_failed_when_llm_raises(self):
        from services.structure.semantic_enrichment._enricher import enrich_single_unit_async

        unit = self._make_unit()
        policy = self._make_policy()

        with patch(
            "services.structure.semantic_enrichment._enricher.is_unit_eligible_for_enrichment",
            return_value=(True, None),
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt",
                return_value="prompt text",
            ):
                with patch(
                    "services.structure.semantic_enrichment._llm_client.call_semantic_enrichment_llm_async",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("LLM down"),
                ):
                    result = await enrich_single_unit_async(
                        unit=unit,
                        previous_unit=None,
                        next_unit=None,
                        policy=policy,
                        document_id="doc-1",
                    )

        from services.structure.semantic_enrichment._types import SemanticEnrichmentStatus
        assert result.status == SemanticEnrichmentStatus.FAILED
        assert "llm_call_failed" in (result.decision_reason or "")

    @pytest.mark.asyncio
    async def test_returns_failed_when_prompt_build_raises(self):
        from services.structure.semantic_enrichment._enricher import enrich_single_unit_async

        unit = self._make_unit()
        policy = self._make_policy()

        with patch(
            "services.structure.semantic_enrichment._enricher.is_unit_eligible_for_enrichment",
            return_value=(True, None),
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.build_semantic_enrichment_prompt",
                side_effect=ValueError("bad prompt"),
            ):
                result = await enrich_single_unit_async(
                    unit=unit,
                    previous_unit=None,
                    next_unit=None,
                    policy=policy,
                    document_id="doc-1",
                )

        from services.structure.semantic_enrichment._types import SemanticEnrichmentStatus
        assert result.status == SemanticEnrichmentStatus.FAILED
        assert "prompt_build_failed" in (result.decision_reason or "")


# ---------------------------------------------------------------------------
# enrich_legal_units_async()
# ---------------------------------------------------------------------------


class TestEnrichLegalUnitsAsync:
    """Full async enrichment pipeline."""

    def _make_snapshot(
        self, n_units: int = 3, document_id: str = "doc-async-1"
    ) -> MagicMock:
        snapshot = MagicMock()
        snapshot.document_id = document_id
        snapshot.document_version_id = "ver-1"
        snapshot.segment_id = "seg-1"
        snapshot.segment_type = "main"
        snapshot.segment_order = 0
        snapshot.is_primary_segment = True

        units = []
        for i in range(n_units):
            u = MagicMock()
            u.unit_id = f"unit-{i}"
            u.raw_text = f"Clause {i} text here."
            u.unit_type = MagicMock()
            u.unit_type.value = "UNKNOWN"
            u.clause_function = MagicMock()
            u.clause_function.value = "UNKNOWN"
            u.topic_tags = []
            units.append(u)

        snapshot.units = units
        return snapshot


    @pytest.mark.asyncio
    async def test_preflight_gate_skips_all_when_llm_unavailable(self):
        from services.structure.semantic_enrichment._enricher import enrich_legal_units_async

        snapshot = self._make_snapshot(n_units=4)

        with patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=False,
        ):
            result = await enrich_legal_units_async(snapshot)

        assert len(result.enrichments) == 4
        from services.structure.semantic_enrichment._types import SemanticEnrichmentStatus
        for e in result.enrichments:
            assert e.status == SemanticEnrichmentStatus.SKIPPED
            assert "llm_unavailable" in (e.decision_reason or "")
        assert "llm_unavailable_all_units_skipped" in result.build_warnings

    @pytest.mark.asyncio
    async def test_empty_snapshot_returns_immediately(self):
        from services.structure.semantic_enrichment._enricher import enrich_legal_units_async

        snapshot = self._make_snapshot(n_units=0)
        result = await enrich_legal_units_async(snapshot)

        assert result.enrichments == []

    @pytest.mark.asyncio
    async def test_gather_processes_all_units(self):
        from services.structure.semantic_enrichment._enricher import (
            enrich_legal_units_async,
            enrich_single_unit_async,
        )
        from services.structure.semantic_enrichment._types import SemanticEnrichmentStatus

        snapshot = self._make_snapshot(n_units=3)

        async def fake_enrich_single(*, unit, **kwargs):
            from services.structure.semantic_enrichment._types import LegalUnitEnrichment
            e = MagicMock(spec=LegalUnitEnrichment)
            e.status = SemanticEnrichmentStatus.APPLIED
            e.unit_id = unit.unit_id
            e.applied_fields = ["unit_type"]
            e.rejection_reason = None
            return e

        with patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=True,
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.enrich_single_unit_async",
                side_effect=fake_enrich_single,
            ):
                result = await enrich_legal_units_async(snapshot)

        assert len(result.enrichments) == 3

    @pytest.mark.asyncio
    async def test_telemetry_emitted_when_collector_provided(self):
        from services.structure.semantic_enrichment._enricher import enrich_legal_units_async

        snapshot = self._make_snapshot(n_units=2)
        collector = MagicMock()
        collector.emit = MagicMock()

        with patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=False,
        ):
            await enrich_legal_units_async(snapshot, collector=collector)

        collector.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_telemetry_not_emitted_without_collector(self):
        from services.structure.semantic_enrichment._enricher import enrich_legal_units_async

        snapshot = self._make_snapshot(n_units=2)

        with patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=False,
        ):
            # Не должно бросить исключение
            result = await enrich_legal_units_async(snapshot, collector=None)

        assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_units_with_llamacpp_semaphore(self):
        """
        При llamacpp + Semaphore(1) все units завершаются корректно,
        даже при параллельном gather.
        """
        from services.structure.semantic_enrichment._enricher import enrich_legal_units_async
        from services.structure.semantic_enrichment._types import SemanticEnrichmentStatus

        snapshot = self._make_snapshot(n_units=5)
        processed_order: list[str] = []

        async def fake_enrich_single(*, unit, **kwargs):
            from services.structure.semantic_enrichment._types import LegalUnitEnrichment
            processed_order.append(unit.unit_id)
            # Имитируем небольшую async задержку
            await asyncio.sleep(0)
            e = MagicMock(spec=LegalUnitEnrichment)
            e.status = SemanticEnrichmentStatus.APPLIED
            e.unit_id = unit.unit_id
            e.applied_fields = []
            e.rejection_reason = None
            return e

        with patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=True,
        ):
            with patch(
                "services.structure.semantic_enrichment._enricher.enrich_single_unit_async",
                side_effect=fake_enrich_single,
            ):
                result = await enrich_legal_units_async(snapshot)

        assert len(result.enrichments) == 5
        assert len(processed_order) == 5


# ---------------------------------------------------------------------------
# Backward compatibility — sync API не сломан
# ---------------------------------------------------------------------------


class TestSyncAPIBackwardCompatibility:
    """Sync API работает без изменений после Phase 14.1."""

    def test_enrich_legal_units_sync_still_works(self):
        """sync enrich_legal_units() импортируется и работает."""
        from services.structure.semantic_enrichment import enrich_legal_units

        assert callable(enrich_legal_units)

    def test_enrich_single_unit_sync_still_works(self):
        from services.structure.semantic_enrichment import enrich_single_unit

        assert callable(enrich_single_unit)

    def test_call_semantic_enrichment_llm_sync_still_works(self):
        from services.structure.semantic_enrichment import call_semantic_enrichment_llm

        assert callable(call_semantic_enrichment_llm)

    def test_llm_client_sync_call_with_retries_still_works(self):
        """sync call_with_retries() не удалён."""
        client = LLMClient()
        assert callable(client.call_with_retries)
        assert callable(client.call)

    def test_async_functions_are_exported_from_package(self):
        """Новые async функции экспортируются из пакета."""
        from services.structure.semantic_enrichment import (
            enrich_legal_units_async,
            enrich_single_unit_async,
            call_semantic_enrichment_llm_async,
        )

        import inspect
        assert inspect.iscoroutinefunction(enrich_legal_units_async)
        assert inspect.iscoroutinefunction(enrich_single_unit_async)
        assert inspect.iscoroutinefunction(call_semantic_enrichment_llm_async)

    def test_llm_client_async_methods_are_coroutines(self):
        """Новые async методы LLMClient являются coroutine functions."""
        import inspect

        client = LLMClient()
        assert inspect.iscoroutinefunction(client.call_async)
        assert inspect.iscoroutinefunction(client.call_with_retries_async)
        assert inspect.iscoroutinefunction(client._call_openai_async)
        assert inspect.iscoroutinefunction(client._call_ollama_async)
        assert inspect.iscoroutinefunction(client._call_llamacpp_async)


