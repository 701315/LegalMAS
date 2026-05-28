# src/services/review_qc_service.py

"""
Сервис QC‑действий для review mode.

Назначение:
- принять review‑ориентированный finding key
  (run_id, document_id, check_id, segment_id);
- проверить существование Run и Deal;
- применить QC‑статус ко всей группе CheckResult,
  которая соответствует одной ячейке review‑матрицы;
- записать неизменяемую audit‑запись о действии пользователя.

Архитектурный принцип:
- deal_review_service отвечает только за read / aggregation / DTO building;
- review_qc_service отвечает только за mutation и audit trail;
- legacy QC path через result_id не меняется и не ломается.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser
from api.schemas.qc import (
    ReviewFindingKey,
    ReviewQCBulkItemResponse,
    ReviewQCBulkUpdateRequest,
    ReviewQCBulkUpdateResponse,
    ReviewQCUpdateRequest,
    ReviewQCUpdateResponse,
)
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.result_repo import ResultRepository
from db.repositories.run_repo import RunRepository


@dataclass(slots=True)
class ReviewQCScope:
    """
    Подготовленный scope review QC mutation.
    """

    run_id: uuid.UUID
    deal_id: uuid.UUID
    tenant_id: uuid.UUID


@dataclass(slots=True)
class ReviewQCUpdateResult:
    deal_id: uuid.UUID
    run_id: uuid.UUID
    document_id: uuid.UUID
    check_id: str
    segment_id: str | None
    qc_status: str
    qc_by: str
    qc_comment: str | None
    updated_rows_count: int
    changed: bool


@dataclass(slots=True)
class ReviewQCBulkUpdateResult:
    deal_id: uuid.UUID
    run_id: uuid.UUID
    qc_status: str
    qc_by: str
    qc_comment: str | None
    total_findings: int
    updated_findings: int
    changed_findings: int
    updated_rows_count: int
    items: list[ReviewQCUpdateResult]


@dataclass(slots=True)
class ReviewQCAuditPayload:
    """
    Typed helper для единообразного audit payload.
    """

    scope: str
    mode: str
    target_type: str
    run_id: str
    qc_status: str
    comment: str | None

    def to_dict(self, **extra: object) -> dict:
        base = {
            "scope": self.scope,
            "mode": self.mode,
            "target_type": self.target_type,
            "run_id": self.run_id,
            "qc_status": self.qc_status,
            "comment": self.comment,
        }
        base.update(extra)
        return base


def _parse_uuid(value: str, error_detail: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_detail,
        ) from exc


def _normalize_comment(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _row_has_target_qc_state(
    row: object,
    *,
    qc_status: str,
    qc_by: str,
    qc_comment: str | None,
) -> bool:
    """
    Проверить, находится ли строка уже в целевом QC‑состоянии.
    """
    return (
        getattr(row, "qc_status", None) == qc_status
        and getattr(row, "qc_by", None) == qc_by
        and _normalize_comment(getattr(row, "qc_comment", None)) == qc_comment
    )


async def load_review_qc_scope(
    db: AsyncSession,
    run_id: str,
) -> ReviewQCScope:
    """
    Загрузить и проверить базовый scope для review QC операции:
    Run -> Deal -> tenant_id.
    """
    run_uuid = _parse_uuid(run_id, "INVALID_RUN_ID")

    run_repo = RunRepository(db)
    deal_repo = DealRepository(db)

    run = await run_repo.get_by_id(run_uuid)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RUN_NOT_FOUND",
        )

    deal = await deal_repo.get_by_id(run.deal_id)
    if deal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DEAL_NOT_FOUND",
        )

    return ReviewQCScope(
        run_id=run_uuid,
        deal_id=deal.id,
        tenant_id=deal.tenant_id,
    )


async def _apply_single_review_qc_update(
    db: AsyncSession,
    user: CurrentUser,
    scope: ReviewQCScope,
    finding: ReviewFindingKey,
    qc_status: str,
    comment: str | None,
) -> ReviewQCUpdateResult:
    document_uuid = _parse_uuid(finding.document_id, "INVALID_DOCUMENT_ID")

    result_repo = ResultRepository(db)

    updated_rows_count = await result_repo.update_review_qc(
        run_id=scope.run_id,
        document_id=document_uuid,
        check_id=finding.check_id,
        segment_id=finding.segment_id,
        qc_status=qc_status,
        qc_by=user.email,
        qc_comment=comment,
    )

    if updated_rows_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="REVIEW_FINDING_NOT_FOUND",
        )

    # Упрощённая семантика changed: если update выполнился, считаем changed=True
    # (потому что update_review_qc всегда SET новые значения, даже если они совпадают).
    # Для строгой проверки "изменилось ли реально" нужен предварительный SELECT,
    # но для MVP достаточно считать, что rowcount > 0 → changed.
    changed = True

    return ReviewQCUpdateResult(
        deal_id=scope.deal_id,
        run_id=scope.run_id,
        document_id=document_uuid,
        check_id=finding.check_id,
        segment_id=finding.segment_id,
        qc_status=qc_status,
        qc_by=user.email,
        qc_comment=comment,
        updated_rows_count=updated_rows_count,
        changed=changed,
    )


async def apply_review_qc_update(
    db: AsyncSession,
    user: CurrentUser,
    payload: ReviewQCUpdateRequest,
    *,
    commit: bool = False,
) -> ReviewQCUpdateResult:
    """
    Применить QC‑действие к одному finding'у review‑матрицы.

    commit=False по умолчанию:
    - безопасный вариант, если commit уже централизован на уровне request/uow.

    commit=True:
    - использовать, если endpoint/service отвечает за завершение транзакции сам.
    """
    scope = await load_review_qc_scope(db=db, run_id=payload.finding.run_id)

    result = await _apply_single_review_qc_update(
        db=db,
        user=user,
        scope=scope,
        finding=payload.finding,
        qc_status=payload.qc_status,
        comment=payload.comment,
    )

    if result.changed:
        audit_repo = AuditRepository(db)
        audit_payload = ReviewQCAuditPayload(
            scope="review",
            mode="single",
            target_type="matrix_cell",
            run_id=payload.finding.run_id,
            qc_status=payload.qc_status,
            comment=payload.comment,
        )
        await audit_repo.log(
            tenant_id=scope.tenant_id,
            deal_id=scope.deal_id,
            action="QC_ACTION",
            actor=user.email,
            actor_role=getattr(user, "global_role", None),
            details=audit_payload.to_dict(
                document_id=payload.finding.document_id,
                check_id=payload.finding.check_id,
                segment_id=payload.finding.segment_id,
                updated_rows_count=result.updated_rows_count,
            ),
        )

    if commit:
        await db.commit()

    return result


async def apply_bulk_review_qc_update(
    db: AsyncSession,
    user: CurrentUser,
    payload: ReviewQCBulkUpdateRequest,
    *,
    commit: bool = False,
) -> ReviewQCBulkUpdateResult:
    """
    Применить одно QC‑действие к нескольким finding'ам review‑матрицы.

    Семантика:
    - strict mode: если любой finding не найден, операция падает целиком;
    - audit лог пишется один раз на всю bulk‑операцию;
    - если все items оказались no-op, audit не пишется.
    """
    first_run_id = payload.findings[0].run_id
    scope = await load_review_qc_scope(db=db, run_id=first_run_id)

    items: list[ReviewQCUpdateResult] = []
    total_updated_rows_count = 0
    changed_findings = 0

    for finding in payload.findings:
        item = await _apply_single_review_qc_update(
            db=db,
            user=user,
            scope=scope,
            finding=finding,
            qc_status=payload.qc_status,
            comment=payload.comment,
        )
        items.append(item)
        total_updated_rows_count += item.updated_rows_count
        if item.changed:
            changed_findings += 1

    if changed_findings > 0:
        audit_repo = AuditRepository(db)
        audit_payload = ReviewQCAuditPayload(
            scope="review",
            mode="bulk",
            target_type="matrix_cell_batch",
            run_id=first_run_id,
            qc_status=payload.qc_status,
            comment=payload.comment,
        )
        await audit_repo.log(
            tenant_id=scope.tenant_id,
            deal_id=scope.deal_id,
            action="QC_ACTION",
            actor=user.email,
            actor_role=getattr(user, "global_role", None),
            details=audit_payload.to_dict(
                total_findings=len(payload.findings),
                updated_findings=len(items),
                changed_findings=changed_findings,
                updated_rows_count=total_updated_rows_count,
                items=[
                    {
                        "document_id": str(item.document_id),
                        "check_id": item.check_id,
                        "segment_id": item.segment_id,
                        "updated_rows_count": item.updated_rows_count,
                        "changed": item.changed,
                    }
                    for item in items
                ],
            ),
        )

    if commit:
        await db.commit()

    return ReviewQCBulkUpdateResult(
        deal_id=scope.deal_id,
        run_id=scope.run_id,
        qc_status=payload.qc_status,
        qc_by=user.email,
        qc_comment=payload.comment,
        total_findings=len(payload.findings),
        updated_findings=len(items),
        changed_findings=changed_findings,
        updated_rows_count=total_updated_rows_count,
        items=items,
    )


def build_review_qc_response(
    result: ReviewQCUpdateResult,
) -> ReviewQCUpdateResponse:
    return ReviewQCUpdateResponse(
        run_id=str(result.run_id),
        deal_id=str(result.deal_id),
        document_id=str(result.document_id),
        check_id=result.check_id,
        segment_id=result.segment_id,
        qc_status=result.qc_status,
        qc_by=result.qc_by,
        qc_comment=result.qc_comment,
        updated_rows_count=result.updated_rows_count,
    )


def build_bulk_review_qc_response(
    result: ReviewQCBulkUpdateResult,
) -> ReviewQCBulkUpdateResponse:
    return ReviewQCBulkUpdateResponse(
        run_id=str(result.run_id),
        deal_id=str(result.deal_id),
        qc_status=result.qc_status,
        qc_by=result.qc_by,
        qc_comment=result.qc_comment,
        total_findings=result.total_findings,
        updated_findings=result.updated_findings,
        changed_findings=result.changed_findings,
        updated_rows_count=result.updated_rows_count,
        items=[
            ReviewQCBulkItemResponse(
                run_id=str(item.run_id),
                deal_id=str(item.deal_id),
                document_id=str(item.document_id),
                check_id=item.check_id,
                segment_id=item.segment_id,
                qc_status=item.qc_status,
                qc_by=item.qc_by,
                qc_comment=item.qc_comment,
                updated_rows_count=item.updated_rows_count,
            )
            for item in result.items
        ],
    )
