# src/api/endpoints/documents.py

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
from ..schemas.deals import DealResponse, DealCreate
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

    Сейчас без фильтрации по tenant_id и статусу:
    возвращаются все сделки, отсортированные по created_at DESC.

    TODO (после внедрения auth и ACL):
    - фильтровать сделки по tenant_id и/или по участию пользователя в проекте,
      чтобы пользователь видел только "свои" проекты.
    """
    repo = DealRepository(db)

    items, total = await repo.get_page(
        page=page,
        per_page=per_page,
        status=status,
        tenant_id=tenant_id,
    )

    # считаем метаданные пагинации
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    has_next = page < total_pages
    has_previous = page > 1

    # маппим ORM-модели Deal → DealResponse
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
    Создать новую сделку (проект) и сразу добавить создателя
    как admin-участника этого проекта.

    Логика:
    - создаём Deal в таблице deals;
    - через ProjectRoleRepository создаём запись в deal_members:
      (deal_id=deal.id, user_id=user.id, login=user.id, role="admin");
    - коммитим транзакцию один раз, чтобы сделка и роль сохранились вместе.
    """
    deal_repo = DealRepository(db)
    role_repo = ProjectRoleRepository(db)

    # 1. Создаём сделку
    deal = await deal_repo.create(
        tenant_id=user.tenant_id,
        name=payload.name,
        deal_type=payload.deal_type,
        jurisdiction=payload.jurisdiction,
        languages=payload.languages,
        pii_mode=payload.pii_mode,
        profile=payload.profile,
        playbook_version_id=payload.playbook_version_id,
        metadata_=payload.metadata_,
    )

    # 2. Добавляем создателя как admin проекта
    # Сейчас user.id — это строка (логин) из dev-auth,
    # поэтому используем её и как user_id, и как login.
    await role_repo.create_member(
        deal_id=deal.id,
        name=user.id,   # временно используем id как name; позже можно заменить на реальное имя
        login=user.id,
        role="admin",
    )

    # 3. Фиксируем и сделку, и membership одной транзакцией
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

    TODO:
    - после внедрения auth/ACL имеет смысл проверять, что текущий пользователь
      имеет доступ к этой сделке (участник проекта/tenant).
    """
    repo = DealRepository(db)
    deal = await repo.get_by_id(deal_id)

    if deal is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Deal not found")

    return DealResponse.model_validate(deal)


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

    TODO:
    - После появления полной ACL можно добавить проверку, что пользователь
      имеет право смотреть документы этой сделки (viewer/editor/admin).
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

    TODO:
    - аналогично, позже можно ограничить доступ к карантинным документам
      только участникам проекта.
    """
    doc_repo = DocumentRepository(db)
    docs = await doc_repo.get_quarantined(deal_id)
    return [map_document_to_response(d) for d in docs]


@router.post(
    "/{deal_id}/documents/upload",
    summary="Загрузить новые документы в сделку",
    response_model=list[DocumentResponse],
)
async def upload_deal_documents(
    deal_id: UUID,
    files: List[UploadFile] = File(..., description="Один или несколько файлов документов"),
    folder_path: str | None = Query(
        default=None,
        description="Опциональный путь в Data Room, например '01. Corporate/Charter Docs'",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Загрузка новых документов в сделку.

    Шаги:
    1. Проверяем права пользователя (admin/editor) на проект.
    2. Создаём Bundle для этой операции загрузки.
    3. Для каждого файла:
       - создаём Document,
       - сохраняем файл в ArtifactStore,
       - создаём DocumentVersion с original_ref,
       - оставляем статус документа PENDING.
    4. Возвращаем список созданных документов.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    # Проверяем роль пользователя в проекте
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    # Репозитории
    bundle_repo = BundleRepository(db)
    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)

    # Создаём bundle для этой загрузки
    bundle = await bundle_repo.create(
        deal_id=deal_id,
        source_type="local",
        idempotency_key=None,
    )

    store = ArtifactStore()
    created_docs: list[DocumentResponse] = []

    for upload in files:
        # Создаём запись документа в БД
        doc = await doc_repo.create(
            deal_id=deal_id,
            bundle_id=bundle.id,
            filename=upload.filename,
            folder_path=folder_path,
            sha256_file=None,
            status=DocumentStatus.PENDING.value,
        )

        # Читаем байты файла
        file_bytes = await upload.read()

        # Сохраняем оригинальный файл в ArtifactStore
        original_path = ArtifactPath.original(
            str(user.tenant_id),
            str(deal_id),
            str(doc.id),
        )
        original_ref = store.put_file(
            original_path,
            file_bytes,
            content_type=upload.content_type or "application/octet-stream",
        )

        # Создаём версию документа с ссылкой на оригинал
        await ver_repo.create(
            document_id=doc.id,
            version_num=1,
            original_ref=original_ref,
        )

        # Добавляем документ в результат, используя общий маппер
        created_docs.append(map_document_to_response(doc))

    # Обновляем количество файлов в bundle и помечаем его как завершённый
    await bundle_repo.increment_file_count(bundle.id, delta=len(files))
    await bundle_repo.mark_completed(bundle.id)

    # Фиксируем изменения
    await db.commit()

    return created_docs



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

    URL удобен для фронта: POST /api/v1/deals/{deal_id}/run.
    Вся бизнес-логика (reclassify / run_checks, Celery и пр.) находится
    в _start_run_core из endpoints/runs.py.

    ВАЖНО:
    - Здесь добавлена проверка роли пользователя в проекте.
    - Запуск run разрешён только для ролей "admin" и "editor".
    - Если роль другая (или нет роли) — вернётся HTTP 403 Forbidden.
    """
    # Проверяем, что у пользователя есть право запускать анализ для этой сделки
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    # Если проверка прошла, запускаем общий механизм старта run
    return await _start_run_core(deal_id, payload, db, user)


from db.repositories.deal_repo import DealRepository
from db.session import get_db
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

@router.get(
    "/debug/all-deals",
    summary="Временный список всех сделок (debug)",
)
async def debug_list_all_deals(
    db: AsyncSession = Depends(get_db),
):
    repo = DealRepository(db)
    deals = await repo.get_all()
    # get_all уже есть в DealRepository
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "status": d.status,
        }
    for d in deals
    ]

from pydantic import BaseModel
import uuid
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from db.repositories.deal_repo import DealRepository

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
        metadata_={},        # важно: параметр называется metadata_
    )
    await db.commit()
    return {
        "id": str(deal.id),
        "name": deal.name,
    }
