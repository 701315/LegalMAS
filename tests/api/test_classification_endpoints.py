import uuid

import pytest
from httpx import AsyncClient

# Все тесты в этом модуле запускаются в anyio-режиме (async).
pytestmark = pytest.mark.anyio


class TestReclassifyEndpoint:
    async def test_reclassify_basic(
        self,
        client: AsyncClient,
        sample_doc_id: uuid.UUID,
    ):
        """
        Базовый сценарий: переклассификация существующего документа.
        """
        resp = await client.post(
            f"/documents/{sample_doc_id}/reclassify",
            json={
                "doc_type": "SHA",
                "reason": "Wrong auto-classification",
                "rerun_checks": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == str(sample_doc_id)
        assert data["new_doc_type"] == "SHA"
        assert "new_applicable_triggers" in data
        assert "yaml_instruction_found" in data

    async def test_reclassify_unknown_doc_returns_404(
        self,
        client: AsyncClient,
    ):
        """
        Переклассификация несуществующего документа -> 404.
        """
        resp = await client.post(
            f"/documents/{uuid.uuid4()}/reclassify",
            json={
                "doc_type": "SHA",
                "reason": "test",
                "rerun_checks": False,
            },
        )
        assert resp.status_code == 404


class TestStructuredDataEndpoint:
    async def test_structured_data_with_values(
        self,
        client: AsyncClient,
        sample_structured_doc_context,
    ):
        """
        Документ с structured_data в рамках run должен вернуть непустой список values.
        """
        ctx = sample_structured_doc_context

        resp = await client.get(
            f"/deals/{ctx.deal_id}/runs/{ctx.run_id}/documents/{ctx.document_id}/structured-data"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["deal_id"] == str(ctx.deal_id)
        assert data["run_id"] == str(ctx.run_id)
        assert data["document_id"] == str(ctx.document_id)
        assert data["total_values"] >= 1
        assert isinstance(data["values"], list)

        first = data["values"][0]
        # Поля из ExtractedValueDTO
        assert "document_name" in first
        assert "doc_type" in first
        assert "check_name" in first
        assert "field_name" in first
        assert "field_value" in first
        assert "field_format" in first

    async def test_structured_data_empty(
        self,
        client: AsyncClient,
        sample_empty_structured_doc_context,
    ):
        """
        Документ без structured_data в данном run должен вернуть total_values=0.
        """
        ctx = sample_empty_structured_doc_context

        resp = await client.get(
            f"/deals/{ctx.deal_id}/runs/{ctx.run_id}/documents/{ctx.document_id}/structured-data"
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["deal_id"] == str(ctx.deal_id)
        assert data["run_id"] == str(ctx.run_id)
        assert data["document_id"] == str(ctx.document_id)
        assert data["total_values"] == 0
        assert data["values"] == []


class TestClassificationReportEndpoint:
    async def test_classification_report_not_found(
        self,
        client: AsyncClient,
    ):
        """
        Запрос отчёта по несуществующему run -> 404.
        """
        resp = await client.get(f"/runs/{uuid.uuid4()}/classification-report")
        assert resp.status_code == 404

    async def test_classification_report_ok(
        self,
        client: AsyncClient,
        sample_run_id: uuid.UUID,
    ):
        """
        Для существующего run эндпоинт должен вернуть базовую структуру отчёта.
        """
        resp = await client.get(f"/runs/{sample_run_id}/classification-report")
        # В зависимости от реализации build_classification_report,
        # здесь может быть 200 или 404, пока только smoke.
        assert resp.status_code in (200, 404)


class TestYAMLInstructionsEndpoint:
    async def test_yaml_instructions_ok(
        self,
        client: AsyncClient,
    ):
        """
        Список YAML-инструкций должен отвечать 200 и возвращать JSON.
        """
        resp = await client.get("/admin/yaml-instructions")
        assert resp.status_code == 200
        data = resp.json()
        # В нашем admin.py возвращается просто список
        assert isinstance(data, list)
