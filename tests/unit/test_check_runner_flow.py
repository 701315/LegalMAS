import uuid

import pytest
from sqlalchemy import select

from src.engine.runner import Runner
from src.engine.checks_runner import CheckRunner
from tests.util.mock_llm_client import MockLLMClient

from src.db.repositories.runner_repo import RunnerRepository
from src.db.uow import db_uow
from src.db.models.run import Run
from src.db.models.playbook import PlaybookVersion, ModelConfig


@pytest.mark.asyncio
async def test_check_runner_flow():
    """
    Интеграционный flow:
    1) Создаём Run (playbook_version + model_config) для сделки.
    2) Runner классифицирует документы сделки и сохраняет результаты checks
       с привязкой к этому run_id.
    3) CheckRunner (если нужен) выполняет checks по классифицированным документам.
    4) Проверяем summary и наличие записей в check_results.
    """
    test_deal_id = uuid.UUID("8ca1a0f5-bfd9-4ac1-8dcb-e0b685244696")

    # 1. Создаём run и подтягиваем playbook_version_id / model_config_id
    async with db_uow() as uow_setup:
        session = uow_setup.session

        pv_id = (
            await session.execute(
                select(PlaybookVersion.id).limit(1)
            )
        ).scalar_one()

        mc_id = (
            await session.execute(
                select(ModelConfig.id).limit(1)
            )
        ).scalar_one()

        run = Run(
            id=uuid.uuid4(),
            deal_id=test_deal_id,
            bundle_id=None,
            playbook_version_id=pv_id,
            model_config_id=mc_id,
            profile="full",
            status="running",
            total_checks=0,
            completed_checks=0,
            environment_hash=None,
            started_at=None,
            completed_at=None,
            risk_summary_ref=None,
            error_details=None,
        )
        session.add(run)
        # commit сделает db_uow при выходе

    run_id = run.id

    # 2. Классификация документов сделки через Runner
    async with db_uow() as uow_for_class:
        runner = Runner(uow_for_class)
        await runner.run_deal(test_deal_id, run_id)

    # 3. Запускаем CheckRunner (если он делает дополнительные шаги поверх уже записанных результатов)
    llm_client = MockLLMClient()
    check_runner = CheckRunner(llm_client)

    summary = await check_runner.run_deal_checks(test_deal_id, run_id)

    # 4. Проверяем, что есть результаты в check_results
    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_repo = uow.check_results

        docs = await runner_repo.get_non_duplicate_docs(test_deal_id)
        doc_ids = [d.id for d in docs]

        results = await check_repo.for_deal(run_id, doc_ids)

    # Базовые проверки пайплайна
    assert summary["processed_docs"] > 0
    assert summary["total_checks"] >= summary["failed_checks"]
    assert len(results) == summary["total_checks"]
