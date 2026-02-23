import time
import uuid

from src.queue.async_helpers import get_worker_session, run_async
from src.db.repositories import DealRepository, RunRepository, DocumentRepository, ResultRepository
from src.workers.orchestrator import start_pipeline

TENANT_ID = "00000000-0000-0000-0000-000000000001"
TEST_PDF_PATH = r"tests\fixtures\test_spa.pdf"  # если путь другой — поправь


async def _create_deal() -> str:
    async with get_worker_session() as session:
        repo = DealRepository(session)
        deal = await repo.create(
            tenant_id=uuid.UUID(TENANT_ID),
            name="DEBUG Vertical Slice Deal",
            deal_type="SPA",
        )
        print("DEBUG: created deal", deal.id)
        return str(deal.id)


async def _inspect_state(deal_id: str, run_id: str):
    async with get_worker_session() as session:
        run_repo = RunRepository(session)
        doc_repo = DocumentRepository(session)
        result_repo = ResultRepository(session)

        run = await run_repo.get_by_id(uuid.UUID(run_id))
        docs = await doc_repo.get_by_deal(uuid.UUID(deal_id))
        results = await result_repo.get_by_run(uuid.UUID(run_id))

        print(
            "DEBUG STATE:",
            f"run_status={getattr(run, 'status', None)}",
            f"docs={len(docs)}",
            f"results={len(results)}",
        )
        if docs:
            print("DEBUG STATE: first doc id/status", docs[0].id, docs[0].status)


from src.queue.celery_app import celery_app

def main():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)

    deal_id = run_async(_create_deal())
    print("DEBUG: created deal", deal_id)

    print("DEBUG: calling start_pipeline")
    result = start_pipeline(
        deal_id=deal_id,
        tenant_id=TENANT_ID,
        source_path=TEST_PDF_PATH,
    )
    print("DEBUG: start_pipeline result", result)

    run_id = result["run_id"]

    for i in range(10):
        print(f"DEBUG: poll {i+1}")
        run_async(_inspect_state(deal_id, run_id))
        time.sleep(2)



if __name__ == "__main__":
    main()
