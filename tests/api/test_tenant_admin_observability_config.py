# tests/api/test_tenant_admin_observability_config.py
"""
Unit-тесты на observability URL helpers в tenant_admin endpoint.

Проверяем:
- internal URL helpers читают из settings и нормализуют trailing slash;
- _build_external_tools_response собирает корректный ответ для superadmin;
- tenant_admin получает только legacy-поля, services и dashboards пустые.
"""

from api.endpoints import tenant_admin


def test_internal_url_helpers_strip_trailing_slash_and_follow_settings(
    monkeypatch,
):
    monkeypatch.setattr(
        tenant_admin.settings, "PROMETHEUS_INTERNAL_URL", "http://127.0.0.1:19090/"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "LOKI_INTERNAL_URL", "http://127.0.0.1:13100/"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "ALERTMANAGER_INTERNAL_URL", "http://127.0.0.1:19093/"
    )

    assert tenant_admin._prometheus_base_url() == "http://127.0.0.1:19090"
    assert tenant_admin._loki_base_url() == "http://127.0.0.1:13100"
    assert tenant_admin._alertmanager_base_url() == "http://127.0.0.1:19093"


def test_internal_url_helpers_work_without_trailing_slash(monkeypatch):
    monkeypatch.setattr(
        tenant_admin.settings, "PROMETHEUS_INTERNAL_URL", "http://127.0.0.1:19090"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "LOKI_INTERNAL_URL", "http://127.0.0.1:13100"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "ALERTMANAGER_INTERNAL_URL", "http://127.0.0.1:19093"
    )

    assert tenant_admin._prometheus_base_url() == "http://127.0.0.1:19090"
    assert tenant_admin._loki_base_url() == "http://127.0.0.1:13100"
    assert tenant_admin._alertmanager_base_url() == "http://127.0.0.1:19093"


def test_build_external_tools_superadmin_uses_external_urls(monkeypatch):
    monkeypatch.setattr(
        tenant_admin.settings, "GRAFANA_EXTERNAL_URL", "http://obs.example:13000"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "PROMETHEUS_EXTERNAL_URL", "http://obs.example:19090"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "ALERTMANAGER_EXTERNAL_URL", "http://obs.example:19093"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "MINIO_CONSOLE_EXTERNAL_URL", "http://obs.example:19001"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "API_DOCS_EXTERNAL_URL", "http://obs.example:8000/docs"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "OLLAMA_EXTERNAL_URL", "http://obs.example:11434/"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "LOKI_EXTERNAL_URL", "http://obs.example:13100"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "TEMPO_EXTERNAL_URL", "http://obs.example:13200"
    )

    response = tenant_admin._build_external_tools_response(is_superadmin=True)

    dashboards = {d.uid: d for d in response.dashboards}
    services = {s.key: s for s in response.services}

    assert response.is_superadmin is True
    assert response.grafana_url == "http://obs.example:13000"
    assert response.prometheus_url == "http://obs.example:19090"
    assert response.alertmanager_url == "http://obs.example:19093"

    # Dashboards строятся на основе GRAFANA_EXTERNAL_URL
    assert (
        dashboards["operations-overview"].url
        == "http://obs.example:13000/d/operations-overview"
    )
    assert (
        dashboards["legalmas-pipeline"].url
        == "http://obs.example:13000/d/legalmas-pipeline"
    )
    assert (
        dashboards["slo-overview"].url == "http://obs.example:13000/d/slo-overview"
    )
    assert dashboards["logs-explorer"].url == "http://obs.example:13000/explore"

    # Прямые сервисные ссылки
    assert services["grafana"].url == "http://obs.example:13000"
    assert services["prometheus"].url == "http://obs.example:19090"
    assert services["alertmanager"].url == "http://obs.example:19093"
    assert services["minio"].url == "http://obs.example:19001"
    assert services["api_docs"].url == "http://obs.example:8000/docs"

    # Ollama: trailing slash обрезается и добавляется /api/tags
    assert services["ollama"].url == "http://obs.example:11434/api/tags"

    # Tempo и Loki через Grafana Explore deep links
    assert "datasource%22:%22tempo%22" in services["tempo"].url
    assert "datasource%22:%22loki%22" in services["loki"].url
    assert services["tempo"].url.startswith("http://obs.example:13000/explore")
    assert services["loki"].url.startswith("http://obs.example:13000/explore")


def test_build_external_tools_tenant_admin_returns_legacy_only(monkeypatch):
    monkeypatch.setattr(
        tenant_admin.settings, "GRAFANA_EXTERNAL_URL", "http://obs.example:13000"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "PROMETHEUS_EXTERNAL_URL", "http://obs.example:19090"
    )
    monkeypatch.setattr(
        tenant_admin.settings, "ALERTMANAGER_EXTERNAL_URL", "http://obs.example:19093"
    )

    response = tenant_admin._build_external_tools_response(is_superadmin=False)

    assert response.is_superadmin is False
    assert response.grafana_url == "http://obs.example:13000"
    assert response.prometheus_url == "http://obs.example:19090"
    assert response.alertmanager_url == "http://obs.example:19093"
    assert response.services == []
    assert response.dashboards == []


    