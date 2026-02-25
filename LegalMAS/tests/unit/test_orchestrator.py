TENANT_ID = "00000000-0000-0000-0000-000000000001"


def test_start_pipeline_delegates_to_run_async(mocker):
    from src.workers import orchestrator

    mock_run_async = mocker.patch("src.workers.orchestrator.run_async", return_value="run-id")
    mock_delay = mocker.patch("src.workers.import_worker.import_bundle.delay")

    result = orchestrator.start_pipeline("deal-id", TENANT_ID, "path/to.pdf")

    mock_run_async.assert_called_once()
    mock_delay.assert_called_once_with(
        deal_id="deal-id",
        tenant_id=TENANT_ID,
        source_path="path/to.pdf",
        run_id="run-id",
    )
    assert result["status"] == "started"
    assert result["run_id"] == "run-id"
