# src/api/endpoints/documents.py

"""
Документный REST-API.

Этот модуль содержит HTTP‑эндпоинты для работы с документами MAS-DD.

Используется:
- фронтендом вкладки Documents (детальная карточка документа, правая панель);
- DD Grid и отчётами (экспорт списка документов в Excel / Word / PDF);
- ручной переклассификацией документов и управлением статусом проверки юристом;
- просмотром семейства документов и структурированных данных (clause tree).

Основные маршруты:
- GET  /documents/{doc_id}                  — детальная карточка документа
- POST /documents/{doc_id}/reclassify       — ручная переклассификация документа
- POST /documents/{doc_id}/replace          — замена файла для документа в карантине
- GET  /documents/{doc_id}/family           — семья документов (master + appendices)
- GET  /documents/{doc_id}/pdf-url          — URL на исходный PDF документа
- GET  /documents/{doc_id}/structured-data  — структурированные данные (дерево оглавления)
- POST /documents/{doc_id}/delete           — мягкое удаление документа
- PATCH /documents/{doc_id}/reviewed        — флаг проверки документа юристом
- POST /documents/export/excel              — экспорт списка документов в Excel
- POST /documents/export/word               — экспорт списка документов в Word
- POST /documents/export/pdf                — экспорт списка документов в PDF.
"""

import logging

import uuid
from pathlib import Path
from uuid import UUID
from io import BytesIO
from typing import List, Optional
from fpdf import FPDF

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.mappers.documents import map_document_to_response
from api.mappers.document_versions import map_document_version_to_response
from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from classifiers.yaml_registry import YAMLRegistry
from db.repositories.run_repo import RunRepository
from db.repositories.runner_repo import RunnerRepository
from services.export.aggregator import aggregate_results

from db.session import get_db
from db.models.relation import DocumentFamily, DocumentFamilyMember
from db.models.document import Document
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.relation_repo import RelationRepository
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository

from core.constants import DocumentStatus
from core.exceptions import PermanentError, TransientError

from storage.artifact_store import ArtifactStore, ArtifactPath

from ..schemas.documents import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentVersionResponse,
    ClassificationMetadata,
    ReclassifyRequest,
    ReclassifyResponse,
    DocumentReviewedUpdateRequest,
)

from ..schemas.documents import DocumentExtractedValuesResponse, ExtractedValue
from services.export.models import StructuredValueRow
from services.document_service import DocumentService, DocumentNotFoundError

from core.document_columns import (
    DocumentColumnId,
    DocumentColumnDef,
    ALL_DOCUMENT_COLUMNS,
    get_columns_by_ids,
)

logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parent.parent.parent  # /src
FONT_PATH = BASE_DIR / "resources" / "fonts" / "DejaVuSans.ttf"

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


# -------------------------------------------------------------------
# Схемы и вспомогательные функции для экспорта
# -------------------------------------------------------------------

from pydantic import BaseModel


class DocumentsExportRequest(BaseModel):
    """
    Параметры экспорта списка документов.

    visible_column_ids:
        - список ID колонок, которые нужно включить в экспорт;
        - если None или пусто — используем исходный набор всех колонок.
    deal_id:
        - ID сделки, для которой выгружаем список документов.
    """

    deal_id: UUID
    visible_column_ids: Optional[List[DocumentColumnId]] = None





def build_table_rows(
    documents: list[Document],
    visible_column_ids: Optional[list[DocumentColumnId]],
):
    """
    Построить заголовки и строки таблицы для экспорта на основе списка документов
    и выбранных колонок.
    """

    column_defs: list[DocumentColumnDef] = get_columns_by_ids(visible_column_ids)

    headers = [c.label for c in column_defs]

    rows: list[list[str]] = []
    for doc in documents:
        row: list[str] = []
        for col in column_defs:
            field = col.field
            value = getattr(doc, field, None)

            # минимальное сохранение логики фронта
            if field == "applicable_triggers_count":
                value = len(getattr(doc, "applicable_triggers", []) or [])
            elif field == "status":
                value = doc.status or ""
            elif field == "risk_level":
                value = doc.risk_level or ""

            if isinstance(value, bool):
                row.append("Да" if value else "Нет")
            elif value is None:
                row.append("")
            else:
                row.append(str(value))
        rows.append(row)

    return headers, rows



# -------------------------------------------------------------------
# Вспомогательные функции
# -------------------------------------------------------------------


async def _load_document_detail(
    db: AsyncSession,
    doc_id: uuid.UUID,
) -> DocumentDetailResponse:
    """
    Собрать DocumentDetailResponse из Document.

    Сейчас:
    - грузим сам документ,
    - строим DocumentResponse,
    - собираем блок ClassificationMetadata.

    Позже можно добавить:
    - загрузку последней версии DocumentVersion,
    - семью документов через RunnerRepository.get_document_family.
    Позже можно добавить:
    - загрузку последней версии DocumentVersion,
    - более полную семью документов (amendments, versions).
    """
    doc_repo = DocumentRepository(db)
    version_repo = DocumentVersionRepository(db)
    relation_repo = RelationRepository(db)

    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # latest_version
    latest_version_obj = await version_repo.get_latest(doc_id)
    latest_version: DocumentVersionResponse | None = None
    if latest_version_obj:
        latest_version = map_document_version_to_response(latest_version_obj)

    # family_id
    family_id = await relation_repo.get_document_family_id(doc_id)

    # Определяем, есть ли YAML-инструкция для doc_type
    yaml_instruction_available = False
    if doc.doc_type:
        yaml_path = Path(f"playbooks/document_types/{doc.doc_type}.yaml")
        yaml_instruction_available = yaml_path.exists()

    # Флаг низкой уверенности
    low_confidence = False
    if doc.classification_confidence is not None:
        low_confidence = 0 < doc.classification_confidence < 0.6

    document_response = map_document_to_response(doc)

    classification_block = None
    if doc.doc_type:
        classification_block = ClassificationMetadata(
            doc_type=doc.doc_type,
            classification_level=doc.classification_level or "",
            classification_confidence=doc.classification_confidence or 0.0,
            applicable_triggers=doc.applicable_triggers or [],
            yaml_instruction_available=yaml_instruction_available,
            low_confidence=low_confidence,
        )

    return DocumentDetailResponse(
        document=document_response,
        latest_version=latest_version,
        family_id=family_id,
        classification=classification_block,
    )


# -------------------------------------------------------------------
# Эндпоинты: детали, переклассификация, версия, замена
# -------------------------------------------------------------------


@router.get(
    "/{doc_id}",
    response_model=DocumentDetailResponse,
    summary="Получить детальную информацию о документе",
)
async def get_document_detail(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    return await _load_document_detail(db=db, doc_id=doc_id)


@router.post(
    "/{doc_id}/reclassify",
    response_model=ReclassifyResponse,
    summary="Ручная переклассификация документа",
)
async def reclassify_document(
    doc_id: uuid.UUID,
    data: ReclassifyRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Ручная переклассификация документа.

    Что делает этот эндпоинт:
    1. Находит документ по ID и проверяет, что он существует.
    2. Проверяет, что у пользователя есть права на проект (сделку) этого документа.
       Ручная переклассификация разрешена только для ролей "admin" и "editor".
    3. Проверяет, что новый doc_type известен YAMLRegistry (есть в реестре типов).
    4. Для найденного типа загружает список доступных триггеров из YAMLRegistry.
       В качестве применённых триггеров используются ключи trigger_definitions.
    5. Обновляет поля классификации документа:
       - doc_type = переданное значение,
       - classification_level = "L_manual",
       - classification_confidence = 1.0,
       - applicable_triggers = список триггеров из YAMLRegistry.
    6. [DEPRECATED] Перезапуск checks для одного документа не выполняется.
       Checks запускаются на уровне всего Run отдельным пайплайном.
    7. Пишет запись в AuditLog через AuditRepository.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Проверяем роль пользователя в проекте (сделке документа)
    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("admin", "editor"),
    )

    previous_doc_type = doc.doc_type

    # --- НОВОЕ: работаем через YAMLRegistry, а не прямой файловый доступ ---
    registry = YAMLRegistry.get_instance()
    cfg = registry.get_config(data.doc_type)

    # Если тип не найден в реестре — возвращаем 422 с понятным описанием
    if cfg is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown document type: '{data.doc_type}'. "
                   f"Проверьте, что тип существует в YAML‑реестре.",
        )

    # В YAMLRegistry тип найден → YAML-файл загружен
    yaml_found = True

    # Берём список возможных триггеров для этого типа.
    # Ключи trigger_definitions — это ID триггеров (используются в TriggerDetector).
    # Если в DocumentTypeConfig уже есть trigger_ids, можно использовать их.
    trigger_ids = getattr(cfg, "trigger_ids", None)
    if trigger_ids is not None:
        new_triggers: list[str] = list(trigger_ids)
    else:
        new_triggers = list(getattr(cfg, "trigger_definitions", {}).keys())

    # Обновляем классификацию документа
    await doc_repo.update_classification(
        doc_id=doc_id,
        doc_type=data.doc_type,
        classification_confidence=1.0,
        classification_level="L_manual",
        classification_details=doc.classification_details or {},
        applicable_triggers=new_triggers,
    )

    # Флаг для аудита: сейчас мы НЕ ставим per-document checks заново
    checks_requeued = False
    rerun_checks_requested = bool(getattr(data, "rerun_checks", False))

    # Запись в AuditLog
    audit_repo = AuditRepository(db)
    await audit_repo.log(
        tenant_id=user.tenant_id,
        action="RECLASSIFY",
        actor=str(getattr(user, "id", "unknown")),
        deal_id=doc.deal_id,
        actor_role=getattr(user, "global_role", None),
        details={
            "document_id": str(doc_id),
            "previous_doc_type": previous_doc_type,
            "new_doc_type": data.doc_type,
            "reason": data.reason,
            "yaml_instruction_found": yaml_found,
            "new_applicable_triggers": new_triggers,
            "checks_requeued": checks_requeued,
            "rerun_checks_flag_requested": rerun_checks_requested,
            "rerun_checks_behavior": "deprecated_no_action",
        },
    )

    # НОВОЕ: помечаем сделку как требующую перезапуска анализа
    # после ручной переклассификации документов.
    deal_repo = DealRepository(db)
    await deal_repo.set_has_pending_manual_reclassifications(
        deal_id=doc.deal_id,
        value=True,
    )

    return ReclassifyResponse(
        document_id=doc_id,
        previous_doc_type=previous_doc_type,
        new_doc_type=data.doc_type,
        new_applicable_triggers=new_triggers,
        yaml_instruction_found=yaml_found,
        checks_requeued=checks_requeued,
    )



@router.get(
    "/{doc_id}/family",
    summary="Get document family (master + members)",
)
async def get_document_family(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Returns the family of a document:

    - master: the main document
    - appendices: all family members (no strict type yet)
    - amendments: [] (reserved for future use)
    - versions: [] (reserved for future use)

    Семейства заранее строятся воркером build_relations и
    сохраняются в таблицы document_families / document_family_members.
    Этот эндпоинт только читает их.

    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    # Ищем family, где master_doc_id = doc_id, с подгруженными members
    stmt = (
        select(DocumentFamily)
        .where(DocumentFamily.master_doc_id == doc_id)
        .options(
            # Подгружаем членов семьи (DocumentFamilyMember)
            selectinload(DocumentFamily.members)
        )
    )
    result = await db.execute(stmt)
    family: DocumentFamily | None = result.scalars().first()

    if not family:
        # Для этого документа семьи нет — возвращаем только master
        return {
            "master": map_document_to_response(doc),
            "appendices": [],
            "amendments": [],
            "versions": [],
        }

    # Собираем ID всех членов семьи
    member_doc_ids = [member.doc_id for member in family.members]

    # Загружаем сами документы по этим ID
    members_docs = []
    if member_doc_ids:
        stmt_members = select(Document).where(
            Document.id.in_(member_doc_ids)
        )
        result_members = await db.execute(stmt_members)
        members_docs = list(result_members.scalars().all())

    appendices = [map_document_to_response(d) for d in members_docs]

    return {
        "master": map_document_to_response(doc),
        "appendices": appendices,
        "amendments": [],
        "versions": [],
    }


@router.get(
    "/{doc_id}/pdf-url",
    summary="Get original PDF URL for document",
)
async def get_document_pdf_url(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    logger.info(
        "PDF URL access attempt",
        extra={
            "user_id": str(user.id),
            "global_role": user.global_role,
            "doc_id": str(doc_id),
            "deal_id": str(doc.deal_id),
        },
    )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    ver_repo = DocumentVersionRepository(db)
    version = await ver_repo.get_latest(doc_id)
    if not version or not version.original_ref:
        raise HTTPException(status_code=404, detail="Original PDF not available")

    store = ArtifactStore()
    presigned_url = store.get_presigned_get_url(version.original_ref)

    return {"url": presigned_url}


@router.get(
    "/{doc_id}/structured-data",
    summary="Get structured clause tree for document",
)
async def get_document_structured_data(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть структурированные данные (дерево пунктов) для документа.

    Статусы:
    - 404 DOCUMENT_NOT_FOUND   — документа нет в БД.
    - 404 STRUCTURED_NOT_READY — структура ещё не сформирована (нет clause_tree_ref).
    - 404 STRUCTURED_MISSING   — структура ожидалась, но артефакт отсутствует.
    - 503 STORAGE_UNAVAILABLE  — MinIO временно недоступен.
    - 503 STRUCTURED_UNKNOWN_ERROR — любая другая неожиданная ошибка при чтении артефакта.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    ver_repo = DocumentVersionRepository(db)
    version = await ver_repo.get_latest(doc_id)

    if not version or not version.clause_tree_ref:
        # Анализ ещё не дошёл до структуры
        raise HTTPException(
            status_code=404,
            detail={
                "code": "STRUCTURED_NOT_READY",
                "message": "Structured data not available",
            },
        )

    store = ArtifactStore()
    try:
        payload = store.get_json(version.clause_tree_ref)
    except PermanentError:
        # Файл ожидается, но не найден — логическая проблема / утрата данных
        raise HTTPException(
            status_code=404,
            detail={
                "code": "STRUCTURED_MISSING",
                "message": "Structured data not found",
            },
        )
    except TransientError:
        # Проблема со стореджем — MinIO временно недоступен
        raise HTTPException(
            status_code=503,
            detail={
                "code": "STORAGE_UNAVAILABLE",
                "message": "Storage temporarily unavailable",
            },
        )
    except Exception:
        # Любая другая неожиданная ошибка при чтении артефакта
        raise HTTPException(
            status_code=503,
            detail={
                "code": "STRUCTURED_UNKNOWN_ERROR",
                "message": "Structured data temporarily unavailable",
            },
        )

    # payload уже dict/list, фронт получает JSON дерево
    return payload


@router.get(
    "/{doc_id}/extracted-values",
    response_model=DocumentExtractedValuesResponse,
    summary="Получить извлечённые структурированные значения для документа",
)
async def get_document_extracted_values(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    # 1. Проверяем, что документ существует и доступен
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    # 2. Находим актуальный Run для сделки и агрегируем результаты

    run_repo = RunRepository(db)
    run = await run_repo.get_latest_for_deal(doc.deal_id)
    if not run:
        # По сделке ещё ни разу не запускали анализ — нет ни одного Run.
        rows: list[StructuredValueRow] = []
    else:
        runner_repo = RunnerRepository(db)
        documents_dict = await runner_repo.load_documents_for_run(run.id)
        check_results = await runner_repo.load_check_results_for_run(run.id)

        # deal_name можно получить из run.deal, если у тебя есть relationship;
        # если нет — передаём пустую строку/позже дообогатишь.
        deal_name = ""

        agg = aggregate_results(
            deal_id=str(doc.deal_id),
            deal_name=deal_name,
            run_id=str(run.id),
            check_results=check_results,
            documents=documents_dict,
        )

        rows: list[StructuredValueRow] = [
            r for r in agg.structured_value_rows
            if r.document_id == str(doc_id)
        ]


    # 3. Если значений нет — возвращаем пустой набор (notAvailable, но без ошибки)
    if not rows:
        return DocumentExtractedValuesResponse(
            document_id=str(doc_id),
            filename=doc.filename,
            doc_type=doc.doc_type,
            extracted_values=[],
            total_extracted=0,
        )

    # 4. Маппинг StructuredValueRow -> ExtractedValue
    extracted_values = [
        ExtractedValue(
            check_id=r.check_id,
            check_name=r.check_name,
            field_name=r.field_name,
            field_value=r.field_value,
            field_format=r.field_format,
            page=r.page,
            clause_uid=r.clause_uid or "",
        )
        for r in rows
    ]

    return DocumentExtractedValuesResponse(
        document_id=str(doc_id),
        filename=doc.filename,
        doc_type=doc.doc_type,
        extracted_values=extracted_values,
        total_extracted=len(extracted_values),
    )


@router.post(
    "/{doc_id}/replace",
    summary="Replace a quarantined document with a new file",
)
async def replace_document(
    doc_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Replace a quarantined document with a corrected file.

    Шаги:
    1. Находим документ и проверяем, что он в статусе QUARANTINE.
    2. Проверяем роль пользователя в проекте (deal_id документа):
       заменять файл могут только роли "admin" и "editor".
    3. Сохраняем новый файл в ArtifactStore.
    4. Сбрасываем статус и классификацию, чтобы документ прошёл пайплайн заново.
    5. Пишем запись в AuditLog.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status != DocumentStatus.QUARANTINE.value:
        raise HTTPException(
            status_code=422,
            detail="Only quarantined documents can be replaced",
        )

    # Проверяем роль пользователя в проекте документа
    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("admin", "editor"),
    )

    # Сохраняем новый файл в ArtifactStore
    store = ArtifactStore()
    file_bytes = await file.read()
    file_ref = store.put_file(
        ArtifactPath.original(str(user.tenant_id), str(doc.deal_id), str(doc.id)),
        file_bytes,
    )

    # Сбрасываем статус и классификацию
    await doc_repo.reset_for_reprocessing(
        doc.id,
        new_status=DocumentStatus.PENDING.value,
        clear_classification=True,
    )

    # Аудит
    audit_repo = AuditRepository(db)
    await audit_repo.log(
        tenant_id=user.tenant_id,
        deal_id=doc.deal_id,
        action="DOCUMENT_REPLACE",
        actor=str(getattr(user, "id", "unknown")),
        actor_role=getattr(user, "global_role", None),
        details={
            "document_id": str(doc.id),
            "filename": file.filename,
            "previous_doc_type": doc.doc_type,
            "classification_reset": True,
            "artifact_ref": file_ref,
        },
    )

    return {
        "status": "ok",
        "document_id": str(doc.id),
        "new_status": DocumentStatus.PENDING.value,
        "classification_reset": True,
    }


@router.post(
    "/{doc_id}/delete",
    summary="Soft-delete документа (пометить как deleted)",
)
async def soft_delete_document(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Мягкое удаление документа из проекта.

    Что делает:
    - проверяет, что документ существует;
    - проверяет роль пользователя в проекте (admin/editor);
    - меняет статус документа на 'deleted';
    - пишет запись в AuditLog.

    Документ остаётся в БД и сторедже, но:
    - по умолчанию может быть скрыт из основного списка документов;
    - остаётся доступным через аудит и внутренние ссылки.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Только admin/editor проекта могут удалять документ
    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("admin", "editor"),
    )

    # Если документ уже удалён — считаем операцию идемпотентной
    if doc.status == DocumentStatus.DELETED.value:
        return {
            "status": "ok",
            "document_id": str(doc.id),
            "new_status": doc.status,
            "already_deleted": True,
        }

    # Меняем статус на deleted
    await doc_repo.update_status(doc_id=doc.id, status=DocumentStatus.DELETED.value)

    # Пишем запись в аудит‑лог
    audit_repo = AuditRepository(db)
    await audit_repo.log(
        tenant_id=user.tenant_id,
        deal_id=doc.deal_id,
        action="DOCUMENT_SOFT_DELETE",
        actor=str(getattr(user, "id", "unknown")),
        actor_role=getattr(user, "global_role", None),
        details={
            "document_id": str(doc.id),
            "previous_status": doc.status,
            "new_status": DocumentStatus.DELETED.value,
        },
    )

    await db.commit()

    return {
        "status": "ok",
        "document_id": str(doc.id),
        "new_status": DocumentStatus.DELETED.value,
        "already_deleted": False,
    }



@router.patch(
    "/{doc_id}/reviewed",
    response_model=DocumentResponse,
    summary="Обновить флаг проверки документа юристом",
)
async def update_document_reviewed_flag(
    doc_id: uuid.UUID,
    body: DocumentReviewedUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Обновить флаг reviewed_by_person у документа.

    Использование:
    - true  -> документ помечен как проверенный юристом;
    - false -> снять отметку о проверке.
    """
    service = DocumentService(db)

    try:
        updated_document = await service.set_reviewed_flag(
            doc_id=doc_id,
            reviewed_by_person=body.reviewed_by_person,
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")

    return updated_document


# -------------------------------------------------------------------
# Эндпоинты экспорта
# -------------------------------------------------------------------

@router.post(
    "/export/excel",
    summary="Экспорт списка документов сделки в Excel",
)
async def export_documents_excel(
    body: DocumentsExportRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Экспортирует список документов сделки в Excel.

    - Проверяет права на сделку.
    - Собирает таблицу по выбранным колонкам.
    - Возвращает xlsx-файл.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=body.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    doc_repo = DocumentRepository(db)
    documents = await doc_repo.list_by_deal_id(body.deal_id)

    if not documents:
        raise HTTPException(status_code=404, detail="Документы не найдены")

    headers, rows = build_table_rows(documents, body.visible_column_ids)

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Documents"

    ws.append(headers)
    for row in rows:
        ws.append(row)

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename = f"deal_{body.deal_id}_documents.xlsx"
    headers_resp = {
        "Content-Disposition": f'attachment; filename=\"{filename}\"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    }

    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers_resp,
    )


@router.post(
    "/export/word",
    summary="Экспорт списка документов сделки в Word (docx)",
)
async def export_documents_word(
    body: DocumentsExportRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    await require_project_role(
        db=db,
        user=user,
        deal_id=body.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    doc_repo = DocumentRepository(db)
    documents = await doc_repo.list_by_deal_id(body.deal_id)

    if not documents:
        raise HTTPException(status_code=404, detail="Документы не найдены")

    headers, rows = build_table_rows(documents, body.visible_column_ids)

    from docx import Document as DocxDocument

    docx = DocxDocument()
    table = docx.add_table(rows=1, cols=len(headers))
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h

    for row in rows:
        row_cells = table.add_row().cells
        for i, cell_val in enumerate(row):
            row_cells[i].text = cell_val

    stream = BytesIO()
    docx.save(stream)
    stream.seek(0)

    filename = f"deal_{body.deal_id}_documents.docx"
    headers_resp = {
        "Content-Disposition": f'attachment; filename=\"{filename}\"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    }

    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers_resp,
    )


@router.post(
    "/export/pdf",
    summary="Экспорт списка документов сделки в PDF",
)
async def export_documents_pdf(
    body: DocumentsExportRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    await require_project_role(
        db=db,
        user=user,
        deal_id=body.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    doc_repo = DocumentRepository(db)
    documents = await doc_repo.list_by_deal_id(body.deal_id)

    if not documents:
        raise HTTPException(status_code=404, detail="Документы не найдены")

    headers, rows = build_table_rows(documents, body.visible_column_ids)

    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", FONT_PATH.as_posix(), uni=True)
    pdf.set_font("DejaVu", size=10)

    line_height = pdf.font_size * 1.5
    col_width = pdf.epw / max(len(headers), 1)

    for h in headers:
        pdf.cell(col_width, line_height, txt=h[:50], border=1)
    pdf.ln(line_height)

    for row in rows:
        for cell_val in row:
            pdf.cell(col_width, line_height, txt=cell_val[:50], border=1)
        pdf.ln(line_height)

    out_bytes = bytes(pdf.output(dest="S"))

    filename = f"deal_{body.deal_id}_documents.pdf"

    return Response(
        content=out_bytes,
        media_type="application/pdf",
        headers={
        "Content-Disposition": f'attachment; filename="deal_{body.deal_id}_documents.pdf"',
        },
    )

