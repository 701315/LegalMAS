# src/api/endpoints/deal_review.py

"""
FastAPI endpoints for UI deal review.

All endpoints require the user to have a viewer/editor/admin project role.
Data is compiled by querying check_results directly from the database.

Routes:
  GET /{deal_id}/runs/{run_id}/documents
      List of documents with risk counters.

  GET /{deal_id}/runs/{run_id}/documents/{document_id}
      Detailed document card with all checks.

  GET /{deal_id}/runs/{run_id}/documents/{document_id}/structured-data
      Structured values extracted for a single document.

  GET /{deal_id}/runs/{run_id}/dd-requests
      DD requests compiled from run results.

  GET /{deal_id}/runs/{run_id}/conditional-checks
      Triggered conditional checks.

  GET /{deal_id}/runs/{run_id}/extracted-values
      All extracted structured values.

  GET /{deal_id}/runs/{run_id}/dd-matrix
      Matrix representation of DD Grid (documents x checks).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.models.run import Run
from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.audit_repo import AuditRepository
from db.repositories.run_repo import RunRepository
from db.session import get_db
from services.deal_review_service import (
    build_conditional_checks,
    build_dd_grid_v1_response,
    build_dd_matrix,
    build_dd_requests,
    build_extracted_values,
)
from services.result_presentation_read_service import (
    apply_presentations_for_read,
    resolve_output_locale,
    resolve_presentation_locale,  # Deprecated alias, kept for transition
)
from services.check_definition_loader import (
    load_check_definitions_for_run,
)
from services.result_presentation_request_service import (
    ResultPresentationProgress,
    ResultPresentationRequestService,
)
from services.outbox_service import OutboxService
from ..schemas.deal_review import (
    CheckItemDTO,
    ConditionalCheckDTO,
    DDGridV1ResponseDTO,
    DDMatrixResponseDTO,
    DDRequestDTO,
    DocumentDetailDTO,
    DocumentStructuredDataDTO,
    DocumentSummaryDTO,
    ExtractedValueDTO,
    ResultPresentationProgressDTO,
    ResultPresentationRequestDTO,
)

from db.models.deal import Deal
from ops.metrics import get_metrics

router = APIRouter(prefix="/deals", tags=["deal_review"])

async def _resolve_output_locale_or_422(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    explicit_locale: str | None = None,
    user_default_output_locale: str | None = None,
    user_ui_locale: str | None = None,
    deal_primary_language: str | None = None,
    run_analysis_language: str | None = None,
) -> str:
    """
    Resolve effective output locale using 6-level chain.

    Invalid explicit query values are client errors (422). Invalid persisted
    fallback values are safely skipped by resolve_output_locale().
    """
    try:
        return await resolve_output_locale(
            db,
            tenant_id=tenant_id,
            explicit_locale=explicit_locale,
            user_default_output_locale=user_default_output_locale,
            user_ui_locale=user_ui_locale,
            deal_primary_language=deal_primary_language,
            run_analysis_language=run_analysis_language,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


# Backward-compatible alias for callers still using the old name.
_resolve_presentation_locale_or_422 = _resolve_output_locale_or_422


def _to_result_presentation_progress_dto(
    progress: ResultPresentationProgress,
    *,
    dispatch_status: str = "not_dispatched",
) -> ResultPresentationProgressDTO:
    """Convert D3 service progress dataclass to the public API DTO."""
    return ResultPresentationProgressDTO(
        run_id=progress.run_id,
        locale=progress.locale,
        content_version=progress.content_version,
        total=progress.total,
        missing=progress.missing,
        pending=progress.pending,
        processing=progress.processing,
        ready=progress.ready,
        reviewed=progress.reviewed,
        approved=progress.approved,
        failed=progress.failed,
        stale=progress.stale,
        created_pending=progress.created_pending,
        existing=progress.existing,
        is_complete=progress.is_complete,
        dispatch_status=dispatch_status,
    )

# ---------------------------------------------------------------------------
# Helper function: access validation and run loading
# Used across endpoints requiring specific run context.
# ---------------------------------------------------------------------------


async def _get_run_with_access_check(
    deal_id: str,
    run_id: str,
    db: AsyncSession,
    user: CurrentUser,
    allowed_roles: tuple[str, ...] = ("admin", "editor", "viewer"),
) -> object:
    """
    Load Run from database and validate that:
    1. Run exists.
    2. Run belongs to the specified deal.
    3. User has viewer/editor/admin project role on the associated deal.

    Returns the Run object.
    Raises HTTPException 404 / 400 / 403 on violation.
    """
    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(uuid.UUID(run_id))
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "RUN_NOT_FOUND"},
            detail="Run not found",
        )

    if str(run.deal_id) != deal_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            headers={"X-Error-Code": "RUN_DEAL_MISMATCH"},
            detail="Run does not belong to this deal",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=allowed_roles,
    )
    return run


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/{deal_id}/runs/{run_id}/result-presentations/requests",
    response_model=ResultPresentationProgressDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create pending locale-specific result presentations",
)
async def request_result_presentations(
    deal_id: str,
    run_id: str,
    payload: ResultPresentationRequestDTO,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ResultPresentationProgressDTO:
    """
    Create missing pending CheckResultPresentation rows for one Run and locale.

    This operation is idempotent:
    - existing presentation rows are never overwritten;
    - duplicate logical identities are protected by the database;
    - D3 intentionally does not dispatch an LLM worker yet.

    Access: project admin / editor only.
    """
    run = await _get_run_with_access_check(
        deal_id=deal_id,
        run_id=run_id,
        db=db,
        user=user,
        allowed_roles=("admin", "editor"),
    )

    deal = await db.get(Deal, uuid.UUID(deal_id))
    if deal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "DEAL_NOT_FOUND"},
            detail="Deal not found",
        )

    target_locale = await _resolve_presentation_locale_or_422(
        db,
        tenant_id=run.tenant_id,
        explicit_locale=payload.locale,
        user_default_output_locale=getattr(user, "default_output_locale", None),
        user_ui_locale=user.ui_locale,
        deal_primary_language=deal.primary_language,
        run_analysis_language=run.analysis_language,
    )

    service = ResultPresentationRequestService(db)
    progress = await service.request_pending_presentations(
        run_id=uuid.UUID(run_id),
        locale=target_locale,
        source_locale=deal.primary_language,
    )

    # Sprint 6.5: Emit Prometheus translation requested metrics
    try:
        get_metrics().translation_requested_total.labels(locale=target_locale).inc(progress.created_pending)
    except Exception:
        pass

    from services.translation_audit import ACTION_REQUESTED
    audit_repo = AuditRepository(db)
    await audit_repo.log(
        tenant_id=run.tenant_id,
        deal_id=run.deal_id,
        action=ACTION_REQUESTED,
        actor=user.email or user.id,
        actor_role=user.global_role,
        details={
            "run_id": run_id,
            "requested_locale": target_locale,
            "content_version": progress.content_version,
            "total_results": progress.total,
            "created_pending": progress.created_pending,
            "existing_presentations": progress.existing,
            "missing": progress.missing,
            "pending": progress.pending,
            "processing": progress.processing,
            "ready": progress.ready,
            "reviewed": progress.reviewed,
            "approved": progress.approved,
            "failed": progress.failed,
            "stale": progress.stale,
            "translation_execution_policy": "active_application_provider",
            "cloud_fallback_enabled": False,
            "dispatch_status": "not_dispatched",
        },
    )

    outbox_service = OutboxService(db)
    await outbox_service.enqueue_task(
        task_name="workers.process_pending_result_presentations",
        payload={
            "run_id": run_id,
            "deal_id": deal_id,
            "tenant_id": str(run.tenant_id),
            "locale": target_locale,
            "content_version": progress.content_version,
            "batch_limit": 25,
        },
        aggregate_type="run",
        aggregate_id=run_id,
        dedup_key=(
            "result-presentation-batch:"
            f"{run_id}:{target_locale}:{progress.content_version}"
        ),
        headers={
            "queue": "heavy_llm_checks",
        },
    )

    await db.commit()

    return _to_result_presentation_progress_dto(
        progress,
        dispatch_status="queued",
    )


@router.get(
    "/{deal_id}/runs/{run_id}/result-presentations/progress",
    response_model=ResultPresentationProgressDTO,
    summary="Get locale-specific result presentation progress",
)
async def get_result_presentation_progress(
    deal_id: str,
    run_id: str,
    locale: str = Query(
        ...,
        min_length=2,
        max_length=35,
        description=(
            "Target presentation locale. "
            "Must be enabled in the shared UI locale configuration."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ResultPresentationProgressDTO:
    """
    Return progress for locale-specific result presentations without creating,
    updating, dispatching, or translating records.

    Access: project admin / editor / viewer.
    """
    run = await _get_run_with_access_check(
        deal_id=deal_id,
        run_id=run_id,
        db=db,
        user=user,
    )

    target_locale = await _resolve_presentation_locale_or_422(
        db,
        tenant_id=run.tenant_id,
        explicit_locale=locale,
        user_default_output_locale=getattr(user, "default_output_locale", None),
        user_ui_locale=user.ui_locale,
        deal_primary_language=None,
        run_analysis_language=run.analysis_language,
    )

    service = ResultPresentationRequestService(db)
    progress = await service.get_progress(
        run_id=uuid.UUID(run_id),
        locale=target_locale,
    )

    return _to_result_presentation_progress_dto(progress)


@router.get(
    "/{deal_id}/runs/{run_id}/documents",
    response_model=list[DocumentSummaryDTO],
    summary="List of documents and risks for run",
)
async def get_documents_for_run(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieve list of documents with aggregated risk counters by severity level
    for the specified run execution.

    Access: project viewer / editor / admin.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_uuid = uuid.UUID(run_id)
    from db.repositories.runner_repo import RunnerRepository
    from db.uow import db_uow

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        documents = await runner_repo.load_documents_for_run(run_uuid)

    # Direct severity count by documents
    doc_stats: dict[str, dict[str, int]] = {
        doc_id: {"critical": 0, "high": 0, "medium": 0, "pass": 0, "unclear": 0}
        for doc_id in documents.keys()
    }

    for cr in check_results:
        doc_id = cr.get("document_id", "")
        if doc_id not in doc_stats:
            continue

        result = cr.get("result", "unclear")
        severity = cr.get("severity", "medium")

        if result == "fail":
            if severity in doc_stats[doc_id]:
                doc_stats[doc_id][severity] += 1
        elif result == "pass":
            doc_stats[doc_id]["pass"] += 1
        else:
            doc_stats[doc_id]["unclear"] += 1

    # DTO Assembly
    summaries: list[DocumentSummaryDTO] = []
    for doc_id, doc_meta in documents.items():
        stats = doc_stats.get(doc_id, {})
        summaries.append(
            DocumentSummaryDTO(
                document_id=doc_id,
                name=doc_meta.get("name", ""),
                doc_type=doc_meta.get("doc_type", "Generic"),
                status=doc_meta.get("status", ""),
                critical_count=stats.get("critical", 0),
                high_count=stats.get("high", 0),
                medium_count=stats.get("medium", 0),
                pass_count=stats.get("pass", 0),
                unclear_count=stats.get("unclear", 0),
                has_degraded_structure=False,  # Can be added if needed
                in_quarantine=doc_meta.get("status") == "quarantine",
                classification_level=doc_meta.get("classification_level", ""),
                classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
            )
        )

    summaries.sort(key=lambda s: s.name.lower())
    return summaries


@router.get(
    "/{deal_id}/runs/{run_id}/documents/{document_id}",
    response_model=DocumentDetailDTO,
    summary="Detailed document card for run",
)
async def get_document_detail_for_run(
    deal_id: str,
    run_id: str,
    document_id: str,
    output_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        description=(
            "Requested output locale for result presentation. "
            "Falls back to user default, UI locale, deal language, then system default."
        ),
    ),
    presentation_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        deprecated=True,
        description="Deprecated: use output_locale instead.",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieve detailed parameters of a single document: checks performed,
    evidences, structured_data, and classification metadata.

    Access: project viewer / editor / admin.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_uuid = uuid.UUID(run_id)

    deal = await db.get(Deal, uuid.UUID(deal_id))
    run_for_locale = await db.get(Run, uuid.UUID(run_id))
    effective_locale = output_locale or presentation_locale
    resolved_output_locale = await _resolve_output_locale_or_422(
        db,
        tenant_id=run_for_locale.tenant_id if run_for_locale else uuid.UUID(int=0),
        explicit_locale=effective_locale,
        user_default_output_locale=getattr(user, "default_output_locale", None),
        user_ui_locale=user.ui_locale,
        deal_primary_language=deal.primary_language if deal else None,
        run_analysis_language=run_for_locale.analysis_language if run_for_locale else None,
    )

    from db.repositories.runner_repo import RunnerRepository
    from db.uow import db_uow

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        check_results = await apply_presentations_for_read(
            session=uow.session,
            check_results=check_results,
            requested_locale=resolved_output_locale,
        )
        documents = await runner_repo.load_documents_for_run(run_uuid)

    if document_id not in documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "DOCUMENT_NOT_FOUND"},
            detail="Document not found",
        )

    doc_meta = documents[document_id]

    # Filter check_results by document_id
    doc_check_results = [
        cr for cr in check_results
        if cr.get("document_id") == document_id
    ]

    # Assemble CheckItemDTO
    checks: list[CheckItemDTO] = []
    for cr in doc_check_results:
        checks.append(
            CheckItemDTO(
                check_id=cr.get("check_id", ""),
                check_name=cr.get("check_name", ""),
                result=cr.get("result", "unclear"),
                severity=cr.get("severity", "medium"),
                evidence_snippet=(cr.get("display_text") or cr.get("value_text", ""))[:300],
                page=cr.get("page"),
                clause_uid=cr.get("clause_uid", ""),
                confidence=cr.get("confidence", 0.0),
                detector_used=cr.get("detector_used", ""),
                quality_flags={"flags": cr.get("quality_flags")} if cr.get("quality_flags") else None,
                conditional_check_triggered=cr.get("conditional_check_triggered", False),
                trigger_name=cr.get("trigger_name", ""),
                structured_data=cr.get("structured_data") or {},
                origin=cr.get("origin"),
                segment_id=cr.get("segment_id"),
                segment_type=cr.get("segment_type"),
                segment_title=cr.get("segment_title"),
                segment_order=cr.get("segment_order"),
                is_primary_segment=cr.get("is_primary_segment"),
                display_text=cr.get("display_text"),
                review_status=cr.get("review_status"),
                review_message=cr.get("review_message"),
                review_status_counter=cr.get("review_status_counter"),
                needs_manual_review=cr.get("needs_manual_review", False),
                ui_mode=cr.get("ui_mode"),
                output_locale=cr.get("output_locale"),
                presentation_locale=cr.get("presentation_locale"),
                presentation_content_version=cr.get(
                    "presentation_content_version"
                ),
                presentation_source_locale=cr.get(
                    "presentation_source_locale"
                ),
                presentation_status=cr.get("presentation_status"),
                presentation_is_fallback=cr.get(
                    "presentation_is_fallback",
                    True,
                ),
                canonical_check_name=cr.get("canonical_check_name"),
                canonical_display_text=cr.get(
                    "canonical_display_text"
                ),
                canonical_review_message=cr.get(
                    "canonical_review_message"
                ),
            )
        )

    return DocumentDetailDTO(
        document_id=document_id,
        name=doc_meta.get("name", ""),
        doc_type=doc_meta.get("doc_type", "Generic"),
        status=doc_meta.get("status", ""),
        classification_level=doc_meta.get("classification_level", ""),
        classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
        applicable_triggers=doc_meta.get("applicable_triggers", []),
        checks=checks,
        output_locale=resolved_output_locale,
        presentation_locale=resolved_output_locale,
    )


@router.get(
    "/{deal_id}/runs/{run_id}/documents/{document_id}/structured-data",
    response_model=DocumentStructuredDataDTO,
    summary="Structured values for document within run",
)
async def get_document_structured_data_for_run(
    deal_id: str,
    run_id: str,
    document_id: str,
    output_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        description="Requested output locale for result presentation.",
    ),
    presentation_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        deprecated=True,
        description="Deprecated: use output_locale instead.",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieve structured properties (monetary thresholds, dates, counterparties)
    extracted from a document within the specified run sequence.

    Access: project viewer / editor / admin.
    """
    run_uuid = uuid.UUID(run_id)
    run = await _get_run_with_access_check(deal_id, run_id, db, user)

    deal = await db.get(Deal, uuid.UUID(deal_id))
    effective_locale = output_locale or presentation_locale
    resolved_locale = await _resolve_output_locale_or_422(
        db,
        tenant_id=run.tenant_id,
        explicit_locale=effective_locale,
        user_default_output_locale=getattr(user, "default_output_locale", None),
        user_ui_locale=user.ui_locale,
        deal_primary_language=deal.primary_language if deal else None,
        run_analysis_language=run.analysis_language,
    )

    from db.repositories.runner_repo import RunnerRepository
    from db.uow import db_uow

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        check_results = await apply_presentations_for_read(
            session=uow.session,
            check_results=check_results,
            requested_locale=resolved_locale,
        )
        documents = await runner_repo.load_documents_for_run(run_uuid)

    doc_meta = documents.get(document_id)
    if not doc_meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "DOCUMENT_NOT_FOUND_IN_RUN"},
            detail="Document not found in this run",
        )

    # Load playbook name
    playbook_name: str | None = None
    playbook_version_id_str: str | None = None
    if getattr(run, "playbook_version_id", None):
        playbook_version_id_str = str(run.playbook_version_id)
        try:
            pb_repo = PlaybookRepository(db)
            pv = await pb_repo.get_by_id(run.playbook_version_id)
            playbook_name = pv.name if pv else None
        except Exception:
            pass

    # Extract structured values directly from check_results
    doc_values: list[ExtractedValueDTO] = []

    for cr in check_results:
        if cr.get("document_id") != document_id:
            continue

        structured_data = cr.get("structured_data") or {}

        for field_name, field_value in structured_data.items():
            # Value normalization
            if isinstance(field_value, dict) and "value" in field_value:
                raw_display_value = field_value.get("value")
            else:
                raw_display_value = field_value

            if raw_display_value is None or str(raw_display_value) in ("not_found", "not_defined", "None", ""):
                continue

            display_value = str(raw_display_value)

            # Infer format
            name_lower = field_name.lower()
            if any(x in name_lower for x in ("amount", "price", "sum", "cost")):
                field_format = "money"
            elif any(x in name_lower for x in ("date", "expiry", "term")):
                field_format = "date"
            elif any(x in name_lower for x in ("party", "parties", "entity")):
                field_format = "entity_name"
            else:
                field_format = "text"

            doc_values.append(
                ExtractedValueDTO(
                    document_name=doc_meta.get("name", ""),
                    doc_type=doc_meta.get("doc_type", "Generic"),
                    check_name=cr.get("check_name", ""),
                    field_name=field_name,
                    field_value=display_value,
                    field_format=field_format,
                    page=cr.get("page"),
                    clause_uid=cr.get("clause_uid", ""),
                    segment_id=cr.get("segment_id"),
                    segment_type=cr.get("segment_type"),
                    segment_title=cr.get("segment_title"),
                    segment_order=cr.get("segment_order"),
                    is_primary_segment=cr.get("is_primary_segment"),
                )
            )

    return DocumentStructuredDataDTO(
        deal_id=str(run.deal_id),
        run_id=str(run.id),
        document_id=document_id,
        document_name=doc_meta["name"],
        doc_type=doc_meta["doc_type"],
        playbook_version_id=playbook_version_id_str,
        playbook_name=playbook_name,
        profile=getattr(run, "profile", None),
        total_values=len(doc_values),
        values=doc_values,
    )


@router.get(
    "/{deal_id}/runs/{run_id}/dd-requests",
    response_model=list[DDRequestDTO],
    summary="DD requests based on run results",
)
async def get_dd_requests(
    deal_id: str,
    run_id: str,
    output_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        description="Requested output locale for result presentation.",
    ),
    presentation_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        deprecated=True,
        description="Deprecated: use output_locale instead.",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Compile DD requests extracted from missing required properties.
    Deduplicated by check_id, ordered by critical priority indices.

    Access: project viewer / editor / admin.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_uuid = uuid.UUID(run_id)

    from db.repositories.runner_repo import RunnerRepository
    from db.repositories.playbook_repo import PlaybookRepository
    from db.uow import db_uow
    from db.models.run import Run
    from engine.playbook.loader import load_playbook_from_version

    deal = await db.get(Deal, uuid.UUID(deal_id))
    run_for_locale = await db.get(Run, uuid.UUID(run_id))
    effective_locale = output_locale or presentation_locale
    resolved_locale = await _resolve_output_locale_or_422(
        db,
        tenant_id=run_for_locale.tenant_id if run_for_locale else uuid.UUID(int=0),
        explicit_locale=effective_locale,
        user_default_output_locale=getattr(user, "default_output_locale", None),
        user_ui_locale=user.ui_locale,
        deal_primary_language=deal.primary_language if deal else None,
        run_analysis_language=run_for_locale.analysis_language if run_for_locale else None,
    )

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        pb_repo = PlaybookRepository(uow.session)

        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        check_results = await apply_presentations_for_read(
            session=uow.session,
            check_results=check_results,
            requested_locale=resolved_locale,
        )
        documents = await runner_repo.load_documents_for_run(run_uuid)

        # Load PlaybookVersion to retrieve CheckDefinition
        run = await uow.session.get(Run, run_uuid)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                headers={"X-Error-Code": "RUN_NOT_FOUND"},
                detail="Run not found",
            )

        pb_version = await pb_repo.get_by_id(run.playbook_version_id)
        if not pb_version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                headers={"X-Error-Code": "PLAYBOOK_VERSION_NOT_FOUND"},
                detail="PlaybookVersion not found",
            )

        playbook = load_playbook_from_version(pb_version)

        # Build {check_id: CheckDefinition} from BOTH sources:
        #   - global checks (playbook.checks, origin=GLOBAL_PLAYBOOK);
        #   - doc-type checks (Run.instruction_versions → compiled_payload
        #     → DocTypeCheckLoader.load_all_checks_for_doc).
        #
        # Bug history: previously only playbook.checks was used. That
        # collection contains ONLY global checks, so any check_result
        # produced by a doc-type check was silently skipped by
        # build_dd_requests (`if not check_def: continue`). On NDA run
        # 17156da9, 20 of 23 checks are doc-type; without this fix they
        # never produced DD requests.
        checks_by_id = await load_check_definitions_for_run(
            session=uow.session,
            run=run,
            playbook_checks=playbook.checks,
        )

    return build_dd_requests(
        check_results, documents, checks_by_id, locale=resolved_locale,
    )


@router.get(
    "/{deal_id}/runs/{run_id}/conditional-checks",
    response_model=list[ConditionalCheckDTO],
    summary="List of triggered conditional checks",
)
async def get_conditional_checks(
    deal_id: str,
    run_id: str,
    output_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        description="Requested output locale for result presentation.",
    ),
    presentation_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        deprecated=True,
        description="Deprecated: use output_locale instead.",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieve list of conditional checks activated by instruction triggers
    registered under applicable triggers for the run workspace.

    Access: project viewer / editor / admin.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )
    run_uuid = uuid.UUID(run_id)

    deal = await db.get(Deal, uuid.UUID(deal_id))
    run_for_locale = await db.get(Run, uuid.UUID(run_id))
    effective_locale = output_locale or presentation_locale
    resolved_locale = await _resolve_output_locale_or_422(
        db,
        tenant_id=run_for_locale.tenant_id if run_for_locale else uuid.UUID(int=0),
        explicit_locale=effective_locale,
        user_default_output_locale=getattr(user, "default_output_locale", None),
        user_ui_locale=user.ui_locale,
        deal_primary_language=deal.primary_language if deal else None,
        run_analysis_language=run_for_locale.analysis_language if run_for_locale else None,
    )

    from db.repositories.runner_repo import RunnerRepository
    from db.uow import db_uow
    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        check_results = await apply_presentations_for_read(
            session=uow.session,
            check_results=check_results,
            requested_locale=resolved_locale,
        )
        documents = await runner_repo.load_documents_for_run(run_uuid)
    return build_conditional_checks(check_results, documents)


@router.get(
    "/{deal_id}/runs/{run_id}/extracted-values",
    response_model=list[ExtractedValueDTO],
    summary="All extracted structured values for run",
)
async def get_extracted_values(
    deal_id: str,
    run_id: str,
    output_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        description="Requested output locale for result presentation.",
    ),
    presentation_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        deprecated=True,
        description="Deprecated: use output_locale instead.",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Compile all structured metadata fields extracted across the run scope:
    valuation sums, expiration limits, parties, etc.

    Access: project viewer / editor / admin.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )
    run_uuid = uuid.UUID(run_id)

    deal = await db.get(Deal, uuid.UUID(deal_id))
    run_for_locale = await db.get(Run, uuid.UUID(run_id))
    effective_locale = output_locale or presentation_locale
    resolved_locale = await _resolve_output_locale_or_422(
        db,
        tenant_id=run_for_locale.tenant_id if run_for_locale else uuid.UUID(int=0),
        explicit_locale=effective_locale,
        user_default_output_locale=getattr(user, "default_output_locale", None),
        user_ui_locale=user.ui_locale,
        deal_primary_language=deal.primary_language if deal else None,
        run_analysis_language=run_for_locale.analysis_language if run_for_locale else None,
    )

    from db.repositories.runner_repo import RunnerRepository
    from db.uow import db_uow
    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        check_results = await apply_presentations_for_read(
            session=uow.session,
            check_results=check_results,
            requested_locale=resolved_locale,
        )
        documents = await runner_repo.load_documents_for_run(run_uuid)
    return build_extracted_values(check_results, documents)


@router.get(
    "/{deal_id}/runs/{run_id}/dd-matrix",
    response_model=DDMatrixResponseDTO,
    summary="Matrix representation of DD Grid (documents x checks)",
)
async def get_dd_matrix(
    deal_id: str,
    run_id: str,
    output_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        description=(
            "Requested output locale for result presentation. "
            "Falls back to user default, UI locale, deal language, then system default."
        ),
    ),
    presentation_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        deprecated=True,
        description="Deprecated: use output_locale instead.",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Compile standard matrix layout representation for the run dataset.

    Access: project viewer / editor / admin.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_uuid = uuid.UUID(run_id)

    deal_for_locale = await db.get(Deal, uuid.UUID(deal_id))
    run_for_locale = await db.get(Run, uuid.UUID(run_id))
    effective_locale = output_locale or presentation_locale
    resolved_output_locale = await _resolve_output_locale_or_422(
        db,
        tenant_id=run_for_locale.tenant_id if run_for_locale else uuid.UUID(int=0),
        explicit_locale=effective_locale,
        user_default_output_locale=getattr(user, "default_output_locale", None),
        user_ui_locale=user.ui_locale,
        deal_primary_language=deal_for_locale.primary_language if deal_for_locale else None,
        run_analysis_language=run_for_locale.analysis_language if run_for_locale else None,
    )

    from db.repositories.runner_repo import RunnerRepository
    from db.repositories.playbook_repo import PlaybookRepository
    from db.repositories.run_repo import RunRepository
    from db.uow import db_uow
    from engine.playbook.loader import load_playbook_from_version

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        pb_repo = PlaybookRepository(uow.session)
        run_repo = RunRepository(uow.session)

        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        check_results = await apply_presentations_for_read(
            session=uow.session,
            check_results=check_results,
            requested_locale=resolved_output_locale,
        )
        documents = await runner_repo.load_documents_for_run(run_uuid)

        # Load PlaybookVersion for CheckDefinition
        run = await run_repo.get_by_id(run_uuid)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                headers={"X-Error-Code": "RUN_NOT_FOUND"},
                detail="Run not found",
            )

        pb_version = await pb_repo.get_by_id(run.playbook_version_id)
        if not pb_version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                headers={"X-Error-Code": "PLAYBOOK_VERSION_NOT_FOUND"},
                detail="PlaybookVersion not found",
            )

        playbook = load_playbook_from_version(pb_version)
        checks_by_id = {check.id: check for check in playbook.checks}

        deal = await uow.session.get(Deal, uuid.UUID(deal_id))
        deal_name = deal.name if deal else deal_id

    return build_dd_matrix(
        check_results=check_results,
        documents=documents,
        checks_by_id=checks_by_id,
        deal_id=deal_id,
        run_id=run_id,
        deal_name=deal_name,
    )


@router.get(
    "/{deal_id}/runs/{run_id}/dd-grid-v1",
    response_model=DDGridV1ResponseDTO,
    summary="DD Grid V1 — hierarchical representation (groups -> columns -> cells)",
)
async def get_dd_grid_v1(
    deal_id: str,
    run_id: str,
    output_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        description=(
            "Requested output locale for result presentation. "
            "Falls back to user default, UI locale, deal language, then system default."
        ),
    ),
    presentation_locale: str | None = Query(
        default=None,
        min_length=2,
        max_length=35,
        deprecated=True,
        description="Deprecated: use output_locale instead.",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    DD Grid V1: Complete hierarchical structure of DD validation metrics for the new UI.

    Returns DDGridV1ResponseDTO — a compiled payload structure ready for immediate
    rendering by DD Grid components without additional round-trips.

    Distinctions from /dd-matrix:
    - strict hierarchy of global_groups (group → checks → columns)
    - strict hierarchy of doc_type_classes (registry groups → types → checks)
    - cell_values containing detailed cell_state:
        defined         — value discovered, display_value formatted.
        not_defined     — check executed, value not discovered.
        not_applicable  — check not applicable to the document doc_type.
        not_executed    — check was not executed for this document segment.
        error           — technical processing error.
    - drawer_contents containing reason + field details + evidence + location.
    - location propagation:
        exact (high confidence) — clause_ref + page pinpoint from LLM extraction.
        fallback (low confidence) — check-level instruction fallback or null.

    Column formats:
      text           — plain string (+ unit if specified).
      enum           — lookup mapping of enum_labels[raw_value].
      yes_no         — 'Yes' / 'No'.
      presence_only  — 'Present'.

    Drawer reason precedence:
      1. metadata field 'reason'
      2. metadata field 'explanation'
      3. metadata field 'notes'
      4. review_message (CheckResult)
      5. display_text (CheckResult)

    Full API specification contract: docs/dd_grid_v1_contract.md

    Access: project viewer / editor / admin.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )
    deal = await db.get(Deal, uuid.UUID(deal_id))
    run_for_locale = await db.get(Run, uuid.UUID(run_id))
    effective_locale = output_locale or presentation_locale
    resolved_output_locale = await _resolve_output_locale_or_422(
        db,
        tenant_id=run_for_locale.tenant_id if run_for_locale else uuid.UUID(int=0),
        explicit_locale=effective_locale,
        user_default_output_locale=getattr(user, "default_output_locale", None),
        user_ui_locale=user.ui_locale,
        deal_primary_language=deal.primary_language if deal else None,
        run_analysis_language=run_for_locale.analysis_language if run_for_locale else None,
    )

    try:
        return await build_dd_grid_v1_response(
            deal_id=deal_id,
            run_id=run_id,
            output_locale=resolved_output_locale,
            presentation_locale=resolved_output_locale,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "GRID_BUILD_FAILED"},
            detail=str(exc),
        ) from exc
