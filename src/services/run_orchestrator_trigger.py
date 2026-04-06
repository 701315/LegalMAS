# src/services/run_orchestrator_trigger.py

from mas_queue.celery_app import celery_app


def retrigger_run_pipeline(
    *,
    run_id: str | None,
    deal_id: str | None = None,
    tenant_id: str | None = None,
    force_reclassify: bool = False,
) -> None:
    """
    Безопасный retrigger оркестратора:
    - не делает ничего, если run_id не передан;
    - не решает, что запускать дальше — только будит workers.start_run_pipeline.
    """
    if not run_id:
        return

    celery_app.send_task(
        "workers.start_run_pipeline",
        kwargs={
            "run_id": run_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "force_reclassify": force_reclassify,
        },
    )

    