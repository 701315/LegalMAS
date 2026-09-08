# src/api/endpoints/tenant_admin.py

"""
Tenant Admin Dashboard API.

Administrative panel for tenant_admin.
Each tenant_admin can only see data belonging to their tenant.
superadmin can view any tenant via tenant_id query param.

Endpoints:
    GET /api/v1/tenant/dashboard                     — summary statistics
    GET /api/v1/tenant/metrics                       — proxy to Prometheus
    GET /api/v1/tenant/logs                          — proxy to Loki
    GET /api/v1/tenant/projects/{deal_id}/insights   — summary + error history from PostgreSQL
"""

from __future__ import annotations

import json
import math
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.rate_limit import check_admin_rate_limit, check_logs_rate_limit
from core.config import settings
from core.logging import get_logger
from db.models.deal import Deal
from db.models.deal_member import DealMember
from db.models.document import Document
from db.models.ops import DLQRecord
from db.models.run import Run
from db.models.user import User
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.run_repo import RunRepository
from db.repositories.tenant_locale_policy_repo import TenantLocalePolicyRepository
from db.models.tenant_result_locale_policy import TenantResultLocalePolicy
from core.i18n.result_locales import get_supported_result_locales
from db.session import get_db, get_session
from ops.metrics import get_metrics

logger = get_logger(__name__)

router = APIRouter(prefix="/tenant", tags=["tenant-admin"])

PROMETHEUS_TIMEOUT_SECONDS = 10.0
LOKI_TIMEOUT_SECONDS = 15.0
ALERTMANAGER_TIMEOUT_SECONDS = 5.0
MAX_LOG_LIMIT = 500
# Upper bound of explicitly defined period. 30 days is a compromise between
# usefulness and protection against accidental humongous queries.
MAX_LOG_SINCE_MINUTES = 43_200  # 30 days

OPERATIONAL_LEVELS = {"warning", "error", "critical"}
OPERATIONAL_ALLOWED_INFO_LOGGERS: set[str] = set()

GROUP_SIMILAR_MIN_COUNT = 2

LOKI_FETCH_MULTIPLIER = 3
LOKI_FETCH_HARD_CAP = 5_000

# Maximum number of "troubled" records returned in drill-down.
# This is a long-term historical slice from DB — 100 records is sufficient.
PROJECT_ERROR_LIMIT = 100

# Bounded query cost for Loki:
# Automatically lower the limit when the time window is too wide.
_LOKI_COST_CAPS: list[tuple[int, int]] = [
    (43_200, 100),  # >= 30 days or since_minutes=0 ("all time")
    (10_080, 200),  # >= 7 days
]

_LOKI_SLOW_QUERY_THRESHOLD_SECONDS = 3.0


# ── Loki cost controls / metrics ────────────────────────────────────────────

def _apply_loki_cost_cap(since_minutes: int, requested_limit: int) -> tuple[int, bool]:
    """
    Apply a cap to the limit depending on the width of the time window.

    since_minutes == 0 is treated as "all time", but is actually
    capped by MAX_LOG_SINCE_MINUTES.
    """
    effective_since = since_minutes if since_minutes > 0 else MAX_LOG_SINCE_MINUTES

    for min_minutes, max_limit in _LOKI_COST_CAPS:
        if effective_since >= min_minutes:
            if requested_limit > max_limit:
                return max_limit, True
            return requested_limit, False

    return requested_limit, False


def _since_minutes_bucket(since_minutes: int) -> str:
    effective_since = since_minutes if since_minutes > 0 else MAX_LOG_SINCE_MINUTES
    if effective_since >= 43_200:
        return "30d"
    if effective_since >= 10_080:
        return "7d"
    if effective_since >= 1_440:
        return "1d"
    return "lt1d"


def _observe_admin_logs_query_duration(since_minutes: int, duration_seconds: float) -> None:
    try:
        get_metrics().admin_logs_query_duration_seconds.labels(
            since_minutes_bucket=_since_minutes_bucket(since_minutes),
        ).observe(duration_seconds)
    except Exception:
        # Metrics must not break the response pipeline.
        pass


def _strip_trailing_slash(url: str) -> str:
    """Normalize base URL by stripping the trailing slash."""
    return str(url or "").rstrip("/")


def _prometheus_base_url() -> str:
    """Internal Prometheus base URL for backend-to-backend queries."""
    return _strip_trailing_slash(settings.PROMETHEUS_INTERNAL_URL)


def _loki_base_url() -> str:
    """Internal Loki base URL for backend-to-backend queries."""
    return _strip_trailing_slash(settings.LOKI_INTERNAL_URL)


def _alertmanager_base_url() -> str:
    """Internal Alertmanager base URL for backend-to-backend queries."""
    return _strip_trailing_slash(settings.ALERTMANAGER_INTERNAL_URL)


def _build_external_tools_response(*, is_superadmin: bool) -> ExternalToolsDTO:
    """
    Build response for /tenant/tools from backend settings.

    Important:
    - internal URLs are used only by backend and do not belong here;
    - external URLs must be physically reachable by browser;
    - superadmin receives expanded list of deep links;
    - tenant_admin receives only legacy fields for backwards compatibility.
    """
    grafana_url = settings.GRAFANA_EXTERNAL_URL
    prometheus_url = settings.PROMETHEUS_EXTERNAL_URL
    alertmanager_url = settings.ALERTMANAGER_EXTERNAL_URL

    if not is_superadmin:
        return ExternalToolsDTO(
            grafana_url=grafana_url,
            prometheus_url=prometheus_url,
            alertmanager_url=alertmanager_url,
            is_superadmin=False,
            services=[],
            dashboards=[],
        )

    grafana_base = _strip_trailing_slash(grafana_url)
    ollama_base = _strip_trailing_slash(settings.OLLAMA_EXTERNAL_URL)

    dashboards = [
        ExternalDashboardDTO(
            uid="operations-overview",
            label="Operations Overview",
            description="HTTP, LLM, DLQ, active runs",
            url=f"{grafana_base}/d/operations-overview",
        ),
        ExternalDashboardDTO(
            uid="legalmas-pipeline",
            label="Pipeline Overview",
            description="Document processing stages",
            url=f"{grafana_base}/d/legalmas-pipeline",
        ),
        ExternalDashboardDTO(
            uid="slo-overview",
            label="SLO Overview",
            description="Quality metrics and SLO",
            url=f"{grafana_base}/d/slo-overview",
        ),
        ExternalDashboardDTO(
            uid="logs-explorer",
            label="Log Explorer",
            description="Loki log search and analysis",
            url=f"{grafana_base}/explore",
        ),
    ]

    services = [
        ExternalServiceDTO(
            key="grafana",
            label="Grafana",
            url=settings.GRAFANA_EXTERNAL_URL,
            description="Dashboards, alerts, explore",
        ),
        ExternalServiceDTO(
            key="prometheus",
            label="Prometheus",
            url=settings.PROMETHEUS_EXTERNAL_URL,
            description="Metrics, alert rules, targets",
        ),
        ExternalServiceDTO(
            key="alertmanager",
            label="Alertmanager",
            url=settings.ALERTMANAGER_EXTERNAL_URL,
            description="Active alerts, silences",
        ),
        ExternalServiceDTO(
            key="tempo",
            label="Tempo (via Grafana)",
            url=(
                f"{grafana_base}/explore?"
                'left=%7B%22datasource%22:%22tempo%22%7D'
            ),
            description="Distributed traces via Grafana Explore",
        ),
        ExternalServiceDTO(
            key="loki",
            label="Loki (via Grafana)",
            url=(
                f"{grafana_base}/explore?"
                'left=%7B%22datasource%22:%22loki%22%7D'
            ),
            description="Structured logs via Grafana Explore",
        ),
        ExternalServiceDTO(
            key="minio",
            label="MinIO Console",
            url=settings.MINIO_CONSOLE_EXTERNAL_URL,
            description="Object storage: artifacts, exports",
        ),
        ExternalServiceDTO(
            key="api_docs",
            label="API Docs",
            url=settings.API_DOCS_EXTERNAL_URL,
            description="OpenAPI Swagger for backend",
        ),
        ExternalServiceDTO(
            key="ollama",
            label="Ollama API",
            url=f"{ollama_base}/api/tags",
            description="LLM inference status and models",
        ),
    ]

    return ExternalToolsDTO(
        grafana_url=grafana_url,
        prometheus_url=prometheus_url,
        alertmanager_url=alertmanager_url,
        is_superadmin=True,
        services=services,
        dashboards=dashboards,
    )


# ── Guards ──────────────────────────────────────────────────────────────────

def _require_tenant_admin(user: CurrentUser) -> None:
    if user.global_role not in ("tenant_admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            headers={"X-Error-Code": "TENANT_ADMIN_ACCESS_REQUIRED"},
            detail="Tenant admin access required",
        )


def _resolve_tenant_id(user: CurrentUser, tenant_id_param: uuid.UUID | None) -> uuid.UUID:
    if user.global_role == "superadmin" and tenant_id_param is not None:
        return tenant_id_param

    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            headers={"X-Error-Code": "NO_TENANT_ASSOCIATED"},
            detail="User has no tenant associated",
        )
    return uuid.UUID(str(user.tenant_id))


async def _assert_deal_in_tenant(
    db: AsyncSession, deal_id: uuid.UUID, tenant_id: uuid.UUID
) -> Deal:
    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    deal = result.scalar_one_or_none()

    if deal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "DEAL_NOT_FOUND"},
            detail="Deal not found",
        )

    if deal.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            headers={"X-Error-Code": "DEAL_NOT_IN_TENANT"},
            detail="Deal does not belong to tenant",
        )

    return deal


# ── Response models ─────────────────────────────────────────────────────────

class UserProjectDTO(BaseModel):
    deal_id: str
    deal_name: str
    role: str


class TenantUserDTO(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    system_role: str
    is_active: bool
    created_at: datetime
    projects: list[UserProjectDTO] = Field(default_factory=list)
    projects_count: int = 0


class ProjectRunSummaryDTO(BaseModel):
    run_id: str
    status: str
    total_checks: int
    completed_checks: int
    has_errors: bool
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ProjectHealthDTO(BaseModel):
    deal_id: str
    deal_name: str
    created_at: datetime
    total_documents: int
    failed_documents: int
    quarantine_documents: int
    last_run: ProjectRunSummaryDTO | None = None


class TenantStatsDTO(BaseModel):
    total_projects: int
    total_users: int
    active_users: int
    total_documents: int
    failed_documents: int
    quarantine_documents: int
    runs_last_7_days: int
    dlq_size: int


class TenantDashboardResponse(BaseModel):
    tenant_id: str
    stats: TenantStatsDTO
    projects: list[ProjectHealthDTO]
    users: list[TenantUserDTO]


class PipelineMetrics(BaseModel):
    dlq_size: int = 0
    active_runs: int = 0
    stuck_executions: int = 0
    docs_processed_last_hour: int = 0
    docs_failed_last_hour: int = 0


class ApiEndpointMetric(BaseModel):
    handler: str
    method: str
    requests: int
    errors: int
    p95_ms: float | None = None


class ApiMetrics(BaseModel):
    top_endpoints: list[ApiEndpointMetric] = Field(default_factory=list)


class CeleryTaskFailureMetric(BaseModel):
    task_name: str
    failures_last_hour: int
    failure_types: list[str] = Field(default_factory=list)


class CeleryMetrics(BaseModel):
    task_failures_last_hour: list[CeleryTaskFailureMetric] = Field(default_factory=list)


class LlmProviderMetric(BaseModel):
    provider: str
    requests_last_hour: int
    timeouts_last_hour: int


class LlmMetrics(BaseModel):
    providers: list[LlmProviderMetric] = Field(default_factory=list)


class PlatformMetricsResponse(BaseModel):
    collected_at: datetime
    prometheus_available: bool
    pipeline: PipelineMetrics
    api: ApiMetrics
    celery: CeleryMetrics
    llm: LlmMetrics


class LogEntry(BaseModel):
    timestamp: str
    level: str
    event: str
    logger: str
    stage: str | None = None
    queue: str | None = None
    worker_hostname: str | None = None
    deal_id: str | None = None
    run_id: str | None = None
    document_id: str | None = None
    task_id: str | None = None
    task_name: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    count: int = 1
    first_seen: str | None = None
    last_seen: str | None = None


class LogsStats(BaseModel):
    fetched: int = 0
    returned: int = 0
    filtered_out_by_mode: int = 0
    grouped_into: int = 0
    mode: str = "operational"


class LogsResponse(BaseModel):
    collected_at: datetime
    loki_available: bool
    entries: list[LogEntry] = Field(default_factory=list)
    stats: LogsStats = Field(default_factory=LogsStats)


class ProjectDocumentStats(BaseModel):
    total: int = 0
    failed: int = 0
    quarantine: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_doc_type: dict[str, int] = Field(default_factory=dict)
    reviewed_by_person: int = 0
    requires_review: int = 0


class ProjectRunStats(BaseModel):
    total_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    completed_with_errors_runs: int = 0
    running_runs: int = 0
    pending_runs: int = 0
    runs_last_7_days: int = 0
    avg_duration_seconds: float | None = None
    last_run: ProjectRunSummaryDTO | None = None
    recent_runs: list[ProjectRunSummaryDTO] = Field(default_factory=list)


class ProjectMemberDTO(BaseModel):
    user_id: str
    email: str
    full_name: str | None = None
    system_role: str
    is_active: bool
    project_role: str


class ProjectErrorItem(BaseModel):
    """
    A single record from the project's issue/error history.

    Source is PostgreSQL only (Document.processing_error_details and
    Run.error_details). It lives as long as the DB itself, meaning it remains
    available even a year after the incident when Loki logs are already purged.

    The 'kind' field determines what the error relates to:
      - "document" — failures of a specific document;
      - "run"      — failures or issues of a specific run.
    """
    kind: str  # "document" | "run"
    occurred_at: datetime | None = None
    document_id: str | None = None
    document_filename: str | None = None
    document_status: str | None = None
    run_id: str | None = None
    run_status: str | None = None
    stage: str | None = None
    error_type: str | None = None
    error_reason: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None


class ProjectErrorStats(BaseModel):
    failed_documents: int = 0
    quarantine_documents: int = 0
    failed_runs: int = 0
    completed_with_errors_runs: int = 0
    total_items: int = 0
    truncated: bool = False
    items: list[ProjectErrorItem] = Field(default_factory=list)


class ProjectInsightsResponse(BaseModel):
    deal_id: str
    deal_name: str
    created_at: datetime
    tenant_id: str
    documents: ProjectDocumentStats
    runs: ProjectRunStats
    members: list[ProjectMemberDTO] = Field(default_factory=list)
    members_count: int = 0
    last_activity_at: datetime | None = None
    errors: ProjectErrorStats = Field(default_factory=ProjectErrorStats)


class ActiveAlertDTO(BaseModel):
    """
    Single active alert from Alertmanager.
    Normalized form of Alertmanager API v2 response.
    """
    fingerprint: str
    alertname: str
    severity: str
    state: str  # active | suppressed | unprocessed
    starts_at: str
    ends_at: str | None = None
    updated_at: str | None = None
    summary: str | None = None
    description: str | None = None
    source: str | None = None       # prometheus | loki (from label 'source')
    category: str | None = None     # security | performance | pipeline | system
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    generator_url: str | None = None


class AlertsResponse(BaseModel):
    collected_at: datetime
    alertmanager_available: bool
    active_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    alerts: list[ActiveAlertDTO] = Field(default_factory=list)


class ExternalServiceDTO(BaseModel):
    """
    Single external service (Grafana, Prometheus, MinIO, etc.).
    Shown as an item in the "External Tools" dropdown.
    """
    key: str          # unique identifier for React key
    label: str        # human-readable label
    url: str          # full URL to open in a new tab
    description: str  # short description of what it shows


class ExternalDashboardDTO(BaseModel):
    """
    Single Grafana dashboard.
    URL is built as {grafana_url}/d/{uid}.
    """
    uid: str          # Grafana dashboard UID (e.g., "operations-overview")
    label: str        # human-readable label
    description: str  # short description
    url: str          # full URL to open


class ExternalToolsDTO(BaseModel):
    """
    External monitoring tools for navigation from admin panel.

    Returns 2 lists:
    - services: infrastructure services (Grafana, Prometheus, ...)
    - dashboards: specific Grafana dashboards with deep links

    Both lists are empty for non-superadmins.
    Frontend checks is_superadmin and hides the panel if False.

    Backwards compatibility: legacy fields grafana_url / prometheus_url /
    alertmanager_url are kept for existing components (AlertsPanel).
    """
    # Backwards compatibility — do not remove, used in AlertsPanel
    grafana_url: str
    prometheus_url: str
    alertmanager_url: str
    is_superadmin: bool

    # Expanded details for "External Tools" dropdown
    services: list[ExternalServiceDTO] = Field(default_factory=list)
    dashboards: list[ExternalDashboardDTO] = Field(default_factory=list)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _safe_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _escape_logql_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _empty_platform_metrics_response(*, available: bool) -> PlatformMetricsResponse:
    return PlatformMetricsResponse(
        collected_at=datetime.now(UTC),
        prometheus_available=available,
        pipeline=PipelineMetrics(),
        api=ApiMetrics(),
        celery=CeleryMetrics(),
        llm=LlmMetrics(),
    )


def _empty_logs_response(*, available: bool, mode: str) -> LogsResponse:
    return LogsResponse(
        collected_at=datetime.now(UTC),
        loki_available=available,
        entries=[],
        stats=LogsStats(mode=mode),
    )


def _parse_prometheus_sample_value(row: dict[str, Any]) -> float | None:
    value = row.get("value")
    if not isinstance(value, list) or len(value) < 2:
        return None

    try:
        parsed = float(value[1])
    except (TypeError, ValueError):
        return None

    if not math.isfinite(parsed):
        return None

    return parsed


def _parse_prometheus_sample_int(row: dict[str, Any]) -> int:
    parsed = _parse_prometheus_sample_value(row)
    if parsed is None:
        return 0
    return int(parsed)


async def _prometheus_query(
    client: httpx.AsyncClient,
    query: str,
) -> list[dict[str, Any]]:
    response = await client.get(
        f"{_prometheus_base_url()}/api/v1/query",
        params={"query": query},
    )
    response.raise_for_status()

    payload = response.json()
    if payload.get("status") != "success":
        logger.warning(
            "Prometheus query returned non-success status",
            query=query,
            error=payload.get("error"),
        )
        return []

    result = payload.get("data", {}).get("result", [])
    if not isinstance(result, list):
        return []

    return result


def _build_loki_selector(
    *,
    level: str | None,
    stage: str | None,
    queue: str | None,
) -> str:
    labels: dict[str, str] = {"job": "legalmas"}

    if level:
        labels["level"] = level
    if stage:
        labels["stage"] = stage
    if queue:
        labels["queue"] = queue

    selector_parts = [
        f'{key}="{_escape_logql_value(value)}"'
        for key, value in labels.items()
    ]
    return "{" + ", ".join(selector_parts) + "}"


def _to_run_summary(run: Run) -> ProjectRunSummaryDTO:
    return ProjectRunSummaryDTO(
        run_id=str(run.id),
        status=run.status,
        total_checks=run.total_checks or 0,
        completed_checks=run.completed_checks or 0,
        has_errors=bool(run.has_errors),
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _is_operational_entry(entry: LogEntry) -> bool:
    lvl = entry.level.lower()
    if lvl in OPERATIONAL_LEVELS:
        return True
    if lvl == "info" and entry.logger in OPERATIONAL_ALLOWED_INFO_LOGGERS:
        return True
    return False


def _group_key(entry: LogEntry) -> tuple[str, str, str, str | None]:
    return (entry.level.lower(), entry.logger, entry.event, entry.stage)


def _group_similar_entries(entries: list[LogEntry]) -> list[LogEntry]:
    if not entries:
        return entries

    groups: dict[tuple[str, str, str, str | None], LogEntry] = {}
    order: list[tuple[str, str, str, str | None]] = []
    ordered_singles: list[LogEntry] = []

    for entry in entries:
        lvl = entry.level.lower()

        if lvl in ("error", "critical"):
            ordered_singles.append(entry)
            continue

        key = _group_key(entry)
        if key not in groups:
            group_entry = entry.model_copy(deep=True)
            group_entry.count = 1
            group_entry.first_seen = entry.timestamp
            group_entry.last_seen = entry.timestamp
            groups[key] = group_entry
            order.append(key)
        else:
            g = groups[key]
            g.count += 1
            g.timestamp = entry.timestamp
            g.last_seen = entry.timestamp
            g.raw = entry.raw

    result: list[LogEntry] = list(ordered_singles)
    for key in order:
        g = groups[key]
        if g.count >= GROUP_SIMILAR_MIN_COUNT:
            result.append(g)
        else:
            g.count = 1
            g.first_seen = None
            g.last_seen = None
            result.append(g)

    result.sort(key=lambda e: e.timestamp, reverse=True)
    return result


def _extract_error_from_dict(
    details: dict[str, Any] | None,
) -> tuple[str | None, str | None, str | None, str | None, datetime | None]:
    """
    Universal parser for error_details / processing_error_details fields.

    Returns (stage, error_type, reason, message, timestamp).
    All fields are optional — contract is compatible with actual JSON models:
    {stage, type, reason?, message, run_id?, timestamp}
    """
    if not isinstance(details, dict):
        return None, None, None, None, None

    stage = _safe_optional_text(details.get("stage"))
    error_type = _safe_optional_text(details.get("type"))
    reason = _safe_optional_text(details.get("reason"))
    message = _safe_optional_text(details.get("message"))

    ts_raw = details.get("timestamp")
    ts_parsed: datetime | None = None
    if isinstance(ts_raw, str):
        try:
            # Loki / worker usually write ISO-8601 in UTC
            ts_parsed = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except ValueError:
            ts_parsed = None
    elif isinstance(ts_raw, datetime):
        ts_parsed = ts_raw

    return stage, error_type, reason, message, ts_parsed


async def _collect_project_errors(
    db: AsyncSession,
    deal_id: uuid.UUID,
    all_runs: list[Run],
) -> ProjectErrorStats:
    """
    Collects project issue/error history from PostgreSQL.

    Sources:
      - Document with failed/quarantine status (+ processing_error_details);
      - Run with failed/completed_with_errors status (+ error_details);

    Guaranteed to be available as long as the DB exists — even a year after
    the incident when Loki logs have already been rotated.
    """
    # ── Troubled documents ───────────────────────────────────────────────────
    failed_docs_result = await db.execute(
        select(Document)
        .where(
            Document.deal_id == deal_id,
            Document.status.in_(["failed", "quarantine"]),
        )
        .order_by(Document.updated_at.desc())
        .limit(PROJECT_ERROR_LIMIT)
    )
    failed_docs = list(failed_docs_result.scalars().all())

    docs_failed_count_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.deal_id == deal_id,
            Document.status == "failed",
        )
    )
    failed_documents_count = int(docs_failed_count_result.scalar_one() or 0)

    docs_quarantine_count_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.deal_id == deal_id,
            Document.status == "quarantine",
        )
    )
    quarantine_documents_count = int(docs_quarantine_count_result.scalar_one() or 0)

    # ── Troubled runs ────────────────────────────────────────────────────────
    problem_runs = [
        r
        for r in all_runs
        if str(r.status or "").lower() in ("failed", "completed_with_errors")
    ]
    failed_runs_count = sum(
        1 for r in all_runs if str(r.status or "").lower() == "failed"
    )
    completed_with_errors_runs_count = sum(
        1
        for r in all_runs
        if str(r.status or "").lower() == "completed_with_errors"
    )

    items: list[ProjectErrorItem] = []

    for doc in failed_docs:
        stage, err_type, reason, message, ts_from_details = _extract_error_from_dict(
            doc.processing_error_details
        )
        occurred_at = ts_from_details or doc.updated_at
        items.append(
            ProjectErrorItem(
                kind="document",
                occurred_at=occurred_at,
                document_id=str(doc.id),
                document_filename=doc.filename,
                document_status=doc.status,
                run_id=None,
                run_status=None,
                stage=stage,
                error_type=err_type,
                error_reason=reason,
                error_message=message,
                error_details=doc.processing_error_details
                if isinstance(doc.processing_error_details, dict)
                else None,
            )
        )

    for run in problem_runs:
        stage, err_type, reason, message, ts_from_details = _extract_error_from_dict(
            run.error_details
        )
        occurred_at = (
            ts_from_details
            or run.completed_at
            or run.started_at
            or run.created_at
        )
        items.append(
            ProjectErrorItem(
                kind="run",
                occurred_at=occurred_at,
                document_id=None,
                document_filename=None,
                document_status=None,
                run_id=str(run.id),
                run_status=run.status,
                stage=stage,
                error_type=err_type,
                error_reason=reason,
                error_message=message,
                error_details=run.error_details
                if isinstance(run.error_details, dict)
                else None,
            )
        )

    def _sort_key(item: ProjectErrorItem) -> datetime:
        # Items without timestamp are considered oldest to sink to bottom.
        return item.occurred_at or datetime.min.replace(tzinfo=UTC)

    items.sort(key=_sort_key, reverse=True)

    truncated = len(items) > PROJECT_ERROR_LIMIT
    items = items[:PROJECT_ERROR_LIMIT]

    total_items = (
        failed_documents_count
        + quarantine_documents_count
        + failed_runs_count
        + completed_with_errors_runs_count
    )

    return ProjectErrorStats(
        failed_documents=failed_documents_count,
        quarantine_documents=quarantine_documents_count,
        failed_runs=failed_runs_count,
        completed_with_errors_runs=completed_with_errors_runs_count,
        total_items=total_items,
        truncated=truncated,
        items=items,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/dashboard",
    response_model=TenantDashboardResponse,
    summary="Tenant admin dashboard summary statistics",
)
async def get_tenant_dashboard(
    tenant_id: uuid.UUID | None = Query(
        default=None,
        description="Only for superadmin: view a specific tenant",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(check_admin_rate_limit),
) -> TenantDashboardResponse:
    _require_tenant_admin(user)
    resolved_tenant_id = _resolve_tenant_id(user, tenant_id)

    deals_result = await db.execute(
        select(Deal)
        .where(Deal.tenant_id == resolved_tenant_id)
        .order_by(Deal.created_at.desc())
    )
    deals = list(deals_result.scalars().all())
    deal_ids = [d.id for d in deals]
    deals_by_id: dict[uuid.UUID, Deal] = {d.id: d for d in deals}

    users_result = await db.execute(
        select(User)
        .where(User.tenant_id == resolved_tenant_id)
        .order_by(User.created_at.desc())
    )
    users = list(users_result.scalars().all())

    memberships_by_user: dict[uuid.UUID, list[UserProjectDTO]] = defaultdict(list)

    if deal_ids:
        memberships_result = await db.execute(
            select(DealMember).where(DealMember.deal_id.in_(deal_ids))
        )
        for member in memberships_result.scalars().all():
            deal = deals_by_id.get(member.deal_id)
            if deal is None:
                continue
            memberships_by_user[member.user_id].append(
                UserProjectDTO(
                    deal_id=str(deal.id),
                    deal_name=deal.name,
                    role=str(member.role),
                )
            )

    total_docs = 0
    failed_docs = 0
    quarantine_docs = 0

    if deal_ids:
        docs_agg = await db.execute(
            select(
                func.count(Document.id).label("total"),
                func.count(Document.id).filter(Document.status == "failed").label("failed"),
                func.count(Document.id).filter(Document.status == "quarantine").label("quarantine"),
            ).where(Document.deal_id.in_(deal_ids))
        )
        row = docs_agg.first()
        if row:
            total_docs = int(row.total or 0)
            failed_docs = int(row.failed or 0)
            quarantine_docs = int(row.quarantine or 0)

    runs_7d = 0
    if deal_ids:
        seven_days_ago = datetime.now(UTC) - timedelta(days=7)
        runs_7d_result = await db.execute(
            select(func.count(Run.id)).where(
                Run.deal_id.in_(deal_ids),
                Run.created_at >= seven_days_ago,
            )
        )
        runs_7d = int(runs_7d_result.scalar_one() or 0)

    dlq_result = await db.execute(select(func.count(DLQRecord.id)))
    dlq_size = int(dlq_result.scalar_one() or 0)

    run_repo = RunRepository(db)
    project_list: list[ProjectHealthDTO] = []

    for deal in deals:
        deal_docs_result = await db.execute(
            select(
                func.count(Document.id).label("total"),
                func.count(Document.id).filter(Document.status == "failed").label("failed"),
                func.count(Document.id).filter(Document.status == "quarantine").label("quarantine"),
            ).where(Document.deal_id == deal.id)
        )
        deal_row = deal_docs_result.first()
        deal_total = int(deal_row.total or 0) if deal_row else 0
        deal_failed = int(deal_row.failed or 0) if deal_row else 0
        deal_quarantine = int(deal_row.quarantine or 0) if deal_row else 0

        last_run_dto: ProjectRunSummaryDTO | None = None
        if deal.last_run_id:
            last_run = await run_repo.get_by_id(deal.last_run_id)
            if last_run:
                last_run_dto = _to_run_summary(last_run)

        project_list.append(
            ProjectHealthDTO(
                deal_id=str(deal.id),
                deal_name=deal.name,
                created_at=deal.created_at,
                total_documents=deal_total,
                failed_documents=deal_failed,
                quarantine_documents=deal_quarantine,
                last_run=last_run_dto,
            )
        )

    users_dto: list[TenantUserDTO] = []
    for u in users:
        user_projects = memberships_by_user.get(u.id, [])
        user_projects_sorted = sorted(
            user_projects, key=lambda p: p.deal_name.lower()
        )
        users_dto.append(
            TenantUserDTO(
                id=str(u.id),
                email=u.email,
                full_name=u.full_name,
                system_role=u.system_role,
                is_active=u.is_active,
                created_at=u.created_at,
                projects=user_projects_sorted,
                projects_count=len(user_projects_sorted),
            )
        )

    stats = TenantStatsDTO(
        total_projects=len(deals),
        total_users=len(users),
        active_users=sum(1 for u in users if u.is_active),
        total_documents=total_docs,
        failed_documents=failed_docs,
        quarantine_documents=quarantine_docs,
        runs_last_7_days=runs_7d,
        dlq_size=dlq_size,
    )

    return TenantDashboardResponse(
        tenant_id=str(resolved_tenant_id),
        stats=stats,
        projects=project_list,
        users=users_dto,
    )


@router.get(
    "/projects/{deal_id}/insights",
    response_model=ProjectInsightsResponse,
    summary="Detailed summary and project error history (from PostgreSQL)",
)
async def get_project_insights(
    deal_id: uuid.UUID,
    request: Request,
    tenant_id: uuid.UUID | None = Query(
        default=None,
        description="Only for superadmin: tenant context",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(check_admin_rate_limit),
) -> ProjectInsightsResponse:
    _require_tenant_admin(user)
    resolved_tenant_id = _resolve_tenant_id(user, tenant_id)

    deal = await _assert_deal_in_tenant(db, deal_id, resolved_tenant_id)

    docs_by_status_result = await db.execute(
        select(Document.status, func.count(Document.id))
        .where(Document.deal_id == deal_id)
        .group_by(Document.status)
    )
    by_status: dict[str, int] = {}
    for st, cnt in docs_by_status_result.all():
        by_status[str(st) if st is not None else "unknown"] = int(cnt or 0)

    docs_by_doctype_result = await db.execute(
        select(Document.doc_type, func.count(Document.id))
        .where(Document.deal_id == deal_id)
        .group_by(Document.doc_type)
    )
    by_doc_type: dict[str, int] = {}
    for dt, cnt in docs_by_doctype_result.all():
        key = str(dt) if dt is not None else "unknown"
        by_doc_type[key] = int(cnt or 0)

    docs_extra_result = await db.execute(
        select(
            func.count(Document.id).label("total"),
            func.count(Document.id).filter(Document.reviewed_by_person.is_(True)).label("reviewed"),
            func.count(Document.id)
            .filter(Document.classification_requires_review.is_(True))
            .label("requires_review"),
        ).where(Document.deal_id == deal_id)
    )
    docs_extra = docs_extra_result.first()

    total_docs = int(docs_extra.total or 0) if docs_extra else 0
    reviewed_docs = int(docs_extra.reviewed or 0) if docs_extra else 0
    requires_review_docs = int(docs_extra.requires_review or 0) if docs_extra else 0
    failed_docs = int(by_status.get("failed", 0))
    quarantine_docs = int(by_status.get("quarantine", 0))

    documents_stats = ProjectDocumentStats(
        total=total_docs,
        failed=failed_docs,
        quarantine=quarantine_docs,
        by_status=by_status,
        by_doc_type=by_doc_type,
        reviewed_by_person=reviewed_docs,
        requires_review=requires_review_docs,
    )

    runs_result = await db.execute(
        select(Run)
        .where(Run.deal_id == deal_id)
        .order_by(Run.created_at.desc())
    )
    all_runs = list(runs_result.scalars().all())

    seven_days_ago = datetime.now(UTC) - timedelta(days=7)

    completed_runs = 0
    failed_runs = 0
    completed_with_errors_runs = 0
    running_runs = 0
    pending_runs = 0
    runs_last_7_days = 0
    durations: list[float] = []

    for run in all_runs:
        st = str(run.status or "").lower()
        if st == "completed":
            completed_runs += 1
        elif st == "failed":
            failed_runs += 1
        elif st == "completed_with_errors":
            completed_with_errors_runs += 1
        elif st == "running":
            running_runs += 1
        elif st == "pending":
            pending_runs += 1

        if run.created_at and run.created_at >= seven_days_ago:
            runs_last_7_days += 1

        if run.started_at and run.completed_at:
            delta = (run.completed_at - run.started_at).total_seconds()
            if delta >= 0:
                durations.append(delta)

    avg_duration = None
    if durations:
        avg_duration = round(sum(durations) / len(durations), 2)

    last_run_dto: ProjectRunSummaryDTO | None = None
    if deal.last_run_id:
        run_repo = RunRepository(db)
        last_run_obj = await run_repo.get_by_id(deal.last_run_id)
        if last_run_obj:
            last_run_dto = _to_run_summary(last_run_obj)

    if last_run_dto is None and all_runs:
        last_run_dto = _to_run_summary(all_runs[0])

    recent_runs = [_to_run_summary(r) for r in all_runs[:10]]

    runs_stats = ProjectRunStats(
        total_runs=len(all_runs),
        completed_runs=completed_runs,
        failed_runs=failed_runs,
        completed_with_errors_runs=completed_with_errors_runs,
        running_runs=running_runs,
        pending_runs=pending_runs,
        runs_last_7_days=runs_last_7_days,
        avg_duration_seconds=avg_duration,
        last_run=last_run_dto,
        recent_runs=recent_runs,
    )

    members_result = await db.execute(
        select(DealMember, User)
        .join(User, User.id == DealMember.user_id)
        .where(DealMember.deal_id == deal_id)
    )
    members: list[ProjectMemberDTO] = []
    for member, u in members_result.all():
        members.append(
            ProjectMemberDTO(
                user_id=str(u.id),
                email=u.email,
                full_name=u.full_name,
                system_role=u.system_role,
                is_active=u.is_active,
                project_role=str(member.role),
            )
        )

    activity_candidates: list[datetime] = []
    for run in all_runs:
        for ts in (run.completed_at, run.started_at, run.created_at):
            if ts is not None:
                activity_candidates.append(ts)

    docs_updated_result = await db.execute(
        select(func.max(Document.updated_at)).where(Document.deal_id == deal_id)
    )
    latest_doc_updated = docs_updated_result.scalar_one_or_none()
    if latest_doc_updated is not None:
        activity_candidates.append(latest_doc_updated)

    last_activity_at = max(activity_candidates) if activity_candidates else None

    # ── Error history ────────────────────────────────────────────────────────
    errors_stats = await _collect_project_errors(db, deal_id, all_runs)

    # ── Direct audit for insights ────────────────────────────────────────────
    # The /insights suffix is too generic for AuditMiddleware, so we write the audit
    # log explicitly inside the endpoint using a separate session.
    try:
        async with get_session() as audit_session:
            audit_repo = AuditRepository(audit_session)
            await audit_repo.log(
                tenant_id=resolved_tenant_id,
                action="ADMIN_VIEW_PROJECT_INSIGHTS",
                actor=user.id,
                deal_id=deal_id,
                actor_role=user.global_role,
                details={
                    "request_id": getattr(request.state, "request_id", None),
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": 200,
                    "deal_name": deal.name,
                    "user_email": user.email,
                    "total_documents": documents_stats.total,
                    "total_runs": runs_stats.total_runs,
                },
            )
            await audit_session.commit()
    except Exception:
        logger.exception(
            "Failed to write audit for project insights",
            deal_id=str(deal_id),
            actor=user.id,
        )

    return ProjectInsightsResponse(
        deal_id=str(deal.id),
        deal_name=deal.name,
        created_at=deal.created_at,
        tenant_id=str(resolved_tenant_id),
        documents=documents_stats,
        runs=runs_stats,
        members=members,
        members_count=len(members),
        last_activity_at=last_activity_at,
        errors=errors_stats,
    )


@router.get(
    "/metrics",
    response_model=PlatformMetricsResponse,
    summary="Global platform metrics for admin panel",
)
async def get_platform_metrics(
    tenant_id: uuid.UUID | None = Query(
        default=None,
        description="Only for superadmin: tenant context (global metrics)",
    ),
    user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(check_admin_rate_limit),
) -> PlatformMetricsResponse:
    _require_tenant_admin(user)
    _resolve_tenant_id(user, tenant_id)

    try:
        async with httpx.AsyncClient(timeout=PROMETHEUS_TIMEOUT_SECONDS) as client:
            dlq_rows = await _prometheus_query(client, "mas_dd_dlq_size")
            http_requests_rows = await _prometheus_query(
                client,
                "sum(increase(mas_dd_http_requests_total[1h])) by (handler, method, status_code)",
            )
            http_latency_rows = await _prometheus_query(
                client,
                "histogram_quantile(0.95, sum(rate(mas_dd_http_request_duration_seconds_bucket[1h])) by (handler, le))",
            )
            docs_processed_rows = await _prometheus_query(
                client,
                "sum(increase(mas_dd_documents_processed_total[1h])) by (stage, status)",
            )
            active_runs_rows = await _prometheus_query(client, "mas_dd_active_runs")
            stuck_rows = await _prometheus_query(client, "mas_dd_stuck_stage_executions_total")
            celery_failures_rows = await _prometheus_query(
                client,
                "sum(increase(mas_dd_celery_task_failures_total[1h])) by (task_name, failure_type)",
            )
            llm_requests_rows = await _prometheus_query(
                client,
                "sum(increase(mas_dd_llm_requests_total[1h])) by (provider, status)",
            )
            llm_timeouts_rows = await _prometheus_query(
                client,
                "sum(increase(mas_dd_llm_timeout_total[1h])) by (provider)",
            )
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "Prometheus unavailable for tenant admin metrics",
            error=str(exc),
        )
        return _empty_platform_metrics_response(available=False)

    dlq_size = _parse_prometheus_sample_int(dlq_rows[0]) if dlq_rows else 0
    active_runs = _parse_prometheus_sample_int(active_runs_rows[0]) if active_runs_rows else 0
    stuck_executions = _parse_prometheus_sample_int(stuck_rows[0]) if stuck_rows else 0

    docs_processed_last_hour = 0
    docs_failed_last_hour = 0

    for row in docs_processed_rows:
        count = _parse_prometheus_sample_int(row)
        docs_processed_last_hour += count

        metric = row.get("metric", {})
        row_status = _safe_text(metric.get("status"))
        if row_status == "failed":
            docs_failed_last_hour += count

    p95_by_handler: dict[str, float] = {}
    for row in http_latency_rows:
        metric = row.get("metric", {})
        handler = _safe_text(metric.get("handler"), default="unknown")
        value = _parse_prometheus_sample_value(row)
        if value is None:
            continue
        p95_by_handler[handler] = round(value * 1000, 2)

    endpoint_totals: dict[tuple[str, str], dict[str, int | str]] = {}
    for row in http_requests_rows:
        metric = row.get("metric", {})
        handler = _safe_text(metric.get("handler"), default="unknown")
        method = _safe_text(metric.get("method"), default="UNKNOWN")
        status_code = _safe_text(metric.get("status_code"))
        count = _parse_prometheus_sample_int(row)

        key = (handler, method)
        if key not in endpoint_totals:
            endpoint_totals[key] = {
                "handler": handler,
                "method": method,
                "requests": 0,
                "errors": 0,
            }

        endpoint_totals[key]["requests"] = int(endpoint_totals[key]["requests"]) + count

        if status_code.isdigit() and int(status_code) >= 400:
            endpoint_totals[key]["errors"] = int(endpoint_totals[key]["errors"]) + count

    top_endpoints = [
        ApiEndpointMetric(
            handler=str(item["handler"]),
            method=str(item["method"]),
            requests=int(item["requests"]),
            errors=int(item["errors"]),
            p95_ms=p95_by_handler.get(str(item["handler"])),
        )
        for item in endpoint_totals.values()
    ]
    top_endpoints.sort(key=lambda item: (item.requests, item.errors), reverse=True)
    top_endpoints = top_endpoints[:5]

    celery_by_task: dict[str, dict[str, Any]] = {}
    for row in celery_failures_rows:
        metric = row.get("metric", {})
        task_name = _safe_text(metric.get("task_name"), default="unknown")
        failure_type = _safe_text(metric.get("failure_type"), default="unknown")
        count = _parse_prometheus_sample_int(row)

        if task_name not in celery_by_task:
            celery_by_task[task_name] = {
                "task_name": task_name,
                "failures_last_hour": 0,
                "failure_types": set(),
            }

        celery_by_task[task_name]["failures_last_hour"] += count
        celery_by_task[task_name]["failure_types"].add(failure_type)

    task_failures_last_hour = [
        CeleryTaskFailureMetric(
            task_name=str(item["task_name"]),
            failures_last_hour=int(item["failures_last_hour"]),
            failure_types=sorted(str(v) for v in item["failure_types"]),
        )
        for item in celery_by_task.values()
    ]
    task_failures_last_hour.sort(
        key=lambda item: item.failures_last_hour,
        reverse=True,
    )

    llm_by_provider: dict[str, dict[str, int | str]] = {}

    for row in llm_requests_rows:
        metric = row.get("metric", {})
        provider = _safe_text(metric.get("provider"), default="unknown")
        count = _parse_prometheus_sample_int(row)

        if provider not in llm_by_provider:
            llm_by_provider[provider] = {
                "provider": provider,
                "requests_last_hour": 0,
                "timeouts_last_hour": 0,
            }

        llm_by_provider[provider]["requests_last_hour"] = (
            int(llm_by_provider[provider]["requests_last_hour"]) + count
        )

    for row in llm_timeouts_rows:
        metric = row.get("metric", {})
        provider = _safe_text(metric.get("provider"), default="unknown")
        count = _parse_prometheus_sample_int(row)

        if provider not in llm_by_provider:
            llm_by_provider[provider] = {
                "provider": provider,
                "requests_last_hour": 0,
                "timeouts_last_hour": 0,
            }

        llm_by_provider[provider]["timeouts_last_hour"] = (
            int(llm_by_provider[provider]["timeouts_last_hour"]) + count
        )

    llm_providers = [
        LlmProviderMetric(
            provider=str(item["provider"]),
            requests_last_hour=int(item["requests_last_hour"]),
            timeouts_last_hour=int(item["timeouts_last_hour"]),
        )
        for item in llm_by_provider.values()
    ]
    llm_providers.sort(
        key=lambda item: (item.requests_last_hour, item.timeouts_last_hour),
        reverse=True,
    )

    return PlatformMetricsResponse(
        collected_at=datetime.now(UTC),
        prometheus_available=True,
        pipeline=PipelineMetrics(
            dlq_size=dlq_size,
            active_runs=active_runs,
            stuck_executions=stuck_executions,
            docs_processed_last_hour=docs_processed_last_hour,
            docs_failed_last_hour=docs_failed_last_hour,
        ),
        api=ApiMetrics(top_endpoints=top_endpoints),
        celery=CeleryMetrics(task_failures_last_hour=task_failures_last_hour),
        llm=LlmMetrics(providers=llm_providers),
    )


@router.get(
    "/logs",
    response_model=LogsResponse,
    summary="Platform logs for admin panel",
)
async def get_tenant_logs(
    tenant_id: uuid.UUID | None = Query(
        default=None,
        description="Only for superadmin: view a specific tenant",
    ),
    deal_id: str | None = Query(default=None, description="Filter by project"),
    run_id: str | None = Query(default=None, description="Filter by specific run_id"),
    document_id: str | None = Query(
        default=None, description="Filter by specific document_id"
    ),
    task_id: str | None = Query(default=None, description="Filter by task_id"),
    level: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    queue: str | None = Query(default=None),
    mode: str = Query(
        default="operational",
        description="operational — only warning+/error+; debug — all logs",
    ),
    group_similar: bool = Query(
        default=True,
        description="Group similar repeating events",
    ),
    limit: int = Query(default=50, ge=1, le=MAX_LOG_LIMIT),
    since_minutes: int = Query(
        default=60,
        ge=0,
        le=MAX_LOG_SINCE_MINUTES,
        description="Time range in minutes. 0 = maximum available (by Loki retention).",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(check_logs_rate_limit),
) -> LogsResponse:
    _require_tenant_admin(user)
    resolved_tenant_id = _resolve_tenant_id(user, tenant_id)

    normalized_mode = (mode or "operational").strip().lower()
    if normalized_mode not in ("operational", "debug"):
        normalized_mode = "operational"

    normalized_level = _normalize_optional_str(level)
    normalized_stage = _normalize_optional_str(stage)
    normalized_queue = _normalize_optional_str(queue)
    normalized_deal_id = _normalize_optional_str(deal_id)
    normalized_run_id = _normalize_optional_str(run_id)
    normalized_document_id = _normalize_optional_str(document_id)
    normalized_task_id = _normalize_optional_str(task_id)

    deal_repo = DealRepository(db)
    tenant_deals = await deal_repo.get_by_tenant(resolved_tenant_id)
    allowed_deal_ids = [str(deal.id) for deal in tenant_deals]
    allowed_deal_ids_set = set(allowed_deal_ids)

    requested_deal_id: str | None = None
    if normalized_deal_id is not None:
        try:
            requested_deal_id = str(uuid.UUID(normalized_deal_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                headers={"X-Error-Code": "INVALID_DEAL_ID"},
                detail="Invalid deal_id",
            ) from exc

        if requested_deal_id not in allowed_deal_ids_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                headers={"X-Error-Code": "DEAL_NOT_IN_TENANT"},
                detail="Deal does not belong to tenant",
            )

    if not allowed_deal_ids:
        return _empty_logs_response(available=True, mode=normalized_mode)

    selector = _build_loki_selector(
        level=normalized_level,
        stage=normalized_stage,
        queue=normalized_queue,
    )

    filters: list[str] = []
    if requested_deal_id is not None:
        filters.append(f'deal_id = "{_escape_logql_value(requested_deal_id)}"')
    else:
        # Anchor each UUID to prevent partial-match on substrings.
        # UUIDs are fixed-length but regex matching without anchors
        # could produce false positives if one ID is a prefix of another.
        escaped_ids = [_escape_logql_value(did) for did in allowed_deal_ids]
        deal_regex = "|".join(escaped_ids)
        filters.append(f'deal_id =~ "^({deal_regex})$"')

    if normalized_run_id:
        filters.append(f'run_id = "{_escape_logql_value(normalized_run_id)}"')
    if normalized_document_id:
        filters.append(f'document_id = "{_escape_logql_value(normalized_document_id)}"')
    if normalized_task_id:
        filters.append(f'task_id = "{_escape_logql_value(normalized_task_id)}"')

    query = f"{selector} | json | " + " | ".join(filters)

    end_dt = datetime.now(UTC)
    # since_minutes == 0 → "all time" (request maximum allowed
    # window, actual horizon is limited by Loki retention).
    if since_minutes > 0:
        start_dt = end_dt - timedelta(minutes=since_minutes)
    else:
        start_dt = end_dt - timedelta(minutes=MAX_LOG_SINCE_MINUTES)

    effective_limit, was_capped = _apply_loki_cost_cap(since_minutes, limit)
    if was_capped:
        logger.warning(
            "Loki query limit auto-capped due to wide time window",
            requested_limit=limit,
            effective_limit=effective_limit,
            since_minutes=since_minutes,
            user_id=user.id,
        )

    fetch_limit = min(effective_limit * LOKI_FETCH_MULTIPLIER, LOKI_FETCH_HARD_CAP)

    loki_started_at = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=LOKI_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{_loki_base_url()}/loki/api/v1/query_range",
                params={
                    "query": query,
                    "limit": fetch_limit,
                    "start": int(start_dt.timestamp() * 1_000_000_000),
                    "end": int(end_dt.timestamp() * 1_000_000_000),
                    "direction": "backward",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        loki_duration = time.monotonic() - loki_started_at
        _observe_admin_logs_query_duration(since_minutes, loki_duration)

        logger.warning(
            "Loki unavailable for tenant admin logs",
            error=str(exc),
            duration_seconds=round(loki_duration, 3),
        )
        return _empty_logs_response(available=False, mode=normalized_mode)

    loki_duration = time.monotonic() - loki_started_at
    _observe_admin_logs_query_duration(since_minutes, loki_duration)

    if loki_duration >= _LOKI_SLOW_QUERY_THRESHOLD_SECONDS:
        logger.warning(
            "Slow Loki query in admin logs endpoint",
            duration_seconds=round(loki_duration, 3),
            since_minutes=since_minutes,
            effective_limit=effective_limit,
            was_capped=was_capped,
            user_id=user.id,
        )

    if payload.get("status") != "success":
        logger.warning(
            "Loki query returned non-success status",
            error=payload.get("error"),
            query=query,
        )
        return _empty_logs_response(available=False, mode=normalized_mode)

    result_streams = payload.get("data", {}).get("result", [])
    if not isinstance(result_streams, list):
        return _empty_logs_response(available=True, mode=normalized_mode)

    parsed_entries: list[tuple[int, LogEntry]] = []

    for stream in result_streams:
        values = stream.get("values", [])
        if not isinstance(values, list):
            continue

        for item in values:
            if not isinstance(item, list) or len(item) < 2:
                continue

            raw_ts = item[0]
            raw_line = item[1]

            try:
                sort_ts = int(raw_ts)
            except (TypeError, ValueError):
                sort_ts = 0

            if isinstance(raw_line, str):
                try:
                    decoded = json.loads(raw_line)
                except json.JSONDecodeError:
                    decoded = {"line": raw_line}
            else:
                decoded = {"value": raw_line}

            raw_payload = decoded if isinstance(decoded, dict) else {"value": decoded}

            timestamp = _safe_optional_text(raw_payload.get("timestamp"))
            if timestamp is None:
                if sort_ts > 0:
                    timestamp = datetime.fromtimestamp(
                        sort_ts / 1_000_000_000,
                        tz=UTC,
                    ).isoformat()
                else:
                    timestamp = datetime.now(UTC).isoformat()

            entry = LogEntry(
                timestamp=timestamp,
                level=_safe_text(raw_payload.get("level"), default="info"),
                event=_safe_text(
                    raw_payload.get("event")
                    or raw_payload.get("message")
                    or raw_payload.get("msg")
                    or raw_payload.get("line"),
                    default="",
                ),
                logger=_safe_text(raw_payload.get("logger"), default=""),
                stage=_safe_optional_text(raw_payload.get("stage")),
                queue=_safe_optional_text(raw_payload.get("queue")),
                worker_hostname=_safe_optional_text(raw_payload.get("worker_hostname")),
                deal_id=_safe_optional_text(raw_payload.get("deal_id")),
                run_id=_safe_optional_text(raw_payload.get("run_id")),
                document_id=_safe_optional_text(raw_payload.get("document_id")),
                task_id=_safe_optional_text(raw_payload.get("task_id")),
                task_name=_safe_optional_text(raw_payload.get("task_name")),
                raw=raw_payload,
            )
            parsed_entries.append((sort_ts, entry))

    parsed_entries.sort(key=lambda item: item[0], reverse=True)

    all_entries = [e for _, e in parsed_entries]

    # ── Defense-in-depth: post-filter by tenant_id ────────────────────────
    # If a log entry contains tenant_id and it does not match the
    # resolved tenant, drop it. This is a safety net on top of the
    # deal_id-based LogQL filter.
    # Superadmin viewing a specific tenant is also filtered;
    # superadmin without tenant_id param sees everything (resolved_tenant_id
    # is always set by _resolve_tenant_id).
    _resolved_tid_str = str(resolved_tenant_id)

    def _tenant_allowed(entry: LogEntry) -> bool:
        entry_tenant = entry.raw.get("tenant_id")
        if entry_tenant is None:
            return True  # no tenant_id in log line — pass through (filtered by deal_id)
        return str(entry_tenant).strip() == _resolved_tid_str

    all_entries = [e for e in all_entries if _tenant_allowed(e)]

    fetched_count = len(all_entries)

    if normalized_mode == "operational":
        filtered_entries = [e for e in all_entries if _is_operational_entry(e)]
    else:
        filtered_entries = all_entries

    filtered_out = fetched_count - len(filtered_entries)

    if group_similar:
        grouped_entries = _group_similar_entries(filtered_entries)
    else:
        grouped_entries = filtered_entries

    grouped_into = len(grouped_entries)
    final_entries = grouped_entries[:effective_limit]

    return LogsResponse(
        collected_at=datetime.now(UTC),
        loki_available=True,
        entries=final_entries,
        stats=LogsStats(
            fetched=fetched_count,
            returned=len(final_entries),
            filtered_out_by_mode=filtered_out,
            grouped_into=grouped_into,
            mode=normalized_mode,
        ),
    )


# ─── Alerts & External Tools ────────────────────────────────────────────────

@router.get(
    "/alerts",
    response_model=AlertsResponse,
    summary="Active alerts from Alertmanager",
)
async def get_tenant_alerts(
    tenant_id: uuid.UUID | None = Query(
        default=None,
        description="Only for superadmin: tenant context (global alerts)",
    ),
    user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(check_admin_rate_limit),
) -> AlertsResponse:
    """
    Return active alerts from Alertmanager.

    Alerts are generated by:
    - Prometheus (by metrics from mas_dd_*)
    - Loki ruler (by patterns in logs)

    Endpoint acts as a proxy to Alertmanager API v2.
    If Alertmanager is unreachable, returns empty list with
    alertmanager_available=false.
    """
    _require_tenant_admin(user)
    _resolve_tenant_id(user, tenant_id)

    empty = AlertsResponse(
        collected_at=datetime.now(UTC),
        alertmanager_available=False,
    )

    try:
        async with httpx.AsyncClient(timeout=ALERTMANAGER_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{_alertmanager_base_url()}/api/v2/alerts",
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "Alertmanager unavailable for tenant alerts",
            error=str(exc),
        )
        return empty

    if not isinstance(payload, list):
        return empty

    alerts: list[ActiveAlertDTO] = []
    critical_count = 0
    warning_count = 0
    info_count = 0

    for raw in payload:
        if not isinstance(raw, dict):
            continue

        labels_raw = raw.get("labels") or {}
        annotations_raw = raw.get("annotations") or {}
        status_raw = raw.get("status") or {}

        labels = {
            str(k): str(v) for k, v in labels_raw.items()
            if isinstance(labels_raw, dict)
        }
        annotations = {
            str(k): str(v) for k, v in annotations_raw.items()
            if isinstance(annotations_raw, dict)
        }

        severity = _safe_text(labels.get("severity"), default="unknown").lower()
        state = _safe_text(status_raw.get("state") if isinstance(status_raw, dict) else None, default="unknown")

        if severity == "critical":
            critical_count += 1
        elif severity == "warning":
            warning_count += 1
        elif severity == "info":
            info_count += 1

        alerts.append(ActiveAlertDTO(
            fingerprint=_safe_text(raw.get("fingerprint"), default=""),
            alertname=_safe_text(labels.get("alertname"), default="unknown"),
            severity=severity,
            state=state,
            starts_at=_safe_text(raw.get("startsAt"), default=""),
            ends_at=_safe_optional_text(raw.get("endsAt")),
            updated_at=_safe_optional_text(raw.get("updatedAt")),
            summary=_safe_optional_text(annotations.get("summary")),
            description=_safe_optional_text(annotations.get("description")),
            source=_safe_optional_text(labels.get("source")),
            category=_safe_optional_text(labels.get("category")),
            labels=labels,
            annotations=annotations,
            generator_url=_safe_optional_text(raw.get("generatorURL")),
        ))

    # Sort: critical → warning → info → other, then by startsAt (newer on top)
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(
        key=lambda a: (severity_order.get(a.severity, 99), a.starts_at),
        reverse=False,
    )
    alerts.sort(key=lambda a: severity_order.get(a.severity, 99))

    return AlertsResponse(
        collected_at=datetime.now(UTC),
        alertmanager_available=True,
        active_count=len(alerts),
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
        alerts=alerts,
    )


@router.get(
    "/tools",
    response_model=ExternalToolsDTO,
    summary="URLs of external monitoring tools",
)
async def get_external_tools(
    user: CurrentUser = Depends(get_current_user),
) -> ExternalToolsDTO:
    """
    Return URLs of Grafana / Prometheus / Alertmanager + expanded
    list of services and Grafana dashboards for admin panel.

    Source of truth is backend settings of the current environment.
    Frontend should not guess URLs on its own.

    Expanded lists (services, dashboards) are filled only for
    superadmin — tenant_admin receives is_superadmin=False and empty lists.
    """
    _require_tenant_admin(user)
    return _build_external_tools_response(
        is_superadmin=user.global_role == "superadmin"
    )


# ─── Tenant Locale Policy settings (Sprint 6.7) ───────────────────────────

class TenantLocalePolicyDTO(BaseModel):
    allowed_locales: list[str] = Field(default_factory=list, description="Allowed BCP 47 codes (e.g. ['en', 'ru'])")
    is_translation_enabled: bool = Field(default=True, description="Enable or disable translation pipeline")
    restrict_to_allowed: bool = Field(default=True, description="Strictly enforce allowed_locales validation")


@router.get(
    "/locale-policy",
    response_model=TenantLocalePolicyDTO,
    summary="Get tenant result locale policy settings",
)
async def get_tenant_locale_policy(
    tenant_id: uuid.UUID | None = Query(
        default=None,
        description="Only for superadmin: context tenant id",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> TenantLocalePolicyDTO:
    _require_tenant_admin(user)
    resolved_tenant_id = _resolve_tenant_id(user, tenant_id)

    repo = TenantLocalePolicyRepository(db)
    policy = await repo.get_by_tenant_id(resolved_tenant_id)

    if policy is None:
        # Return default policy if not explicitly configured in DB
        return TenantLocalePolicyDTO(
            allowed_locales=[],
            is_translation_enabled=True,
            restrict_to_allowed=False,
        )

    return TenantLocalePolicyDTO(
        allowed_locales=policy.allowed_locales,
        is_translation_enabled=policy.is_translation_enabled,
        restrict_to_allowed=policy.restrict_to_allowed,
    )


@router.put(
    "/locale-policy",
    response_model=TenantLocalePolicyDTO,
    summary="Update or create tenant result locale policy",
)
async def update_tenant_locale_policy(
    payload: TenantLocalePolicyDTO,
    tenant_id: uuid.UUID | None = Query(
        default=None,
        description="Only for superadmin: context tenant id",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> TenantLocalePolicyDTO:
    _require_tenant_admin(user)
    resolved_tenant_id = _resolve_tenant_id(user, tenant_id)

    # Validate that BCP 47 locales are globally supported
    supported = get_supported_result_locales()
    for loc in payload.allowed_locales:
        norm = loc.strip().lower()
        if norm not in supported:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Locale '{loc}' is not supported globally.",
            )

    repo = TenantLocalePolicyRepository(db)
    policy = await repo.get_by_tenant_id(resolved_tenant_id)

    if policy is None:
        policy = TenantResultLocalePolicy(
            tenant_id=resolved_tenant_id,
            allowed_locales=[loc.strip().lower() for loc in payload.allowed_locales],
            is_translation_enabled=payload.is_translation_enabled,
            restrict_to_allowed=payload.restrict_to_allowed,
        )
        db.add(policy)
    else:
        policy.allowed_locales = [loc.strip().lower() for loc in payload.allowed_locales]
        policy.is_translation_enabled = payload.is_translation_enabled
        policy.restrict_to_allowed = payload.restrict_to_allowed

    await db.commit()

    # Log action to audit trail
    try:
        audit_repo = AuditRepository(db)
        await audit_repo.log(
            tenant_id=resolved_tenant_id,
            action="tenant.locale_policy_updated",
            actor=user.email or str(user.id),
            details={
                "allowed_locales": policy.allowed_locales,
                "is_translation_enabled": policy.is_translation_enabled,
                "restrict_to_allowed": policy.restrict_to_allowed,
            },
        )
        await db.commit()
    except Exception:
        logger.exception("Failed to log locale policy update audit log")

    return TenantLocalePolicyDTO(
        allowed_locales=policy.allowed_locales,
        is_translation_enabled=policy.is_translation_enabled,
        restrict_to_allowed=policy.restrict_to_allowed,
    )
