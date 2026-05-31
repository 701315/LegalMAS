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

Downstream consumer:
- EvidenceBundleBuilder использует enriched topic_tags и unit_type
  для более точного retrieval при risk analysis.

Основные компоненты:
- _types.py       — data contracts (proposals, enrichments, sidecar result)
- _policy.py      — conservative merge-policy (fill/add/reject/override)
- _prompting.py   — prompt construction с hierarchy context
- _validator.py   — safe JSON parsing LLM response
- _llm_client.py  — Ollama-compatible HTTP client с retry
- _enricher.py    — per-unit orchestrator
- projection.py   — построение effective enriched units для downstream
"""

from services.structure.semantic_enrichment._enricher import (
    enrich_legal_units,
    enrich_single_unit,
)
from services.structure.semantic_enrichment._llm_client import (
    call_semantic_enrichment_llm,
    is_semantic_enrichment_llm_available,
)
from services.structure.semantic_enrichment._policy import (
    apply_enrichment_policy,
    build_failed_enrichment,
    build_skipped_enrichment,
    is_unit_eligible_for_enrichment,
    make_policy_from_settings,
)
from services.structure.semantic_enrichment._prompting import (
    PROMPT_VERSION,
    build_semantic_enrichment_prompt,
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
    "PROMPT_VERSION",
    "LLMEnrichmentProposal",
    "LegalUnitEnrichment",
    "LegalUnitsEnrichmentResult",
    "SemanticEnrichmentPolicy",
    "SemanticEnrichmentStatus",
    "apply_enrichment_policy",
    "build_failed_enrichment",
    "build_skipped_enrichment",
    "build_semantic_enrichment_prompt",
    "call_semantic_enrichment_llm",
    "enrich_legal_units",
    "enrich_single_unit",
    "is_unit_eligible_for_enrichment",
    "parse_llm_enrichment_response",
    "project_enriched_units",
    "project_single_unit",
    "is_semantic_enrichment_llm_available",
    "make_policy_from_settings",
]



