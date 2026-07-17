# src/api/endpoints/requests.py

"""
Эндпоинты для DD-запросов (Request List) на уровне сделки.

Фронт ожидает:
- GET    /api/v1/deals/{deal_id}/requests
- POST   /api/v1/deals/{deal_id}/requests
- PATCH  /api/v1/requests/{req_id}
- DELETE /api/v1/requests/{req_id}
"""

import io
import uuid
from datetime import datetime

import xlsxwriter
from docx import Document
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.requests import (
    DDRequestCreate,
    DDRequestResponse,
    DDRequestUpdate,
)
from db.repositories.dd_request_repo import DDRequestRepository
from db.repositories.deal_repo import DealRepository
from db.session import get_db

router = APIRouter(
    prefix="/deals",
    tags=["requests"],
)


@router.get(
    "/{deal_id}/requests",
    response_model=list[DDRequestResponse],
    summary="Список DD-запросов по сделке",
)
async def list_dd_requests_for_deal(
    deal_id: uuid.UUID,
    status: str | None = Query(
        default=None,
        description="Фильтр по статусу: open / in_progress / resolved",
    ),
    priority: str | None = Query(
        default=None,
        description="Фильтр по приоритету: critical / high / medium",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть все DD-запросы для сделки, с опциональными фильтрами.

    Доступ:
    - только участники проекта (viewer/editor/admin) для этой сделки.
    """
    # Проверка доступа по проектной роли (любой участник)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    repo = DDRequestRepository(db)
    items = await repo.list_for_deal(deal_id, status=status, priority=priority)
    return [DDRequestResponse.model_validate(r) for r in items]


@router.post(
    "/{deal_id}/requests",
    response_model=DDRequestResponse,
    summary="Создать новый DD-запрос по сделке",
)
async def create_dd_request_for_deal(
    deal_id: uuid.UUID,
    payload: DDRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Ручное создание DD-запроса юристом.

    Доступ:
    - только редакторы/админы проекта ("editor", "admin").
    """
    # Проверка проектной роли: создавать запросы могут только editor/admin
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    # Опционально: проверяем, что сделка существует
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id, tenant_id=user.tenant_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    req_repo = DDRequestRepository(db)

    # document_ids / check_result_ids пока не используем как ссылки,
    # их можно будет позже разложить в document_refs / evidence_refs.
    req = await req_repo.create_for_deal(
        deal_id=deal_id,
        title=None,
        priority=payload.priority,
        text=payload.text,
        status="open",
        addressee=payload.addressee,
        check_id=None,
        structured_values=[],
        source="manual",
        document_refs=payload.document_ids or [],
        evidence_refs=payload.check_result_ids or [],
    )

    # commit делается на уровне сессии (как у других эндпоинтов)
    await db.commit()
    await db.refresh(req)

    return DDRequestResponse.model_validate(req)


# Отдельный роутер для операций по ID (без префикса /deals)
requests_router = APIRouter(
    prefix="/requests",
    tags=["requests"],
)


@requests_router.patch(
    "/{req_id}",
    response_model=DDRequestResponse,
    summary="Обновить существующий DD-запрос",
)
async def update_dd_request(
    req_id: uuid.UUID,
    payload: DDRequestUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Обновление существующего DD-запроса.

    Доступ:
    - только editor/admin соответствующей сделки.
    """
    repo = DDRequestRepository(db)

    req = await repo.get_by_id(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Проверка проектной роли по deal_id запроса
    await require_project_role(
        db=db,
        user=user,
        deal_id=req.deal_id,
        allowed_roles=("admin", "editor"),
    )

    data: dict = {}
    if payload.priority is not None:
        data["priority"] = payload.priority
    if payload.text is not None:
        data["text"] = payload.text
    if payload.addressee is not None:
        data["addressee"] = payload.addressee
    if payload.status is not None:
        data["status"] = payload.status

    updated = await repo.update(req_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Request not found")

    await db.commit()
    await db.refresh(updated)

    return DDRequestResponse.model_validate(updated)


@requests_router.delete(
    "/{req_id}",
    status_code=204,
    summary="Удалить DD-запрос",
)
async def delete_dd_request(
    req_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Удаление DD-запроса.

    Доступ:
    - только editor/admin соответствующей сделки.
    """
    repo = DDRequestRepository(db)

    req = await repo.get_by_id(req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Проверка проектной роли по deal_id запроса
    await require_project_role(
        db=db,
        user=user,
        deal_id=req.deal_id,
        allowed_roles=("admin", "editor"),
    )

    await repo.delete(req_id)
    await db.commit()


@router.post(
    "/{deal_id}/requests/export",
    summary="Экспорт DD-запросов по сделке в Word/Excel",
)
async def export_dd_requests_for_deal(
    deal_id: uuid.UUID,
    format: str = Query(
        ...,
        description="Формат экспорта: word или excel",
        pattern="^(word|excel)$",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Экспорт DD-запросов по сделке в Word/Excel.

    Доступ:
    - любой участник проекта (viewer/editor/admin).
    """
    # Проверка доступа по проектной роли (любая)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    repo = DDRequestRepository(db)
    items = await repo.list_for_deal(deal_id)

    if not items:
        raise HTTPException(status_code=404, detail="No DD requests for this deal")

    requests = [DDRequestResponse.model_validate(r) for r in items]

    if format == "word":
        content_bytes = generate_requests_docx(deal_id, requests)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    else:  # excel
        content_bytes = generate_requests_xlsx(deal_id, requests)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"dd_requests_{deal_id}_{ts}.{ext}"

    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def generate_requests_docx(deal_id: uuid.UUID, requests: list[DDRequestResponse]) -> bytes:
    doc = Document()
    doc.add_heading(f"DD Requests for deal {deal_id}", level=1)

    doc.add_paragraph(f"Total requests: {len(requests)}")
    doc.add_paragraph("")

    columns = [
        "ID",
        "Priority",
        "Status",
        "Addressee",
        "Text",
        "Check ID",
        "Source",
        "Structured values",
        "Document refs",
        "Evidence refs",
        "Created at",
        "Updated at",
    ]
    table = doc.add_table(rows=1, cols=len(columns))
    table.style = "Table Grid"

    hdr = table.rows[0].cells
    for idx, name in enumerate(columns):
        hdr[idx].text = name

    import json

    for r in requests:
        row = table.add_row().cells
        row[0].text = str(r.id)
        row[1].text = r.priority
        row[2].text = r.status
        row[3].text = r.addressee
        row[4].text = r.text
        row[5].text = r.check_id or ""
        row[6].text = r.source

        # structured_values как JSON
        try:
            row[7].text = json.dumps(r.structured_values, ensure_ascii=False, indent=2)
        except Exception:
            row[7].text = str(r.structured_values or "")

        # ссылки на документы/доказательства
        row[8].text = ", ".join(str(d) for d in r.document_refs or [])
        row[9].text = ", ".join(str(e) for e in r.evidence_refs or [])

        row[10].text = r.created_at.isoformat()
        row[11].text = r.updated_at.isoformat() if r.updated_at else ""

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def generate_requests_xlsx(deal_id: uuid.UUID, requests: list[DDRequestResponse]) -> bytes:
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    ws = workbook.add_worksheet("Requests")

    header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9D9D9"})
    wrap_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})

    columns = [
        ("ID", 36),
        ("Priority", 12),
        ("Status", 12),
        ("Addressee", 20),
        ("Text", 60),
        ("Check ID", 18),
        ("Source", 14),
        ("Structured values", 40),
        ("Document refs", 30),
        ("Evidence refs", 30),
        ("Created at", 22),
        ("Updated at", 22),
    ]

    for col_idx, (name, width) in enumerate(columns):
        ws.write(0, col_idx, name, header_fmt)
        ws.set_column(col_idx, col_idx, width)

    import json

    for row_idx, r in enumerate(requests, start=1):
        ws.write(row_idx, 0, str(r.id), wrap_fmt)
        ws.write(row_idx, 1, r.priority, wrap_fmt)
        ws.write(row_idx, 2, r.status, wrap_fmt)
        ws.write(row_idx, 3, r.addressee, wrap_fmt)
        ws.write(row_idx, 4, r.text, wrap_fmt)
        ws.write(row_idx, 5, r.check_id or "", wrap_fmt)
        ws.write(row_idx, 6, r.source, wrap_fmt)

        try:
            sv_text = json.dumps(r.structured_values, ensure_ascii=False)
        except Exception:
            sv_text = str(r.structured_values or "")
        ws.write(row_idx, 7, sv_text, wrap_fmt)

        doc_refs = ", ".join(str(d) for d in r.document_refs or [])
        ev_refs = ", ".join(str(e) for e in r.evidence_refs or [])
        ws.write(row_idx, 8, doc_refs, wrap_fmt)
        ws.write(row_idx, 9, ev_refs, wrap_fmt)

        ws.write(row_idx, 10, r.created_at.isoformat(), wrap_fmt)
        ws.write(
            row_idx,
            11,
            r.updated_at.isoformat() if r.updated_at else "",
            wrap_fmt,
        )

    workbook.close()
    return output.getvalue()
