import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.api.main import app
from src.core.config import settings
from src.core.constants import DocumentStatus
from src.core.logging import deal_id_var, document_id_var, request_id_var
from src.db.models.bundle import Bundle
from src.db.models.document import Document
from src.db.models.result import CheckResult
from src.db.models.run import Run
from src.db.repositories import PlaybookRepository
from src.db.session import get_db

_db_lock = asyncio.Lock()


TEST_DEAL_ID = uuid.UUID("2e5857cb-0ffd-44f9-aa43-95ed5c999bf0")

# один общий engine и sessionmaker для тестов
test_engine = create_async_engine(settings.DATABASE_URL, future=True)
TestSession = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# глобальный лок для сериализации работы с БД в тестах
_db_lock = asyncio.Lock()


@pytest.fixture
def anyio_backend() -> str:
    # фиксируем backend, чтобы не ловить разные event loop’ы
    return "asyncio"


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSession() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with _db_lock:
            async with TestSession() as session:
                try:
                    yield session
                finally:
                    await session.rollback()

    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000099")


@pytest.fixture(autouse=True)
def reset_context_vars():
    request_id_var.set(None)
    deal_id_var.set(None)
    document_id_var.set(None)
    yield
    request_id_var.set(None)
    deal_id_var.set(None)
    document_id_var.set(None)


@pytest.fixture(scope="session", autouse=True)
def disable_downstream_tasks():
    """
    Отключить запуск downstream-тасок (PII Sanitizer, Structure Builder)
    в интеграционных тестах для изоляции стадий pipeline.
    """
    original_value = settings.DISABLE_DOWNSTREAM_TASKS
    os.environ["DISABLE_DOWNSTREAM_TASKS"] = "true"
    settings.DISABLE_DOWNSTREAM_TASKS = True

    yield

    settings.DISABLE_DOWNSTREAM_TASKS = original_value
    if "DISABLE_DOWNSTREAM_TASKS" in os.environ:
        os.environ.pop("DISABLE_DOWNSTREAM_TASKS")


# --- Sanity check для test_engine/TestSession --------------------------------


async def test__sanity_db_session(db_session: AsyncSession):
    repo = PlaybookRepository(db_session)
    pb = await repo.get_default()
    assert pb is not None


# --- Bundle fixture ----------------------------------------------------------


@pytest.fixture
async def sample_bundle_id(db_session: AsyncSession) -> uuid.UUID:
    """
    Минимальный bundle для тестовой сделки, создаётся через async db_session.
    """
    bundle_id = uuid.uuid4()
    bundle = Bundle(
        id=bundle_id,
        deal_id=TEST_DEAL_ID,
        source_type="zip",
        status="completed",
        file_count=0,
    )
    db_session.add(bundle)
    await db_session.commit()
    return bundle_id


# --- Document fixtures -------------------------------------------------------


@pytest.fixture
async def sample_doc_id(
    db_session: AsyncSession,
    sample_bundle_id: uuid.UUID,
) -> uuid.UUID:
    """
    Документ с нормальной классификацией (L2) и без structured_data.
    Используется для теста /documents/{id}/reclassify.
    """
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        deal_id=TEST_DEAL_ID,
        bundle_id=sample_bundle_id,
        filename="share_purchase_agreement_v3.pdf",
        folder_path="SPA",
        status=DocumentStatus.CLASSIFIED.value,
        doc_type="SPA",
        language="RU",
        page_count=42,
        classification_level="L2",
        classification_confidence=0.75,
        applicable_triggers=["coc", "consent"],
    )
    db_session.add(doc)
    # Коммит важен, чтобы документ был виден из HTTP‑эндпоинта.
    await db_session.commit()
    return doc_id


@dataclass
class StructuredDocContext:
    deal_id: uuid.UUID
    run_id: uuid.UUID
    document_id: uuid.UUID


from sqlalchemy import select
from src.db.models.playbook import PlaybookVersion, ModelConfig

@pytest.fixture
async def model_config_id(db_session: AsyncSession) -> uuid.UUID:
    """
    Минимальная ModelConfig для тестов.
    """
    # пробуем найти существующую
    row = await db_session.execute(select(ModelConfig.id).limit(1))
    existing = row.scalar_one_or_none()
    if existing is not None:
        return existing

    mc = ModelConfig(
        id=uuid.uuid4(),
        name="test-model-config",
        embeddings_primary="intfloat/multilingual-e5-large",
        embeddings_fallback="cointegrated/LaBSE",
        retrieval_config={},
        scoring_config={},
    )
    db_session.add(mc)
    await db_session.commit()
    return mc.id


@pytest.fixture
async def playbook_version_id(
    db_session: AsyncSession,
    model_config_id: uuid.UUID,
) -> uuid.UUID:
    """
    Минимальная PlaybookVersion, привязанная к ModelConfig.
    """
    row = await db_session.execute(
        select(PlaybookVersion.id).where(PlaybookVersion.model_config_id == model_config_id).limit(1)
    )
    existing = row.scalar_one_or_none()
    if existing is not None:
        return existing

    pb = PlaybookVersion(
        id=uuid.uuid4(),
        name="M&A_RU_TEST",
        semver="0.0.1-test",
        git_commit=None,
        yaml_sha256=None,
        compiled_checks={},
        status="default",
        model_config_id=model_config_id,
    )
    db_session.add(pb)
    await db_session.commit()
    return pb.id







@pytest.fixture
async def sample_structured_doc_context(
    db_session: AsyncSession,
    sample_bundle_id: uuid.UUID,
    playbook_version_id: uuid.UUID,
    model_config_id: uuid.UUID,
) -> StructuredDocContext:
    """
    Документ с хотя бы одним StructuredValue в рамках конкретного run.
    """
    deal_id = TEST_DEAL_ID

    run = Run(
        id=uuid.uuid4(),
        deal_id=deal_id,
        bundle_id=sample_bundle_id,
        playbook_version_id=playbook_version_id,
        model_config_id=model_config_id,
        environment_hash="test-env",
        profile="core",
        status="completed",
        total_checks=10,
        completed_checks=10,
    )
    db_session.add(run)
    await db_session.flush()

    doc = Document(
        id=uuid.uuid4(),
        deal_id=deal_id,
        bundle_id=sample_bundle_id,
        filename="lease_agreement_main.pdf",
        folder_path="Leases",
        status=DocumentStatus.CLASSIFIED.value,
        doc_type="LeaseAgreement",
        language="RU",
        page_count=18,
        classification_level="L3",
        classification_confidence=0.88,
        applicable_triggers=["reencumbrance"],
    )
    db_session.add(doc)
    await db_session.flush()

    result = CheckResult(
        id=uuid.uuid4(),
        run_id=run.id,
        document_id=doc.id,
        check_id="amount_001",
        check_name="Total amount",
        result="fail",
        severity="high",
        value_text="5 000 000 ₽",
        confidence=0.91,
        detector_used="hybrid",
        quality_flags={},
        structured_data={"amount": 5000000, "currency": "RUB"},
        conditional_check_triggered=False,
        trigger_name=None,
        qc_status="pending",
    )
    db_session.add(result)

    await db_session.commit()

    return StructuredDocContext(
        deal_id=deal_id,
        run_id=run.id,
        document_id=doc.id,
    )




@pytest.fixture
async def sample_empty_structured_doc_context(
    db_session: AsyncSession,
    sample_bundle_id: uuid.UUID,
) -> StructuredDocContext:
    """
    Документ, для которого в данном run нет structured_data.
    """
    deal_id = TEST_DEAL_ID
    run_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    # Run
    run = Run(
        id=run_id,
        deal_id=deal_id,
        status="completed",
        profile="core",
        total_checks=0,
        completed_checks=0,
    )
    db_session.add(run)

    # документ без CheckResult со structured_data
    doc = Document(
        id=doc_id,
        deal_id=deal_id,
        bundle_id=sample_bundle_id,
        filename="cover_letter_no_structured.pdf",
        folder_path="Misc",
        status=DocumentStatus.CLASSIFIED.value,
        doc_type="Generic",
        language="RU",
        page_count=1,
        classification_level="L0",
        classification_confidence=0.0,
        applicable_triggers=[],
    )
    db_session.add(doc)

    await db_session.commit()

    return StructuredDocContext(
        deal_id=deal_id,
        run_id=run_id,
        document_id=doc_id,
    )


# --- Run-related fixtures ----------------------------------------------------


@pytest.fixture
async def sample_run_id(
    db_session: AsyncSession,
    sample_bundle_id: uuid.UUID,
    playbook_version_id: uuid.UUID,
    model_config_id: uuid.UUID,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    run = Run(
        id=run_id,
        deal_id=TEST_DEAL_ID,
        bundle_id=sample_bundle_id,
        playbook_version_id=playbook_version_id,
        model_config_id=model_config_id,
        environment_hash="test-env",
        profile="core",
        status="completed",
        total_checks=10,
        completed_checks=10,
    )
    db_session.add(run)

    doc = Document(
        id=doc_id,
        deal_id=TEST_DEAL_ID,
        bundle_id=sample_bundle_id,
        filename="run_doc.pdf",
        folder_path="SPA",
        status=DocumentStatus.CLASSIFIED.value,
        doc_type="SPA",
        language="RU",
        page_count=10,
        classification_level="L2",
        classification_confidence=0.75,
        applicable_triggers=["coc"],
    )
    db_session.add(doc)

    result = CheckResult(
        id=uuid.uuid4(),
        run_id=run_id,
        document_id=doc_id,
        check_id="dummy",
        check_name="dummy",
        result="pass",
        severity="low",
        value_text=None,
        evidence_ref=None,
        confidence=0.9,
        detector_used="test",
        quality_flags={},
        conditional_check_triggered=False,
        trigger_name=None,
        qc_status="pending",
        qc_by=None,
        qc_comment=None,
        qc_at=None,
    )
    db_session.add(result)

    await db_session.commit()
    return run_id



@pytest.fixture
async def run_with_low_conf_docs_id(
    db_session: AsyncSession,
    sample_bundle_id: uuid.UUID,
) -> uuid.UUID:
    """
    Run с несколькими low-confidence документами, связанными через CheckResult.
    """
    run_id = uuid.uuid4()

    run = Run(
        id=run_id,
        deal_id=TEST_DEAL_ID,
        status="completed",
        profile="core",
        total_checks=10,
        completed_checks=10,
    )
    db_session.add(run)

    for conf in (0.55, 0.31, 0.48, 0.22):
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            deal_id=TEST_DEAL_ID,
            bundle_id=sample_bundle_id,
            filename=f"unknown_doc_conf_{conf}.pdf",
            folder_path="Unknown",
            status=DocumentStatus.CLASSIFIED.value,
            doc_type="Generic",
            language="RU",
            page_count=5,
            classification_level="L1",
            classification_confidence=conf,
            applicable_triggers=[],
        )
        db_session.add(doc)

        result = CheckResult(
            id=uuid.uuid4(),
            run_id=run_id,
            document_id=doc_id,
            check_id="dummy",
            check_name="dummy",
            result="pass",
            severity="low",
            value_text=None,
            confidence=0.9,
            detector_used="test",
            quality_flags={},
        )
        db_session.add(result)

    await db_session.commit()
    return run_id
