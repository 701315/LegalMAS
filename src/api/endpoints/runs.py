# src/api/endpoints/runs.py

"""
Endpoints for analysis runs (runs).

Core routes:
- POST /runs                               — start analysis run for a deal
- GET  /runs/{run_id}                      — run status + (optional) classification stats
- GET  /runs/{run_id}/classification-report — detailed classification quality report
- GET  /runs/{run_id}/events               — SSE stream of Run progress (status + completed/total)
"""

from __future__ import annotations

import json
import uuid
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import get_scoped_deal, get_scoped_run, require_project_role
from api.schemas.instruction_overrides import RunInstructionSnapshotResponse
from api.schemas.instructions import EffectiveInstructionResponse
from api.schemas.pagination import PaginatedResponse as PaginatedResponseSchema
from api.schemas.results import CheckResultResponse
from api.schemas.run_check_plan import RunCheckPlanItemResponse, RunCheckPlanResponse
from api.schemas.runs import (
    ClassificationReportResponse,
    DealRunSummaryResponse,
    RunCreate,
    RunPipelineProgressResponse,
    RunResponse,
)
from core.config import settings
from core.constants import LanguageDiscoveryStatus, RunCheckPlanItemStatus, RunStatus
from core.error_catalog import render_error_message
from core.logging import get_logger
from db.models.deal import Deal
from db.models.run import Run
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.export_repo import ExportRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.result_repo import ResultRepository
from db.repositories.run_check_plan_item_repo import RunCheckPlanItemRepository
from db.repositories.run_repo import RunRepository
from db.session import get_db
from engine.checks.snapshot_policy import check_snapshot_integrity
from mas_queue.task_dispatcher import send_task_with_context
from services.effective_instruction_service import (
    EffectiveInstructionNotFoundError,
    EffectiveInstructionService,
)
from services.run_analytics_service import RunAnalyticsService, RunNotFoundError
from services.run_pipeline_progress_service import RunPipelineProgressService
from services.run_progress_service import subscribe_run_progress

logger = get_logger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


async def _start_run_core(
    deal_uuid: uuid.UUID,
    data: RunCreate,
    db: AsyncSession,
    user: CurrentUser,
) -> RunResponse:
    """
    Common logic for starting a deal analysis run.

    Pipeline sequence:
    1) Validate deal existence;
    2) Retrieve the playbook for this deal (or fallback to default);
    3) Fetch model_config_id from the playbook;
    4) Instantiate a new Run linked to these IDs;
    5) Update the last_run_id attribute on the Deal model;
    6) Dispatch a single orchestration Celery task: start_run_pipeline(run_id),
       which dynamically evaluates documents and handles pipeline stages
       (extract → pii → structure → classify → run_deal_checks).
    """
    run_repo = RunRepository(db)
    deal_repo = DealRepository(db)
    playbook_repo = PlaybookRepository(db)
    audit_repo = AuditRepository(db)

    # 1. Validate deal existence within user's tenant scope
    deal = await deal_repo.get_by_id(
        deal_uuid,
        tenant_id=user.tenant_id,
    )
    if not deal:
        raise HTTPException(
            status_code=404,
            headers={"X-Error-Code": "DEAL_NOT_FOUND"},
            detail="Deal not found",
        )

    # 1.1. Deal primary language must be selected beforehand to start analysis.
    #
    # System architectural rule:
    # - Run pre-run language discovery first;
    # - Let user select the primary_language of the deal;
    # - Start Run only after selection is made.
    #
    # Hence, the backend strictly rejects run start if primary_language is missing.
    if not getattr(deal, "primary_language", None):
        logger.warning(
            "Run start rejected: primary_language is not set",
            extra={
                "deal_id": str(deal_uuid),
                "tenant_id": str(getattr(deal, "tenant_id", "")),
                "requested_by": (
                    str(getattr(user, "id", None)) if getattr(user, "id", None) else "unknown"
                ),
            },
        )
        raise HTTPException(
            status_code=400,
            headers={"X-Error-Code": "PRIMARY_LANGUAGE_NOT_SET"},
            detail="Primary language must be selected before starting analysis",
        )

    # 1.2. Analysis start is forbidden while language discovery is still active.
    # This acts as a backend safeguard against UI race conditions or direct API calls.
    if getattr(deal, "language_discovery_status", None) == LanguageDiscoveryStatus.PROCESSING:
        logger.warning(
            "Run start rejected: language discovery is still in progress",
            extra={
                "deal_id": str(deal_uuid),
                "tenant_id": str(getattr(deal, "tenant_id", "")),
                "requested_by": (
                    str(getattr(user, "id", None)) if getattr(user, "id", None) else "unknown"
                ),
                "language_discovery_status": getattr(deal, "language_discovery_status", None),
            },
        )
        raise HTTPException(
            status_code=400,
            headers={"X-Error-Code": "LANGUAGE_DISCOVERY_IN_PROGRESS"},
            detail=(
                "Language discovery is still in progress. "
                "Please wait until it completes before starting analysis."
            ),
        )

    # 2. Fetch the playbook for the deal (assigned playbook or fallback)
    playbook = await playbook_repo.get_for_deal(deal_uuid)
    if not playbook:
        raise HTTPException(
            status_code=400,
            headers={"X-Error-Code": "DEAL_PLAYBOOK_NOT_CONFIGURED"},
            detail="Deal is not configured with a playbook",
        )

    # 3. Ensure the playbook has model_config attached
    if not playbook.model_config_id:
        raise HTTPException(
            status_code=400,
            headers={"X-Error-Code": "PLAYBOOK_MODEL_CONFIG_NOT_CONFIGURED"},
            detail="Playbook is not configured with model_config",
        )

    playbook_version_id = playbook.id
    model_config_id = playbook.model_config_id

    # 4. Determine pipeline strategy and instantiate run.
    #
    # Currently evaluated against:
    # - model (model_config_id) linked to the playbook;
    # - selected playbook_version (playbook_version_id).
    #
    # Execution policy:
    # - If model changed relative to the latest Run: trigger full recompute (FULL_RERUN);
    # - If model remains identical: reuse document structure and re-evaluate checks only (REUSE_STRUCTURE).
    #
    # Future extension: evaluate environment changes via Run.environment_hash
    # and/or config fingerprint once a single configuration registry source is available.
    pipeline_strategy = "REUSE_STRUCTURE"

    last_run = await run_repo.get_latest_for_deal(deal_uuid)
    if last_run:
        same_model = last_run.model_config_id == model_config_id
        # TODO (reproducibility):
        #  - Run.environment_hash is currently almost always None;
        #  - No single configuration fingerprint is currently implemented.
        # Once implemented:
        #  - compute environment_hash (libs, docker, models) and config_fingerprint
        #    to determine if FULL_RERUN or REUSE_STRUCTURE is appropriate.
        if not same_model:
            pipeline_strategy = "FULL_RERUN"
        else:
            pipeline_strategy = "REUSE_STRUCTURE"

    try:
        run = await run_repo.create(
            deal_id=deal_uuid,
            tenant_id=deal.tenant_id,
            playbook_version_id=playbook_version_id,
            model_config_id=model_config_id,
            bundle_id=None,
            profile=data.profile,
            pipeline_strategy=pipeline_strategy,
            checks_mode=data.checks_mode,
        )
    except IntegrityError as exc:
        # R-33: partial unique index uq_runs_one_active_per_deal prevents
        # two concurrent active runs per deal. Return 409 with the id of
        # the already-active run so the client can open it instead of retrying.
        await db.rollback()
        active = await run_repo.get_active_for_deal(deal_uuid)
        headers: dict[str, str] = {"X-Error-Code": "DEAL_ALREADY_HAS_ACTIVE_RUN"}
        if active is not None:
            headers["X-Active-Run-Id"] = str(active.id)
        logger.warning(
            "Run start rejected: active run exists for deal",
            extra={
                "deal_id": str(deal_uuid),
                "tenant_id": str(deal.tenant_id),
                "active_run_id": str(active.id) if active else None,
                "requested_by": getattr(user, "id", None),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            headers=headers,
            detail=(
                "Deal already has an active analysis run. "
                "Wait for it to complete or cancel it before starting a new one."
            ),
        ) from exc

    logger.info(
        "Run created",
        extra={
            "run_id": str(run.id),
            "deal_id": str(deal_uuid),
            "tenant_id": str(deal.tenant_id),
            "playbook_version_id": str(playbook_version_id),
            "model_config_id": str(model_config_id),
            "pipeline_strategy": pipeline_strategy,
            "created_by": getattr(user, "id", None),
        },
    )

    # 5. Update last_run_id and aggregate properties on the Deal model
    await deal_repo.set_last_run_id(
        deal_id=deal_uuid,
        run_id=run.id,
        checks_mode=getattr(run, "checks_mode", None),
        pipeline_strategy=getattr(run, "pipeline_strategy", None),
    )

    # 5.1. Reset pending manual reclassifications flag:
    # Starting a new analysis run supersedes previous manual reclassifications.
    await deal_repo.set_has_pending_manual_reclassifications(
        deal_id=deal_uuid,
        value=False,
    )

    # 6. Persist database state prior to dispatching async tasks
    await db.commit()
    await db.refresh(run)

    # 6.1. Audit trail: Log user-initiated analysis request
    try:
        await audit_repo.log(
            tenant_id=deal.tenant_id,
            deal_id=deal_uuid,
            action="ANALYSIS_REQUESTED",
            actor=str(getattr(user, "id", None)) if getattr(user, "id", None) else "unknown",
            actor_role=getattr(user, "global_role", "user"),
            details={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
                "playbook_version_id": str(playbook_version_id),
                "model_config_id": str(model_config_id),
                "profile": data.profile,
                "checks_mode": data.checks_mode,
                "pipeline_strategy": pipeline_strategy,
                "force_reclassify": bool(
                    data.force_reclassify
                    and getattr(settings, "API_ALLOW_FORCE_RECLASSIFY", False)
                ),
            },
        )
    except Exception as e:
        logger.warning(
            "Failed to write audit log for ANALYSIS_REQUESTED",
            extra={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
                "error": str(e),
            },
        )

    # 7. Dispatch Celery orchestration pipeline task
    try:
        logger.info(
            "Scheduling start_run_pipeline",
            extra={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
                "tenant_id": str(run.tenant_id),
            },
        )

        send_task_with_context(
            "workers.start_run_pipeline",
            kwargs={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
                "tenant_id": str(run.tenant_id),
                "force_reclassify": bool(
                    data.force_reclassify
                    and getattr(settings, "API_ALLOW_FORCE_RECLASSIFY", False)
                ),
            },
        )

    except Exception as e:
        msg = str(e)
        lower_msg = msg.lower()

        # Classify message errors from message broker connection failures
        if any(
            token in lower_msg
            for token in (
                "connection refused",
                "connectionerror",
                "timeout",
                "broker",
                "rabbitmq",
                "redis",
            )
        ):
            reason = "queue_unavailable"
            http_detail = (
                "Failed to start deal analysis: task queue is temporarily unavailable. "
                "Please try again later."
            )
            http_code = "TASK_QUEUE_UNAVAILABLE"
        else:
            reason = "infrastructure_error"
            http_detail = "Failed to start deal analysis: internal infrastructure error."
            http_code = "INFRASTRUCTURE_ERROR"

        await _mark_run_failed_orchestrator(
            run_repo=run_repo,
            run_id=run.id,
            reason=reason,
            message=msg,
        )
        raise HTTPException(
            status_code=503,
            headers={"X-Error-Code": http_code},
            detail=http_detail,
        )

    return RunResponse.model_validate(run)


async def _mark_run_failed_orchestrator(
    run_repo: RunRepository,
    run_id: uuid.UUID,
    *,
    reason: str,
    message: str,
) -> None:
    """
    Mark Run as FAILED in case of broker/orchestrator setup errors.
    """
    await run_repo.update_status(
        run_id,
        RunStatus.FAILED.value,
        error_details={
            "stage": "orchestrator",
            "type": (
                "infrastructure_error"
                if reason in ("infrastructure_error", "queue_unavailable")
                else "config_error"
            ),
            "reason": reason,
            "message": message,
        },
    )


@router.post(
    "",
    response_model=RunResponse,
    summary="Start analysis run for a deal",
)
async def start_run(
    data: RunCreate,
    deal_id: str = Query(..., description="Deal ID to trigger analysis for"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Legacy run initiation endpoint: POST /api/v1/runs?deal_id=...

    Access: Restricted to 'admin' and 'editor' project members only.
    """
    deal_uuid = uuid.UUID(deal_id)

    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_uuid,
        allowed_roles=("admin", "editor"),
    )

    return await _start_run_core(deal_uuid, data, db, user)


@router.get("/deal/{deal_id}", response_model=list[RunResponse])
async def list_runs_for_deal(
    # Tenant verification via scoped dependency
    deal: Deal = Depends(get_scoped_deal),
    include_classification_stats: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    run_repo = RunRepository(db)
    runs = await run_repo.get_by_deal(deal.id)
    result = [RunResponse.model_validate(r) for r in runs]
    if include_classification_stats and runs:
        for i, run_obj in enumerate(runs):
            stats = await run_repo.get_classification_stats_for_run(run_obj.id)
            result[i].classification_stats = stats
    return result


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run: Run = Depends(get_scoped_run),  # Automatic tenant scope isolation
    include_classification_stats: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    run_out = RunResponse.model_validate(run)

    if include_classification_stats:
        stats = await RunRepository(db).get_classification_stats_for_run(run.id)
        run_out.classification_stats = stats

    if getattr(run, "error_details", None):
        run_out.error_user_message = render_error_message(run.error_details)

    return run_out


@router.get("/{run_id}/progress", response_model=RunPipelineProgressResponse)
async def get_run_pipeline_progress(
    run: Run = Depends(get_scoped_run),
    db: AsyncSession = Depends(get_db),
):
    service = RunPipelineProgressService(db)
    return await service.build_progress(run)


@router.get("/{run_id}/events")
async def stream_run_events(
    request: Request,
    run: Run = Depends(get_scoped_run),
    db: AsyncSession = Depends(get_db),
):
    async def event_generator():
        async for event in subscribe_run_progress(run.id):
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def get_run_analytics_service(
    db: AsyncSession = Depends(get_db),
) -> RunAnalyticsService:
    return RunAnalyticsService(db)


def get_effective_instruction_service(
    db: AsyncSession = Depends(get_db),
) -> EffectiveInstructionService:
    return EffectiveInstructionService(db)


@router.get(
    "/{run_id}/documents/{document_id}/effective-instruction",
    response_model=EffectiveInstructionResponse,
    summary="Unified effective instruction (global + doc-type checks) applied to document in this Run",
)
async def get_effective_instruction(
    document_id: uuid.UUID,
    run: Run = Depends(get_scoped_run),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: EffectiveInstructionService = Depends(get_effective_instruction_service),
):
    """
    Return the unified instruction set applied to the specified document in this Run.

    Access: Read-only for any verified project member (admin/editor/viewer).

    is_frozen_snapshot=True indicates doc_type_checks are derived from the
    immutable snapshot captured at Run initialization. False indicates fallback
    to live configuration.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    try:
        result = await service.get_for_document(run_id=run.id, document_id=document_id)
    except EffectiveInstructionNotFoundError as e:
        raise HTTPException(
            status_code=404,
            headers={"X-Error-Code": "EFFECTIVE_INSTRUCTION_NOT_FOUND"},
            detail=str(e),
        )

    return EffectiveInstructionResponse(**result)


@router.get(
    "/{run_id}/classification-report",
    response_model=ClassificationReportResponse,
    summary="Detailed classification quality report for run",
)
async def get_classification_report(
    run: Run = Depends(get_scoped_run),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: RunAnalyticsService = Depends(get_run_analytics_service),
):
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    try:
        return await service.build_classification_report(run.id)
    except RunNotFoundError:
        raise HTTPException(
            status_code=404,
            headers={"X-Error-Code": "CLASSIFICATION_REPORT_NOT_FOUND"},
            detail="Classification report not found",
        )


class RunExportCreate(BaseModel):
    """
    Request body for initiating export results.

    The export type is explicitly supplied. requested_by and requester_role properties
    are resolved server-side from user identity and workspace scopes.
    """

    export_type: Literal[
        "grid_xlsx",
        "deal_summary_xlsx",
        "report_docx",
        "aggregated_json",
    ]

    # Explicit output locale chosen by the user in the UI. Requests,
    # DD Grid and Report tabs share the same locale selector. When
    # omitted, the backend falls back to user.ui_locale and then "en".
    # Exports must honour the user's explicit choice, not the interface
    # language — otherwise switching to English in the UI still
    # produces a Russian report.
    output_locale: str | None = None


class RunExportResponse(BaseModel):
    """
    Short export status response payload for UI wrappers.
    """

    id: uuid.UUID
    run_id: uuid.UUID
    deal_id: uuid.UUID
    export_type: str
    status: str
    file_ref: str | None = None


@router.post(
    "/{run_id}/export",
    response_model=RunExportResponse,
    summary="Start exporting run results",
)
async def start_run_export(
    data: RunExportCreate,
    run: Run = Depends(get_scoped_run),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Triggers run metrics export process.
    Access: Restricted to tenant admin/editor workspace roles.
    """
    export_repo = ExportRepository(db)

    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor"),
    )

    if run.status not in (RunStatus.COMPLETED.value, "completed_with_errors"):
        raise HTTPException(
            status_code=400,
            headers={"X-Error-Code": "RUN_NOT_COMPLETED"},
            detail=f"Run status must be completed to export, got '{run.status}'",
        )

    requested_by = getattr(user, "id", None)
    requester_role = getattr(user, "global_role", "user")

    # Locale resolution priority:
    #   1. explicit output_locale from the request body (set by the UI
    #      locale selector shared across Requests / DD Grid / Report);
    #   2. user.ui_locale as a fallback;
    #   3. "en".
    effective_locale = (
        data.output_locale
        or getattr(user, "ui_locale", None)
        or "en"
    )

    export = await export_repo.create(
        deal_id=run.deal_id,
        run_id=run.id,
        export_type=data.export_type,
        requested_by=requested_by,
        requester_role=requester_role,
        status="pending",
    )

    await db.commit()
    await db.refresh(export)

    try:
        send_task_with_context(
            "workers.export_by_id",
            kwargs={
                "export_id": str(export.id),
                "output_locale": effective_locale,
                "presentation_locale": effective_locale,
            },
            queue="default",
        )

        logger.info(
            "Export task queued",
            extra={
                "export_id": str(export.id),
                "run_id": str(run.id),
                "output_locale": effective_locale,
                "presentation_locale": effective_locale,
            },
        )

    except Exception as e:
        await export_repo.update_status(
            export.id,
            status="failed",
            error_details={"stage": "export", "type": "infrastructure_error", "message": str(e)},
        )
        await db.commit()
        raise HTTPException(
            status_code=503,
            headers={"X-Error-Code": "EXPORT_QUEUE_UNAVAILABLE"},
            detail="Queue unavailable, try again later",
        )

    return RunExportResponse(
        id=export.id,
        run_id=run.id,
        deal_id=run.deal_id,
        export_type=export.export_type,
        status=export.status,
        file_ref=export.file_ref,
    )


@router.get(
    "/{run_id}/results",
    response_model=PaginatedResponseSchema[CheckResultResponse],
    summary="Paginated list of check results for run (DD Grid)",
)
async def list_run_results(
    run_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(200, ge=1, le=1000),
    doc_type: str | None = Query(
        default=None,
        description="Filter checks by document type (doc_type)",
    ),
    severity: str | None = Query(
        default=None,
        description="Filter results by risk severity level: critical/high/medium/pass/unclear",
    ),
    conditional_only: bool | None = Query(
        default=None,
        description="Retrieve only conditional results",
    ),
    has_structured_data: bool | None = Query(
        default=None,
        description="Retrieve only results containing structured_data values",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Check validation results for a run, returned in paginated layout
    suitable for DD Grid components.

    Access requirements:
    - User must be a registered project member (admin/editor/viewer) of the associated deal.
    - Non-associated identities receive 403 Forbidden.
    """
    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(
            status_code=404,
            headers={"X-Error-Code": "RUN_NOT_FOUND"},
            detail="Run not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    result_repo = ResultRepository(db)
    items_raw, total = await result_repo.get_page_for_run(
        run_id=run_id,
        page=page,
        per_page=per_page,
        doc_type=doc_type,
        severity=severity,
        conditional_only=conditional_only,
        has_structured_data=has_structured_data,
    )

    items = [CheckResultResponse.model_validate(r) for r in items_raw]

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    has_next = page < total_pages
    has_previous = page > 1

    return PaginatedResponseSchema[CheckResultResponse](
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=has_next,
        has_previous=has_previous,
    )


@router.get(
    "/deal/{deal_id}/summary",
    response_model=DealRunSummaryResponse,
)
async def get_deal_run_summary(
    deal_id: UUID,
    include_classification_stats: bool = False,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieve concise progress summary metrics of the latest Run associated with a deal.

    Source of truth rules:
    - Deal.last_run_id determines the latest active/historical pipeline state.
    - Security scope permissions verified through require_project_role.
    """
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(
        deal_id,
        tenant_id=user.tenant_id,
    )

    if not deal or not deal.last_run_id:
        raise HTTPException(
            status_code=404,
            headers={"X-Error-Code": "RUN_NOT_FOUND_FOR_DEAL"},
            detail="Run not found for this deal",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=deal.id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(deal.last_run_id)
    if not run:
        raise HTTPException(
            status_code=404,
            headers={"X-Error-Code": "RUN_NOT_FOUND_FOR_DEAL"},
            detail="Run not found for this deal",
        )

    classification_stats = None
    if include_classification_stats:
        classification_stats = await run_repo.get_classification_stats_for_run(run.id)

    error_user_message = None
    if getattr(run, "error_details", None):
        error_user_message = render_error_message(run.error_details)

    return DealRunSummaryResponse(
        deal_id=run.deal_id,
        run_id=run.id,
        status=run.status,
        profile=run.profile,
        checks_mode=getattr(run, "checks_mode", "global_and_doc_type"),
        pipeline_strategy=getattr(run, "pipeline_strategy", "REUSE_STRUCTURE"),
        total_checks=run.total_checks,
        completed_checks=run.completed_checks,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_details=run.error_details,
        error_user_message=error_user_message,
        classification_stats=classification_stats,
    )


@router.get(
    "/{run_id}/instruction-snapshot",
    response_model=RunInstructionSnapshotResponse,
    summary="Frozen instruction snapshot for historical Run",
)
async def get_run_instruction_snapshot(
    run: Run = Depends(get_scoped_run),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> RunInstructionSnapshotResponse:
    """
    Return frozen instruction snapshot configuration metrics for Run.

    Includes:
    - Exact instruction versions recorded at Run initialization;
    - Snapshot checksum manifest data;
    - Pipeline execution details;
    - is_reproducible flag indicating snapshot payload integrity.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    snapshot_schema_version = getattr(run, "snapshot_schema_version", None)
    instruction_versions = getattr(run, "instruction_versions", None) or {}
    instruction_snapshot_manifest = getattr(run, "instruction_snapshot_manifest", None)
    execution_manifest = getattr(run, "execution_manifest", None)

    is_valid, warning = check_snapshot_integrity(
        run_id=str(run.id),
        snapshot_schema_version=snapshot_schema_version,
        instruction_snapshot_payload=getattr(run, "instruction_snapshot_payload", None),
    )

    is_reproducible = (snapshot_schema_version is not None and is_valid)

    return RunInstructionSnapshotResponse(
        run_id=str(run.id),
        deal_id=str(run.deal_id),
        snapshot_schema_version=snapshot_schema_version,
        is_reproducible=is_reproducible,
        instruction_versions=instruction_versions,
        instruction_snapshot_manifest=instruction_snapshot_manifest,
        execution_manifest=execution_manifest,
        doc_types_count=len(instruction_versions),
        warning=warning,
    )


@router.get(
    "/{run_id}/check-plan",
    response_model=RunCheckPlanResponse,
    summary="Checks execution ledger for Run (check-plan)",
)
async def get_run_check_plan(
    run: Run = Depends(get_scoped_run),
    status: RunCheckPlanItemStatus | None = Query(
        default=None,
        description=(
            "Filter ledger items by status. Summary totals "
            "always represent absolute progress metrics regardless of filtering."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> RunCheckPlanResponse:
    """
    Return the execution plan details (source of truth progress metrics) for a Run.

    Items filtered by state properties (if supplied). Summary statistics are absolute.
    Access: Read-only for authorized project members.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    repo = RunCheckPlanItemRepository(db)
    items = await repo.list_by_run_id(run.id, status=status)
    stats = await repo.get_run_progress_stats(run.id)

    return RunCheckPlanResponse(
        run_id=run.id,
        items=[RunCheckPlanItemResponse.model_validate(i) for i in items],
        summary=stats,
    )


@router.get(
    "/{run_id}/check-plan/{plan_item_id}",
    response_model=RunCheckPlanItemResponse,
    summary="Single execution ledger item by ID",
)
async def get_run_check_plan_item(
    plan_item_id: uuid.UUID,
    run: Run = Depends(get_scoped_run),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> RunCheckPlanItemResponse:
    """
    Return a single check plan item, scoped by run_id (safeguarding against cross-run leaks).
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    repo = RunCheckPlanItemRepository(db)
    item = await repo.get_by_id_scoped(plan_item_id, run.id)
    if not item:
        raise HTTPException(
            status_code=404,
            headers={"X-Error-Code": "CHECK_PLAN_ITEM_NOT_FOUND"},
            detail="Check plan item not found",
        )

    return RunCheckPlanItemResponse.model_validate(item)


