# src/api/endpoints/deals.py

"""
Документный REST-API.

Этот модуль описывает все эндпоинты, связанные с отдельными документами
(в отличие от списка документов сделки в endpoints/deals.py).

Основные задачи:
- предоставить фронтенду стабильный REST-API для работы с одним документом:
  * получение детальной карточки документа (метаданные, последняя версия,
    данные классификации, семья документов);
  * доступ к исходному PDF-файлу документа;
  * доступ к структурированным данным (clause tree) документа;
  * ручная переклассификация документа (reclassify);
  * замена файла для документов в карантине;
  * мягкое удаление документа (soft-delete);
  * установка/снятие флага проверки юристом;
  * экспорт списков документов в Excel / Word / PDF.

Архитектурные принципы:
- ORM-модели (Document, DocumentVersion и др.) никогда не отдаются наружу напрямую.
  Все ответы проходят через слой мапперов (map_document_to_response и др.)
  и Pydantic-схемы (DocumentResponse, DocumentDetailResponse и т.п.).
- Вся бизнес-логика формата ответа (human_readable статус, нормализация
  applicable_triggers, выбор последней версии документа) сосредоточена
  в мапперах и сервисах, а не в эндпоинтах.
- Ошибки возвращаются с предсказуемыми HTTP-кодами и JSON-структурой detail:
  * 404 — ресурс не найден или данные ещё не сформированы;
  * 403 — недостаточно прав (RBAC через require_project_role);
  * 503 — временные проблемы инфраструктуры (MinIO / сторедж);
  * 4xx/5xx не должны возникать из-за сырых исключений ORM/Pydantic/MinIO.

Где используется:
- фронтенд вызывает эти эндпоинты для:
  * правой панели "Детали документа" на вкладке "Документы";
  * открытия исходного файла документа;
  * просмотра структурированных данных через отдельное окно;
  * операций переклассификации / удаления / замены файла;
  * экспорта документов в офисные форматы.
"""

from typing import Annotated, List
from uuid import UUID
import sqlalchemy as sa  

from db.repositories.audit_repo import AuditRepository

import os
import tempfile
import zipfile
import uuid
import logging

from db.repositories.playbook_repo import PlaybookRepository
from mas_queue.celery_app import celery_app

from fastapi import (
    APIRouter,
    Query,
    Depends,
    status,
    UploadFile,
    File,
    HTTPException,
)
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role

from .runs import _start_run_core
from api.mappers.documents import map_document_to_response

from ..schemas.runs import RunCreate, RunResponse
from ..schemas.pagination import PaginatedResponse
from ..schemas.documents import DocumentResponse
from db.repositories.project_role_repo import ProjectRoleRepository

from core.constants import DocumentStatus
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.bundle_repo import BundleRepository
from storage.artifact_store import ArtifactStore, ArtifactPath

from db.session import get_db
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.run_repo import RunRepository
from pydantic import BaseModel
from ..schemas.deals import DealResponse, DealCreate, DealPlaybookHistoryItem

from db.models.playbook import PlaybookVersion

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/deals",
    tags=["deals"],
)


@router.get(
    "",
    response_model=PaginatedResponse[DealResponse],
    summary="Список сделок",
)
async def list_deals(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(
        None,
        description="Фильтр по статусу сделки (created, draft, ...)",
    ),
    tenant_id: UUID | None = Query(
        None,
        description="Фильтр по tenant_id (UUID арендатора)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Список сделок с пагинацией.
    """
    repo = DealRepository(db)

    items, total = await repo.get_page(
        page=page,
        per_page=per_page,
        status=status,
        tenant_id=tenant_id,
    )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    has_next = page < total_pages
    has_previous = page > 1

    deal_items = [DealResponse.model_validate(deal) for deal in items]

    return PaginatedResponse[DealResponse](
        items=deal_items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=has_next,
        has_previous=has_previous,
    )


@router.post(
    "",
    response_model=DealResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новую сделку (проект)",
)
async def create_deal(
    payload: DealCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Создать новую сделку (проект) и сразу добавить создателя как admin-участника.

    Важно:
    - Если фронтенд не передал список языков (payload.languages = None),
      мы считаем, что сделка по умолчанию русскоязычная и ставим ["ru"].
    - Это даёт предсказуемое поведение до того, как появится честный layout.
    """
    deal_repo = DealRepository(db)
    role_repo = ProjectRoleRepository(db)

    # Жёсткий дефолт языков: если клиент не указал языки, считаем ["ru"].
    # Для непрофессионального программиста:
    # - payload.languages может быть None или списком строк;
    # - мы нормализуем это в переменную effective_languages.
    effective_languages = payload.languages or ["ru"]

    deal = await deal_repo.create(
        tenant_id=user.tenant_id,
        name=payload.name,
        deal_type=payload.deal_type,
        jurisdiction=payload.jurisdiction,
        languages=effective_languages,
        pii_mode=payload.pii_mode,
        profile=payload.profile,
        playbook_version_id=payload.playbook_version_id,
        metadata_=payload.metadata_,
    )

    await role_repo.create_member(
        deal_id=deal.id,
        name=user.id,
        login=user.id,
        role="admin",
    )

    await db.commit()

    return DealResponse.model_validate(deal)


@router.get(
    "/{deal_id}",
    response_model=DealResponse,
    summary="Детали одной сделки",
)
async def get_deal(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Детали одной сделки по её идентификатору.

    Дополнительно обогащаем ответ человекочитаемым названием профиля
    модели (ModelConfig), который будет использован при анализе сделки.

    Приоритет выбора профиля такой:
    1) Если у сделки явно выбран профиль (deal.model_config_id),
       показываем его.
    2) Если для сделки профиль не выбран, но есть PlaybookVersion с
       model_config_id, показываем профиль, привязанный к плейбуку.
    3) Если нигде нет профиля, поле model_config_name в ответе будет пустым.
    """
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id)

    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Создаём DealResponse напрямую из ORM-объекта.
    # Флаг has_pending_manual_reclassifications берётся из поля модели Deal.
    deal_resp = DealResponse.model_validate(deal)

    model_config_name: str | None = None
    pb_repo = PlaybookRepository(db)

    # 1. Если у сделки явно выбран профиль модели, показываем его
    explicit_model_config_id = getattr(deal, "model_config_id", None)
    if explicit_model_config_id is not None:
        mc = await pb_repo.get_model_config(explicit_model_config_id)
        if mc is not None:
            model_config_name = mc.name
    # 2. Иначе пробуем взять профиль с PlaybookVersion
    elif deal.playbook_version_id:
        pv = await pb_repo.get_by_id(deal.playbook_version_id)
        if pv is not None and getattr(pv, "model_config_id", None):
            mc = await pb_repo.get_model_config(pv.model_config_id)
            if mc is not None:
                model_config_name = mc.name


    deal_resp.model_config_name = model_config_name

    return deal_resp


@router.delete(
    "/{deal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить сделку (проект)",
)
async def delete_deal(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Полное удаление сделки (проекта).
    """

    # Берём именно глобальную роль
    global_role = getattr(user, "global_role", None) or getattr(user, "role", None)
    if global_role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Not enough permissions to delete deal")

    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    await db.delete(deal)
    await db.commit()


@router.get(
    "/{deal_id}/documents",
    response_model=PaginatedResponse[DocumentResponse],
    summary="Список документов сделки",
)
async def list_deal_documents(
    deal_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    include_classification: bool = Query(
        False,
        description="Включить сортировку/данные по классификации",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Список документов для сделки с пагинацией.
    """
    doc_repo = DocumentRepository(db)

    items, total = await doc_repo.get_page_for_deal(
        deal_id=deal_id,
        page=page,
        per_page=per_page,
        include_classification=include_classification,
    )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    has_next = page < total_pages
    has_previous = page > 1

    doc_items = [map_document_to_response(doc) for doc in items]

    return PaginatedResponse[DocumentResponse](
        items=doc_items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=has_next,
        has_previous=has_previous,
    )


@router.get(
    "/{deal_id}/quarantine",
    response_model=list[DocumentResponse],
    summary="Get quarantined documents for a deal",
)
async def get_quarantine_docs(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Returns all documents in quarantine status for a deal.
    """
    doc_repo = DocumentRepository(db)
    docs = await doc_repo.get_quarantined(deal_id)
    return [map_document_to_response(d) for d in docs]


@router.post(
    "/{deal_id}/documents/upload",
    summary="Загрузить новые документы в сделку (через импорт-пайплайн)",
    response_model=dict,
)
async def upload_deal_documents(
    deal_id: UUID,
    files: List[UploadFile] = File(
        ...,
        description="Один или несколько файлов документов",
    ),
    folder_path: str | None = Query(
        default=None,
        description=(
            "Опциональный путь в Data Room, например '01. Corporate/Charter Docs'. "
            "Сейчас это поле используется только для UX; "
            "структура внутри ZIP для import_worker задаётся автоматически."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Загрузка новых документов в сделку через единый production-пайплайн импорта.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    tenant_id = str(deal.tenant_id)

    tmp_dir = tempfile.mkdtemp(prefix="mas_upload_")
    zip_path = os.path.join(tmp_dir, "upload_bundle.zip")

    try:
        with zipfile.ZipFile(
            zip_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for upload in files:
                file_bytes = await upload.read()
                arcname = upload.filename or "document"
                tmp_file_path = os.path.join(tmp_dir, arcname)
                with open(tmp_file_path, "wb") as f:
                    f.write(file_bytes)
                zf.write(tmp_file_path, arcname=arcname)

        celery_app.send_task(
            "workers.import_bundle",
            kwargs={
                "deal_id": str(deal_id),
                "tenant_id": tenant_id,
                "source_path": zip_path,
                "idempotency_key": None,
                "run_id": None,
            },
        )

    except Exception as e:
        try:
            for root, dirs, fnames in os.walk(tmp_dir, topdown=False):
                for name in fnames:
                    try:
                        os.remove(os.path.join(root, name))
                    except Exception:
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except Exception:
                        pass
            os.rmdir(tmp_dir)
        except Exception:
            pass

        logger.error(
            "Failed to enqueue import_bundle from upload",
            extra={
                "deal_id": str(deal_id),
                "tenant_id": tenant_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to enqueue import job",
        )

    return {
        "status": "queued",
        "files_uploaded": len(files),
    }


@router.post(
    "/{deal_id}/run",
    response_model=RunResponse,
    summary="Запустить анализ по сделке",
)
async def start_deal_run(
    deal_id: UUID,
    payload: RunCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Старт нового run для сделки через общую логику запуска.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    return await _start_run_core(deal_id, payload, db, user)


# ======================================================================
# НОВЫЙ ЭНДПОИНТ: привязка PlaybookVersion к сделке
# ======================================================================


class DealPlaybookUpdate(BaseModel):
    """
    Тело запроса для обновления playbook сделки.

    Передаём ID версии плейбука, которая должна использоваться
    по умолчанию при запуске анализа для этой сделки.
    """

    playbook_version_id: UUID


class DealModelConfigUpdate(BaseModel):
    """
    Тело запроса для обновления профиля модели (ModelConfig) для сделки.

    Здесь мы храним явный выбор профиля на уровне проекта.
    Если поле model_config_id = null, то специальный профиль
    для сделки сбрасывается, и при запуске анализа будет
    использован профиль, привязанный к PlaybookVersion.
    """

    model_config_id: UUID | None

class DealPrimaryLanguageUpdate(BaseModel):
    """
    Тело запроса для установки основного языка сделки.

    Правила:
    - primary_language должен входить в список languages сделки;
    - если передан null, основной язык сбрасывается.
    """

    primary_language: str | None


@router.patch(
    "/{deal_id}/playbook",
    response_model=DealResponse,
    summary="Установить playbook для сделки",
)
async def set_deal_playbook(
    deal_id: UUID,
    payload: DealPlaybookUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Привязывает конкретную версию playbook (PlaybookVersion) к сделке
    и пишет событие в журнал аудита.
    """
    # 1. Проверка прав в проекте
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)
    audit_repo = AuditRepository(db)

    # 2. Загружаем сделку
    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    old_playbook_version_id = deal.playbook_version_id
    new_playbook_version_id = payload.playbook_version_id

    # Если версия не меняется — ничего не делаем и не логируем
    if old_playbook_version_id == new_playbook_version_id:
        return DealResponse.model_validate(deal)

    # 3. Проверяем, что PlaybookVersion существует
    result = await db.execute(
        sa.select(PlaybookVersion).where(
            PlaybookVersion.id == new_playbook_version_id
        )
    )
    pv = result.scalar_one_or_none()
    if pv is None:
        raise HTTPException(
            status_code=404,
            detail="Playbook version not found",
        )

    # 4. Обновляем ссылку на playbook_version в сделке
    deal.playbook_version_id = new_playbook_version_id

    # 5. Логируем в аудит
    await audit_repo.log(
        tenant_id=deal.tenant_id,
        deal_id=deal.id,
        action="SET_DEAL_PLAYBOOK",
        actor=user.id,
        actor_role=getattr(user, "role", None),
        details={
            "old_playbook_version_id": str(old_playbook_version_id)
            if old_playbook_version_id
            else None,
            "new_playbook_version_id": str(new_playbook_version_id),
            "playbook_id": str(pv.playbook_id) if getattr(pv, "playbook_id", None) else None,
            "playbook_name": getattr(pv, "name", None),
            "semver": getattr(pv, "semver", None),
        },
    )

    await db.flush()
    await db.commit()
    await db.refresh(deal)

    return DealResponse.model_validate(deal)


@router.patch(
    "/{deal_id}/primary-language",
    response_model=DealResponse,
    summary="Установить основной язык сделки",
)
async def set_deal_primary_language(
    deal_id: UUID,
    payload: DealPrimaryLanguageUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Устанавливает (или сбрасывает) основной язык сделки.

    Правила:
    - менять основной язык могут только роли admin/editor;
    - если primary_language не null, он должен быть в Deal.languages;
    - при нарушении правил возвращаем 400/403/404.
    """
    # 1. Проверка прав: admin/editor
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)
    doc_repo = DocumentRepository(db)
    dv_repo = DocumentVersionRepository(db)

    # 2. Загружаем сделку
    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    # 3. Валидация значения
    new_lang = payload.primary_language
    deal_languages = list(deal.languages or [])

    if new_lang is not None:
        if not deal_languages:
            raise HTTPException(
                status_code=400,
                detail="Cannot set primary_language when deal has no languages",
            )
        if new_lang not in deal_languages:
            raise HTTPException(
                status_code=400,
                detail="primary_language must be one of deal languages",
            )

    # 4. Обновляем основной язык сделки
    old_lang = deal.primary_language
    deal.primary_language = new_lang

    # 5. Готовим список документов для рестарта (без вызова Celery пока)
    restart_items: list[tuple[str, str]] = []

    if new_lang is not None and new_lang != old_lang:
        # Берём документы по сделке в статусе LANGUAGE_SELECTION_REQUIRED
        docs_to_restart = await doc_repo.get_by_deal(
            deal_id=deal_id,
            status=DocumentStatus.LANGUAGE_SELECTION_REQUIRED.value,
        )

        for doc in docs_to_restart:
            latest_version = await dv_repo.get_latest(doc.id)
            if latest_version is None:
                continue

            # Переводим документ в PENDING через единый метод
            await doc_repo.update_status(
                doc.id,
                DocumentStatus.PENDING.value,
                processing_error_details=None,
            )

            restart_items.append((str(doc.id), str(latest_version.id)))

    # 6. Фиксируем изменения в БД
    await db.flush()
    await db.commit()
    await db.refresh(deal)

    # 7. После успешного коммита отправляем Celery-задания
    for document_id_str, version_id_str in restart_items:
        celery_app.send_task(
            "workers.build_primary_language_source",
            kwargs={
                "document_version_id": version_id_str,
                "document_id": document_id_str,
                "deal_id": str(deal.id),
                "tenant_id": str(deal.tenant_id),
                "run_id": None,
            },
        )

    return DealResponse.model_validate(deal)


@router.patch(
    "/{deal_id}/primary-language",
    response_model=DealResponse,
    summary="Установить основной язык сделки",
)
async def set_deal_primary_language(
    deal_id: UUID,
    payload: DealPrimaryLanguageUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Устанавливает (или сбрасывает) основной язык сделки.

    Правила:
    - менять основной язык могут только роли admin/editor;
    - если primary_language не null, он должен быть в Deal.languages;
    - при нарушении правил возвращаем 400/403/404.
    """
    # 1. Проверка прав: admin/editor
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)

    # 2. Загружаем сделку
    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    # 3. Валидация new_lang — как у тебя уже написано
    new_lang = payload.primary_language
    deal_languages = list(deal.languages or [])

    if new_lang is not None:
        if not deal_languages:
            raise HTTPException(
                status_code=400,
                detail="Cannot set primary_language when deal has no languages",
            )
        if new_lang not in deal_languages:
            raise HTTPException(
                status_code=400,
                detail="primary_language must be one of deal languages",
            )

    # 4. Обновляем основной язык сделки
    old_lang = deal.primary_language
    deal.primary_language = new_lang

    # 5. Если язык реально изменился и не null — пробуем "разбудить" документы,
    #    которые ранее остановились на LANGUAGE_SELECTION_REQUIRED.
    if new_lang is not None and new_lang != old_lang:
        doc_repo = DocumentRepository(db)
        dv_repo = DocumentVersionRepository(db)

        # Берём документы по сделке в статусе LANGUAGE_SELECTION_REQUIRED
        docs_to_restart = await doc_repo.get_by_deal(
            deal_id=deal_id,
            status=DocumentStatus.LANGUAGE_SELECTION_REQUIRED.value,
        )

        for doc in docs_to_restart:
            # Актуальная версия документа
            latest_version = await dv_repo.get_latest(doc.id)
            if latest_version is None:
                continue

            # Здесь мы не трогаем первичные артефакты напрямую:
            # build_primary_language_source сам построит primary_source_ref
            # и поставит PRIMARY_READY/запустит extract.

            # Логически можно оставить статус LANGUAGE_SELECTION_REQUIRED
            # до повторного прохода, но лучше перевести в PENDING, чтобы
            # явно показать, что документ "в работе".
            doc.status = DocumentStatus.PENDING.value

            # Пере-запускаем build_primary_language_source.
            # Имена kwargs и имя таски полностью совпадают с воркером.
            celery_app.send_task(
                "workers.build_primary_language_source",
                kwargs={
                    "document_version_id": str(latest_version.id),
                    "document_id": str(doc.id),
                    "deal_id": str(deal.id),
                    "tenant_id": str(deal.tenant_id),
                    "run_id": None,
                },
            )

    await db.flush()
    await db.commit()
    await db.refresh(deal)

    return DealResponse.model_validate(deal)


@router.get(
    "/{deal_id}/playbook-history",
    response_model=list[DealPlaybookHistoryItem],
    summary="История смен playbook-версии для сделки",
)
async def get_deal_playbook_history(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Возвращает историю смен playbook-версии для сделки на основе AuditLog.

    Использует записи AuditLog с action='SET_DEAL_PLAYBOOK'.
    """

    # Проверяем, что пользователь имеет доступ к сделке (как минимум просмотр)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "reviewer", "viewer"),
    )

    audit_repo = AuditRepository(db)
    logs = await audit_repo.get_by_deal(
        deal_id=deal_id,
        action="SET_DEAL_PLAYBOOK",
        limit=100,
    )

    items: list[DealPlaybookHistoryItem] = []
    for entry in logs:
        details = entry.details or {}
        items.append(
            DealPlaybookHistoryItem(
                created_at=entry.created_at,
                actor=str(entry.actor),
                actor_role=entry.actor_role,
                old_playbook_version_id=details.get("old_playbook_version_id"),
                new_playbook_version_id=details.get("new_playbook_version_id"),
                playbook_id=details.get("playbook_id"),
                playbook_name=details.get("playbook_name"),
                semver=details.get("semver"),
            )
        )

    return items




# ----------------------------------------------------------------------
# DEBUG-эндпоинты (оставлены как есть)
# ----------------------------------------------------------------------


@router.get(
    "/debug/all-deals",
    summary="Временный список всех сделок (debug)",
)
async def debug_list_all_deals(
    db: AsyncSession = Depends(get_db),
):
    repo = DealRepository(db)
    deals = await repo.get_all()
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "status": d.status,
        }
        for d in deals
    ]


class DebugDealCreate(BaseModel):
    name: str = "Test deal"
    deal_type: str | None = None


@router.post(
    "/debug/create-deal",
    summary="Создать тестовую сделку (debug)",
)
async def debug_create_deal(
    body: DebugDealCreate,
    db: AsyncSession = Depends(get_db),
):
    repo = DealRepository(db)
    deal = await repo.create(
        tenant_id=uuid.UUID(int=0),
        name=body.name,
        deal_type=body.deal_type,
        jurisdiction=None,
        languages=["ru"],
        pii_mode="local_only",
        profile="full",
        playbook_version_id=None,
        metadata_={},
    )
    await db.commit()
    return {
        "id": str(deal.id),
        "name": deal.name,
    }
