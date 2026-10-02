# src/services/export/core.py

"""
Core orchestrator for analysis results export per deal/Run.

Responsible for:
- Loading dataset from DB (check results, documents, deal metadata, Run/Playbook);
- Aggregating result structures (services.export.aggregator);
- Generating target export files (DD Grid, Summary, Word report, JSON dump);
- Persisting output files via ArtifactStore and returning tracking references (refs).

Important features:
- Agnostic of Celery/FastAPI execution contexts, operates directly over AsyncSession;
- Does not create or update Export records or change Run states;
- Strives for maximum determinism and reproducibility:
  explicitly passes playbook_version, playbook_profile, checks_mode,
  pipeline_strategy, and environment_hash into report templates;
- Evaluates presentation_locale parameters to produce localized report assets.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n.export_translator import normalize_export_locale
from core.logging import get_logger
from db.models.playbook import PlaybookVersion
from db.repositories import (
    DealRepository,
    RunnerRepository,
    RunRepository,
)
from ops.metrics import METRICS
from services.export.dd_grid_v1_excel_builder import build_dd_grid_v1_excel
from services.export.fact_bundle import build_fact_bundle
from services.export.report_builder import build_report_docx
from services.export.summary_builder import build_summary_excel
from services.result_presentation_read_service import (
    apply_presentations_for_read,
)
from storage.artifact_store import ArtifactStore
from storage.exports import ExportSuffix

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Database Data Retrieval
# ---------------------------------------------------------------------------


async def _load_documents_metadata(run_id: str, db: AsyncSession) -> dict[str, dict[str, Any]]:
    """
    Fetch metadata of documents physically processed during the specified run_id.

    This ensures accuracy as export is pinned to the exact document set
    state of the corresponding run rather than the current deal document registry.
    """
    repo = RunnerRepository(db)
    documents = await repo.load_documents_for_run(uuid.UUID(run_id))

    logger.info(
        "Export: loading documents metadata for run",
        extra={
            "run_id": str(run_id),
            "documents_count": len(documents),
        },
    )

    docs: dict[str, dict[str, Any]] = {}
    for document_id, payload in documents.items():
        docs[document_id] = {
            "name": payload.get("name") or "",
            "folder_path": payload.get("folder_path") or "",
            "doc_type": payload.get("doc_type") or "Generic",
            "status": payload.get("status") or "active",
            "classification_level": payload.get("classification_level") or "",
            "classification_confidence": payload.get("classification_confidence") or 0.0,
            "applicable_triggers": payload.get("applicable_triggers") or [],
            "classification_requires_review": bool(
                payload.get("classification_requires_review") or False
            ),
            "language": payload.get("language") or "",
        }

    return docs


async def _load_deal_name(deal_id: str, db: AsyncSession) -> str:
    """
    Retrieve deal name by deal_id.
    Returns deal_id string representation if deal name is not found.
    """
    try:
        repo = DealRepository(db)
        deal = await repo.get_by_id(uuid.UUID(deal_id))
        if deal and deal.name:
            return deal.name
    except Exception:
        # Fallback safeguard to prevent export crash if repositories are unready.
        logger.warning("Failed to retrieve deal name", deal_id=deal_id)

    return deal_id


# ---------------------------------------------------------------------------
# Public Core API: export_core
# ---------------------------------------------------------------------------


async def export_core(
    *,
    run_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    output_locale: str | None = None,
    presentation_locale: str = "en",  # Deprecated
) -> dict[str, Any]:
    """
    Main export process core.

    Executes:
      - pulls dataset from DB,
      - aggregates check results,
      - compiles output formats (grid, summary, report, aggregated JSON),
      - uploads artifacts to ArtifactStore,
      - returns structured summary of references and metrics.

    Important constraints:
      - Does NOT write or update Export database records;
      - Does NOT mutate Run execution statuses;
      - Does NOT depend on Celery or FastAPI dependencies.
    """
    locale = normalize_export_locale(output_locale or presentation_locale)

    logger.info(
        "Export core starting",
        extra={"deal_id": deal_id, "run_id": run_id, "locale": locale},
    )

    store = ArtifactStore()

    # 1. Dataset Retrieval
    logger.info("Loading export dataset", run_id=run_id, deal_id=deal_id)

    # Canonical check_results loader — the same one used by every
    # deal_review.* endpoint. Returns the full row shape (id, origin,
    # display_text, review_status, review_message, needs_manual_review,
    # element_id, bbox, primary_anchor_id, ...) required by the
    # presentation overlay and by the DD-request rules engine.
    #
    # Replaces a local, stale _load_check_results() that only returned a
    # subset of the canonical fields and, crucially, did not include the
    # row `id`. Without the row `id`, apply_presentations_for_read()
    # silently skipped every row, the localized review_status family
    # never made it into the export payload, and no DD requests were
    # triggered in the Word report's Appendix A.
    runner_repo = RunnerRepository(db)
    check_results = await runner_repo.load_check_results_for_run(uuid.UUID(run_id))

    documents = await _load_documents_metadata(run_id, db)
    deal_name = await _load_deal_name(deal_id, db)

    # Apply locale-specific result presentation overlay on top of raw
    # check_results. This mirrors what deal_review.* endpoints do before
    # building reviewer-facing payloads — the same helper is the single
    # source of truth for the localized review_status family.
    #
    # Required here because:
    #   - report_builder._build_dd_requests_for_report uses
    #     should_trigger_dd_request(), which expects the localized
    #     review_status family (clause_missing / clause_partially_defined
    #     / unclear), not the raw DB values (missing_required_cla,
    #     no_issue_detected, pass).
    #   - Without the overlay, no DD requests are triggered and the
    #     Word report's Appendix A renders "no requests".
    check_results = await apply_presentations_for_read(
        session=db,
        check_results=check_results,
        requested_locale=locale,
    )

    # 1.1. Retrieve Run and Playbook details for reproducibility headers
    run_repo = RunRepository(db)
    run_obj = await run_repo.get_by_id(uuid.UUID(run_id))

    playbook_version_str = "1.0.0"
    playbook_profile_str = "M&A Russia DD"
    env_hash_str = ""

    checks_mode_str = ""
    pipeline_strategy_str = ""

    if run_obj is not None:
        env_hash_str = run_obj.environment_hash or ""
        checks_mode_str = getattr(run_obj, "checks_mode", "") or ""
        pipeline_strategy_str = getattr(run_obj, "pipeline_strategy", "") or ""

        try:
            pb_result = await db.execute(
                select(PlaybookVersion).where(PlaybookVersion.id == run_obj.playbook_version_id)
            )
            pb_obj = pb_result.scalar_one_or_none()
        except Exception:
            pb_obj = None

        if pb_obj is not None:
            playbook_version_str = pb_obj.semver or playbook_version_str
            if pb_obj.name:
                playbook_profile_str = pb_obj.name

    # 1.2. Load CheckDefinition metadata for the Excel / report builders.
    #
    # Canonical loader — the same helper used by every deal_review.*
    # endpoint. It merges global playbook checks with doc-type checks
    # from the Run's frozen instruction snapshot (Run.instruction_versions
    # → compiled_payload → DocTypeCheckLoader).
    #
    # Previously this block loaded playbook.checks directly and passed
    # them to the builders. The DD-request rules engine
    # (report_builder._build_dd_requests_for_report) uses checks_by_id
    # to resolve each check's CheckDefinition and skips any check that
    # is not present — so any doc-type check_id (about 31 of 34 here)
    # was silently dropped, and only global checks could ever trigger a
    # DD request.
    #
    # We pass playbook.checks explicitly as required by the loader's
    # contract: load_check_definitions_for_run() builds the base dict
    # from playbook_checks, then merges doc-type checks on top. Passing
    # an empty list would drop global checks from the result.
    from db.repositories.playbook_repo import PlaybookRepository
    from engine.playbook.loader import load_playbook_from_version
    from services.check_definition_loader import load_check_definitions_for_run

    pb_repo = PlaybookRepository(db)
    checks_by_id: dict[str, Any] = {}

    if run_obj and run_obj.playbook_version_id:
        try:
            pb_version = await pb_repo.get_by_id(run_obj.playbook_version_id)
            if pb_version:
                playbook = load_playbook_from_version(pb_version)
                checks_by_id = await load_check_definitions_for_run(
                    session=db,
                    run=run_obj,
                    playbook_checks=playbook.checks,
                )
                logger.info(
                    "Loaded CheckDefinitions for export",
                    run_id=run_id,
                    checks_count=len(checks_by_id),
                    global_count=len(playbook.checks),
                )
        except Exception as e:
            logger.warning(
                "Failed to load CheckDefinitions for export",
                run_id=run_id,
                error=str(e),
            )

    logger.info(
        "Export dataset loaded successfully",
        run_id=run_id,
        check_results=len(check_results),
        documents=len(documents),
    )

    aggregated = None

    refs: dict[str, str | None] = {
        "dd_grid": None,
        "summary": None,
        "report": None,
        "json": None,
    }

    # 3. DD Grid Excel compilation via DDGridV1Data mapper
    try:
        from classifiers.yaml_registry import YAMLRegistry
        from db.repositories.run_check_plan_item_repo import RunCheckPlanItemRepository
        from services.dd_grid_v1_builder import build_dd_grid_v1

        # RunnerRepository comes from the module-level import — no need
        # to re-import it locally, and the local import shadowed the
        # module-level name, breaking the earlier call in this function.
        runner_repo = RunnerRepository(db)
        plan_item_repo = RunCheckPlanItemRepository(db)

        check_results_for_grid = await runner_repo.load_check_results_for_run(uuid.UUID(run_id))
        documents_for_grid = await runner_repo.load_documents_for_run(uuid.UUID(run_id))
        plan_items = await plan_item_repo.list_by_run_id(uuid.UUID(run_id))

        registry = YAMLRegistry.get_instance()

        grid_data = build_dd_grid_v1(
            checks=list(checks_by_id.values()),
            check_results=check_results_for_grid,
            documents=documents_for_grid,
            registry=registry,
            plan_items=plan_items,
            checks_mode=checks_mode_str,
        )

        grid_bytes = build_dd_grid_v1_excel(
            grid_data=grid_data,
            check_results=check_results_for_grid,
            documents=documents_for_grid,
            checks_by_id=checks_by_id,
            deal_name=deal_name,
            run_id=run_id,
            checks_mode=checks_mode_str,
            pipeline_strategy=pipeline_strategy_str,
            locale=locale,
        )

        refs["dd_grid"] = store.save_export_artifact(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            suffix=ExportSuffix.DD_GRID,
            data=grid_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        METRICS.export_duration.labels(export_type="grid_xlsx").observe(0.0)
        logger.info("DD Grid V1 Excel saved successfully", ref=refs["dd_grid"], locale=locale)
    except Exception as e:  # noqa: BLE001
        logger.error("Error generating DD Grid V1 Excel", error=str(e), exc_info=True)
        refs["dd_grid"] = None

    # 4. Summary Excel compilation via direct checking
    try:
        summary_bytes = build_summary_excel(
            check_results=check_results,
            documents=documents,
            checks_by_id=checks_by_id,
            deal_name=deal_name,
            checks_mode=checks_mode_str,
            pipeline_strategy=pipeline_strategy_str,
            locale=locale,
        )
        refs["summary"] = store.save_export_artifact(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            suffix=ExportSuffix.DEAL_SUMMARY,
            data=summary_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        METRICS.export_duration.labels(export_type="summary_xlsx").observe(0.0)
        logger.info("Summary Excel V1 saved successfully", ref=refs["summary"])
    except Exception as e:  # noqa: BLE001
        logger.error("Error generating Summary Excel V1", error=str(e), exc_info=True)
        refs["summary"] = None

    # 5. Word report compilation via direct check_results evaluation
    try:
        # 5.0. Build fact_bundle — единый контракт данных для report_builder
        #      и LLM-нарративов. Переиспользует overlay'd check_results
        #      (см. шаг 1.1), documents (шаг 1) и checks_by_id (шаг 1.2).
        #
        #      fact_bundle строится здесь, а не внутри report_builder,
        #      потому что:
        #      - позже его же можно передать в llm_narratives.py (Этап 2);
        #      - можно залогировать его объём для observability;
        #      - report_builder останется чистым рендерером.
        from datetime import datetime, timezone

        fact_bundle = build_fact_bundle(
            check_results=check_results,
            documents=documents,
            checks_by_id=checks_by_id,
            deal_name=deal_name,
            run_id=run_id,
            playbook_version=playbook_version_str,
            playbook_profile=playbook_profile_str,
            checks_mode=checks_mode_str,
            pipeline_strategy=pipeline_strategy_str,
            environment_hash=env_hash_str,
            locale=locale,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # 5.0.1. LLM narratives (Purpose of Report).
        #
        #      Генерируем нарративы ПОСЛЕ build_fact_bundle (он нужен как
        #      source of truth), но ДО build_report_docx_v2 (он их рендерит).
        #
        #      Fallback: если LLM недоступна или упала — generate_report_narratives
        #      сам вернёт детерминированные шаблоны. Никаких исключений наружу.
        narratives: dict[str, str] = {}
        try:
            from services.export.llm_narratives import (
                generate_report_narratives,
            )

            narratives = await generate_report_narratives(
                fact_bundle, locale=locale
            )
            logger.info(
                "LLM narratives generated",
                extra={
                    "run_id": run_id,
                    "deal_id": deal_id,
                    "narrative_keys": list(narratives.keys()),
                },
            )
        except Exception as narr_exc:  # noqa: BLE001
            logger.warning(
                "LLM narratives generation failed, using fallbacks",
                extra={"run_id": run_id, "error": str(narr_exc)},
            )

        logger.info(
            "FactBundle built for Word report",
            extra={
                "run_id": run_id,
                "deal_id": deal_id,
                "totals": fact_bundle.totals,
                "global_checks_count": len(fact_bundle.global_checks.by_check),
                "doc_type_groups_count": len(fact_bundle.doc_type_checks.by_doc_type),
                "requests_count": len(fact_bundle.requests),
                "extracted_values_count": len(fact_bundle.extracted_values),
            },
        )

        # 5.1. Word report rendering.
        #
        #      Используем новый v2 path (report_sections_v2.build_report_docx_v2),
        #      который собирает Big4-структуру из FactBundle:
        #      Definitions / Purpose / Terms / Key Findings / Detailed Report /
        #      Extracted Values / Appendix A/B/C.
        #
        #      Fallback: если v2 падает — откатываемся на v1 (build_report_docx),
        #      чтобы не терять функциональность.
        report_bytes: bytes
        try:
            from services.export.report_sections_v2 import build_report_docx_v2

            report_bytes = build_report_docx_v2(
                fact_bundle=fact_bundle,
                narratives=narratives,   # ← было None
                style="corporate_blue",
            )
            logger.info(
                "DD Report v2 built successfully",
                run_id=run_id,
                deal_id=deal_id,
                size_bytes=len(report_bytes),
            )
        except Exception as v2_exc:  # noqa: BLE001
            logger.error(
                "DD Report v2 failed, falling back to v1",
                run_id=run_id,
                deal_id=deal_id,
                error=str(v2_exc),
                exc_info=True,
            )
            # Fallback на v1
            report_bytes = build_report_docx(
                check_results=check_results,
                documents=documents,
                checks_by_id=checks_by_id,
                deal_name=deal_name,
                run_id=run_id,
                playbook_version=playbook_version_str,
                playbook_profile=playbook_profile_str,
                environment_hash=env_hash_str,
                checks_mode=checks_mode_str,
                pipeline_strategy=pipeline_strategy_str,
                locale=locale,
            )
        refs["report"] = store.save_export_artifact(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            suffix=ExportSuffix.REPORT,
            data=report_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        METRICS.export_duration.labels(export_type="report_docx").observe(0.0)
        logger.info("Word Report V1 saved successfully", ref=refs["report"])
    except Exception as e:  # noqa: BLE001
        logger.error("Error generating Word Report V1", error=str(e), exc_info=True)
        refs["report"] = None

    # 6. JSON dump compilation
    try:
        json_payload = {
            "deal_id": deal_id,
            "deal_name": deal_name,
            "run_id": run_id,
            "playbook_version": playbook_version_str,
            "playbook_profile": playbook_profile_str,
            "checks_mode": checks_mode_str,
            "pipeline_strategy": pipeline_strategy_str,
            "environment_hash": env_hash_str,
            "total_documents": len(documents),
            "total_checks": len(check_results),
            "check_results_count": len(check_results),
        }
        json_bytes = json.dumps(
            json_payload,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        refs["json"] = store.save_export_artifact(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            suffix=ExportSuffix.AGGREGATED,
            data=json_bytes,
            content_type="application/json",
        )
        METRICS.export_duration.labels(export_type="aggregated_json").observe(0.0)
        logger.info("JSON dump V1 saved successfully", ref=refs["json"])
    except Exception as e:  # noqa: BLE001
        logger.error("Error generating JSON dump V1", error=str(e), exc_info=True)
        refs["json"] = None

    export_ref = refs.get("dd_grid")

    logger.info(
        "Export core completed",
        extra={"deal_id": deal_id, "run_id": run_id, "locale": locale},
    )

    return {
        "run_id": run_id,
        "deal_id": deal_id,
        "rows": len(check_results),
        "top_risks": len(getattr(aggregated, "top_risks", [])) if aggregated else 0,
        "dd_requests": len(getattr(aggregated, "dd_requests", [])) if aggregated else 0,
        "severity": getattr(aggregated, "severity_counts", {}),
        "export_ref": export_ref,
        "refs": {k: v for k, v in refs.items() if v is not None},
        "all_refs": refs,
    }


