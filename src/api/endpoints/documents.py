# src/api/endpoints/documents.py

"""
Документный REST-API.

Эндпоинты:
- GET  /documents/{doc_id}            — детальная карточка документа
- POST /documents/{doc_id}/reclassify — ручная переклассификация документа
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.documents import (
    DocumentDetailResponse,
    DocumentResponse,
    ClassificationMetadata,
    ReclassifyRequest,
    ReclassifyResponse,
)
from src.db.repositories.document_repo import DocumentRepository
from src.db.repositories.run_repo import RunRepository
from src.db.repositories.audit_repo import AuditRepository
from src.db.session import get_db


router = APIRouter(prefix="/documents", tags=["documents"])


# -------------------------------------------------------------------
# Временные заглушки для пользователя (заменишь на свою auth-схему)
# -------------------------------------------------------------------


class CurrentUser:
    id: str = "system"
    role: str = "system"
    tenant_id: uuid.UUID = uuid.UUID(int=0)


def get_current_user() -> CurrentUser:
    """
    Заглушка для текущего пользователя.

    В продакшене замени на реальный get_current_user,
    который достаёт user из токена / API-ключа.
    """
    return CurrentUser()


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
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Пока latest_version и family_id не заполняем
    latest_version = None
    family_id = None

    # Определяем, есть ли YAML-инструкция для doc_type
    yaml_instruction_available = False
    if doc.doc_type:
        yaml_path = Path(f"playbooks/document_types/{doc.doc_type}.yaml")
        yaml_instruction_available = yaml_path.exists()

    # Флаг низкой уверенности
    low_confidence = False
    if doc.classification_confidence is not None:
        low_confidence = 0 < doc.classification_confidence < 0.6

    document_response = DocumentResponse.model_validate(doc)

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
# Эндпоинты
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
    """
    Возвращает детальную карточку документа:
    - основные поля (filename, status, doc_type, язык и т.д.);
    - метаданные классификации (уровень, уверенность, триггеры, наличие YAML).

    TODO: добавить проверку прав доступа к сделке (deal_id).
    """
    return await _load_document_detail(db, doc_id)


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

    Шаги:
    1. Находим документ, проверяем доступ.
    2. Проверяем, есть ли YAML-инструкция для нового doc_type.
    3. Загружаем applicable_triggers из YAML (если файл есть).
    4. Обновляем поля классификации документа (L_manual, confidence=1.0).
    5. При необходимости ставим задачу на повторный запуск проверок.
    6. Пишем запись в AuditLog через AuditRepository.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # TODO: ролевая модель — только editor/owner/admin
    # if user.role not in ("editor", "owner", "admin"):
    #     raise HTTPException(status_code=403, detail="Forbidden")

    previous_doc_type = doc.doc_type

    # Проверяем наличие YAML-инструкции
    yaml_path = Path(f"playbooks/document_types/{data.doc_type}.yaml")
    yaml_found = yaml_path.exists()

    # Загружаем applicable_triggers из YAML
    new_triggers: list[str] = []
    if yaml_found:
        import yaml as yaml_lib

        with open(yaml_path, encoding="utf-8") as f:
            yaml_data = yaml_lib.safe_load(f)
        triggers = yaml_data.get("conditional_triggers", [])
        new_triggers = [t.get("name", "") for t in triggers if t.get("name")]

    # Обновляем классификацию документа
    await doc_repo.update_classification(
        doc_id=doc_id,
        doc_type=data.doc_type,
        classification_confidence=1.0,
        classification_level="L_manual",
        classification_details=doc.classification_details or {},
        applicable_triggers=new_triggers,
    )

    # При необходимости — ставим задачу на повторные проверки
    checks_requeued = False
    if data.rerun_checks:
        run_repo = RunRepository(db)
        latest_run = await run_repo.get_latest_for_deal(doc.deal_id)
        if latest_run:
            try:
                from src.workers.runner import run_checks

                run_checks.delay(
                    document_id=str(doc_id),
                    deal_id=str(doc.deal_id),
                    tenant_id=str(user.tenant_id),
                    run_id=str(latest_run.id),
                )
                checks_requeued = True
            except Exception:
                checks_requeued = False

    # Запись в AuditLog
    audit_repo = AuditRepository(db)
    await audit_repo.log(
        tenant_id=user.tenant_id,
        action="DOCUMENT_RECLASSIFIED",
        actor=str(getattr(user, "id", "unknown")),
        deal_id=doc.deal_id,
        actor_role=getattr(user, "role", None),
        details={
            "document_id": str(doc_id),
            "previous_doc_type": previous_doc_type,
            "new_doc_type": data.doc_type,
            "reason": data.reason,
            "yaml_instruction_found": yaml_found,
            "new_applicable_triggers": new_triggers,
            "checks_requeued": checks_requeued,
        },
    )

    return ReclassifyResponse(
        document_id=doc_id,
        previous_doc_type=previous_doc_type,
        new_doc_type=data.doc_type,
        new_applicable_triggers=new_triggers,
        yaml_instruction_found=yaml_found,
        checks_requeued=checks_requeued,
    )
