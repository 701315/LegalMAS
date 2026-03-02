import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DocumentStatus
from src.db.models.bundle import Bundle
from src.db.models.deal import Deal
from src.db.models.relation import DocumentFamily
from src.db.repositories import DocumentRepository
from src.db.uow import db_uow
from src.workers.relations_worker import build_relations


@pytest.mark.asyncio
async def test_relations_worker_basic_flow(tenant_id):
    """
    Интеграционный сценарий:
    - создаём deal + bundle
    - SPA (master, L3)
    - Appendix (Generic, L1)
    - SPA duplicate (тот же sha256)
    Проверяем, что воркер отрабатывает без ошибок и создаёт хотя бы одну семью.
    """
    async with db_uow() as uow:
        db: AsyncSession = uow.session

        # Deal
        deal = Deal(
            id=uuid.uuid4(),
            tenant_id=tenant_id,  # tenant_id уже UUID
            name="Test deal for relations",
        )
        db.add(deal)
        await db.flush()

        # Bundle
        bundle = Bundle(
            id=uuid.uuid4(),
            deal_id=deal.id,
            source_type="local",
            status="completed",
            file_count=0,
        )
        db.add(bundle)
        await db.flush()

        doc_repo = DocumentRepository(db)

        spa = await doc_repo.create(
            deal_id=deal.id,
            bundle_id=bundle.id,
            filename="SharePurchaseAgreement.pdf",
            folder_path="01. Transaction",
            sha256_file="hash-spa",
            status=DocumentStatus.CLASSIFIED.value,
        )
        appendix = await doc_repo.create(
            deal_id=deal.id,
            bundle_id=bundle.id,
            filename="Appendix 1 to SharePurchaseAgreement.pdf",
            folder_path="01. Transaction",
            sha256_file="hash-app",
            status=DocumentStatus.CLASSIFIED.value,
        )
        duplicate = await doc_repo.create(
            deal_id=deal.id,
            bundle_id=bundle.id,
            filename="SharePurchaseAgreement_copy.pdf",
            folder_path="02. Copies",
            sha256_file="hash-spa",  # тот же хеш
            status=DocumentStatus.CLASSIFIED.value,
        )

        spa.classification_level = "L3"
        spa.yaml_instruction_available = True
        spa.applicable_triggers = ["change_of_control"]
        appendix.classification_level = "L1"
        duplicate.classification_level = "L2"

        await db.flush()

        deal_id = str(deal.id)

    # Вызов Celery-task: используем .run(), так же как для других async-тасок
    result = await build_relations.run(
        deal_id=deal_id,
        tenant_id=str(tenant_id),
    )

    assert result["total_documents"] >= 2
    assert result["families"] >= 1


@pytest.mark.asyncio
async def test_relations_worker_classification_awareness(tenant_id):
    """
    Проверяем, что воркер сохраняет master_classification_level в document_families
    в соответствии с логикой FamilyBuilder (L3 предпочтительнее L2).
    """
    async with db_uow() as uow:
        db: AsyncSession = uow.session

        deal = Deal(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name="Deal for classification awareness",
        )
        db.add(deal)
        await db.flush()

        bundle = Bundle(
            id=uuid.uuid4(),
            deal_id=deal.id,
            source_type="local",
            status="completed",
            file_count=0,
        )
        db.add(bundle)
        await db.flush()

        doc_repo = DocumentRepository(db)

        doc_l3 = await doc_repo.create(
            deal_id=deal.id,
            bundle_id=bundle.id,
            filename="SPA_L3.pdf",
            folder_path="01. Transaction",
            sha256_file="hash-l3",
            status=DocumentStatus.CLASSIFIED.value,
        )
        doc_l2 = await doc_repo.create(
            deal_id=deal.id,
            bundle_id=bundle.id,
            filename="SPA_L2.pdf",
            folder_path="01. Transaction",
            sha256_file="hash-l2",
            status=DocumentStatus.CLASSIFIED.value,
        )

        doc_l3.classification_level = "L3"
        doc_l2.classification_level = "L2"
        await db.flush()

        deal_id_str = str(deal.id)

        # Запускаем воркер в том же event loop
        result = await build_relations.run(
            deal_id=deal_id_str,
            tenant_id=str(tenant_id),
        )

        assert result["families"] >= 1

        # Читаем семьи через тот же AsyncSession
        families = (
            (await db.execute(sa.select(DocumentFamily).where(DocumentFamily.deal_id == deal.id)))
            .scalars()
            .all()
        )

        assert families
        levels = {f.master_classification_level for f in families}
        assert "L3" in levels
