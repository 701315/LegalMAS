# src/services/semantic_enrichment/__init__.py

"""
Semantic Enrichment — LLM-based обогащение semantic metadata поверх LegalUnit.

Этот пакет реализует Phase 12 архитектурного плана:
Deterministic Core → Probabilistic Assistance → Semantic Intelligence.

Что делает этот пакет:
- Принимает LegalUnitsSnapshot (deterministic baseline от LegalUnitBuilder).
- Для каждого eligible LegalUnit строит prompt с богатым контекстом.
- Вызывает локальную LLM (Ollama/llama.cpp) для semantic classification.
- Валидирует и нормализует ответ LLM.
- Применяет conservative merge-policy (fill missing, add-only topics).
- Возвращает sidecar artifact (LegalUnitsEnrichmentResult),
  который НЕ заменяет deterministic snapshot, а дополняет его.

Архитектурная роль:
- Postbuild-layer поверх LegalUnitBuilder (аналогично Phase 8/9).
- Не меняет clause tree, hierarchy, chunk IDs, citability.
- Failure-isolated: если LLM недоступна или вернула мусор,
  deterministic baseline сохраняется без изменений.

Phase 14.1 — Async API:
- enrich_legal_units_async() — async версия с asyncio.gather().
- enrich_single_unit_async() — async версия per-unit orchestrator.
- call_semantic_enrichment_llm_async() — async LLM call adapter.
  llamacpp: run_in_executor + Semaphore(1), не блокирует event loop.
  ollama/openai: httpx.AsyncClient, реальный параллелизм.

Downstream consumer:
- EvidenceBundleBuilder использует enriched topic_tags и unit_type
  для более точного retrieval при risk analysis.

Основные компоненты:
- _types.py       — data contracts (proposals, enrichments, sidecar result)
- _policy.py      — conservative merge-policy (fill/add/reject/override)
- _prompting.py   — prompt construction с hierarchy context
- _validator.py   — safe JSON parsing LLM response
- _llm_client.py  — LLM client adapter (sync + async)
- _enricher.py    — per-unit orchestrator (sync + async)
- projection.py   — построение effective enriched units для downstream
"""

from services.structure.semantic_enrichment._enricher import (
    enrich_legal_units,
    enrich_legal_units_async,
    enrich_single_unit,
    enrich_single_unit_async,
)
from services.structure.semantic_enrichment._llm_client import (
    call_semantic_enrichment_llm,
    call_semantic_enrichment_llm_async,
    is_semantic_enrichment_llm_available,
)
from services.structure.semantic_enrichment._policy import (
    apply_enrichment_policy,
    build_failed_enrichment,
    build_skipped_enrichment,
    explain_unit_enrichment_eligibility,
    is_unit_eligible_for_enrichment,
    make_policy_from_settings,
)
from services.structure.semantic_enrichment._prompting import (
    PROMPT_VERSION,
    SemanticEnrichmentPromptContext,
    build_semantic_enrichment_prompt,
    build_semantic_enrichment_prompt_context,
)
from services.structure.semantic_enrichment._types import (
    LLMEnrichmentProposal,
    LegalUnitEnrichment,
    LegalUnitsEnrichmentResult,
    SemanticEnrichmentPolicy,
    SemanticEnrichmentStatus,
)
from services.structure.semantic_enrichment._validator import parse_llm_enrichment_response
from services.structure.semantic_enrichment.projection import (
    project_enriched_units,
    project_single_unit,
)

__all__ = [
    # Prompt
    "PROMPT_VERSION",
    "SemanticEnrichmentPromptContext",
    "build_semantic_enrichment_prompt_context",
    # Types
    "LLMEnrichmentProposal",
    "LegalUnitEnrichment",
    "LegalUnitsEnrichmentResult",
    "SemanticEnrichmentPolicy",
    "SemanticEnrichmentStatus",
    # Policy
    "apply_enrichment_policy",
    "build_failed_enrichment",
    "build_skipped_enrichment",
    "build_semantic_enrichment_prompt",
    "explain_unit_enrichment_eligibility",
    "is_unit_eligible_for_enrichment",
    "make_policy_from_settings",
    # LLM client — sync
    "call_semantic_enrichment_llm",
    "is_semantic_enrichment_llm_available",
    # LLM client — async (Phase 14.1)
    "call_semantic_enrichment_llm_async",
    # Enricher — sync
    "enrich_legal_units",
    "enrich_single_unit",
    # Enricher — async (Phase 14.1)
    "enrich_legal_units_async",
    "enrich_single_unit_async",
    # Validator
    "parse_llm_enrichment_response",
    # Projection
    "project_enriched_units",
    "project_single_unit",
]


