# src/core/logging.py

"""
Structured logging setup using structlog.

Goals:
- unified structured logging for API, workers and system tasks;
- correlation context automatically added to every log record;
- support for stdout and rotating file handlers;
- compatibility with legacy logger calls using `extra={...}`.
"""

from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

import structlog

from .config import settings

# ---------------------------------------------------------------------------
# Context variables
# ---------------------------------------------------------------------------

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)
deal_id_var: ContextVar[str | None] = ContextVar("deal_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)
document_id_var: ContextVar[str | None] = ContextVar("document_id", default=None)
task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)
stage_var: ContextVar[str | None] = ContextVar("stage", default=None)
actor_role_var: ContextVar[str | None] = ContextVar("actor_role", default=None)
worker_hostname_var: ContextVar[str | None] = ContextVar("worker_hostname", default=None)
queue_var: ContextVar[str | None] = ContextVar("queue", default=None)

_CONTEXT_VARS: tuple[tuple[str, ContextVar[str | None]], ...] = (
    ("request_id", request_id_var),
    ("tenant_id", tenant_id_var),
    ("deal_id", deal_id_var),
    ("run_id", run_id_var),
    ("document_id", document_id_var),
    ("task_id", task_id_var),
    ("stage", stage_var),
    ("actor_role", actor_role_var),
    ("worker_hostname", worker_hostname_var),
    ("queue", queue_var),
)


def _coerce_str(value: object | None) -> str | None:
    """
    Convert context value to a clean string.

    Returns None for empty / blank values.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clear_log_context() -> None:
    """Clear all known logging context variables."""
    for _, var in _CONTEXT_VARS:
        var.set(None)


def bind_log_context(
    *,
    request_id: object | None = None,
    tenant_id: object | None = None,
    deal_id: object | None = None,
    run_id: object | None = None,
    document_id: object | None = None,
    task_id: object | None = None,
    stage: object | None = None,
    actor_role: object | None = None,
    worker_hostname: object | None = None,
    queue: object | None = None,
) -> None:
    """
    Bind selected context values for subsequent log records.

    Only non-empty values are written.
    Existing values for fields not passed remain unchanged.
    """
    values = {
        request_id_var: _coerce_str(request_id),
        tenant_id_var: _coerce_str(tenant_id),
        deal_id_var: _coerce_str(deal_id),
        run_id_var: _coerce_str(run_id),
        document_id_var: _coerce_str(document_id),
        task_id_var: _coerce_str(task_id),
        stage_var: _coerce_str(stage),
        actor_role_var: _coerce_str(actor_role),
        worker_hostname_var: _coerce_str(worker_hostname),
        queue_var: _coerce_str(queue),
    }
    for var, value in values.items():
        if value is not None:
            var.set(value)


def set_request_context(
    *,
    request_id: object | None,
    tenant_id: object | None = None,
    deal_id: object | None = None,
    actor_role: object | None = None,
) -> None:
    """
    Reset and bind request-scoped logging context.
    """
    clear_log_context()
    bind_log_context(
        request_id=request_id,
        tenant_id=tenant_id,
        deal_id=deal_id,
        actor_role=actor_role,
    )


def set_task_context(
    *,
    task_id: object | None,
    tenant_id: object | None = None,
    deal_id: object | None = None,
    run_id: object | None = None,
    document_id: object | None = None,
    stage: object | None = None,
    actor_role: object | None = None,
    worker_hostname: object | None = None,
    queue: object | None = None,
    request_id: object | None = None,
) -> None:
    """
    Reset and bind task-scoped logging context.
    """
    clear_log_context()
    bind_log_context(
        request_id=request_id,
        tenant_id=tenant_id,
        deal_id=deal_id,
        run_id=run_id,
        document_id=document_id,
        task_id=task_id,
        stage=stage,
        actor_role=actor_role,
        worker_hostname=worker_hostname,
        queue=queue,
    )


def add_context(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """
    Add all known context variables to every log entry.
    """
    _ = logger, method_name

    for field_name, var in _CONTEXT_VARS:
        value = var.get()
        if value:
            event_dict[field_name] = value

    event_dict.setdefault("environment", settings.ENVIRONMENT)
    return event_dict


def flatten_extra_processor(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """
    Flatten legacy `extra={...}` payloads into top-level structured fields.

    This is a migration aid for existing worker code that still calls:
        logger.info("...", extra={"run_id": "...", "deal_id": "..."})
    instead of native structlog style:
        logger.info("...", run_id="...", deal_id="...")
    """
    _ = logger, method_name

    extra = event_dict.pop("extra", None)
    if isinstance(extra, dict):
        for key, value in extra.items():
            event_dict.setdefault(key, value)

    return event_dict


def _shared_processors() -> list[structlog.types.Processor]:
    """
    Processors shared by structlog and stdlib logging.
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.ExtraAdder(),
        add_context,
        flatten_extra_processor,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]


def _build_renderer() -> structlog.types.Processor:
    """
    Select renderer according to settings.LOG_FORMAT.
    """
    if settings.LOG_FORMAT == "json":
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=True)


def _build_formatter(
    shared_processors: list[structlog.types.Processor],
    renderer: structlog.types.Processor,
) -> structlog.stdlib.ProcessorFormatter:
    """
    Create ProcessorFormatter for stdlib logging integration.
    """
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )


def _build_rotating_file_handler(
    *,
    base_dir: str,
    file_name: str,
    formatter: logging.Formatter,
) -> logging.Handler:
    """
    Create rotating file handler with shared formatter.
    """
    os.makedirs(base_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(base_dir, file_name),
        maxBytes=settings.LOG_FILE_MAX_BYTES,
        backupCount=settings.LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    return handler


def _configure_noisy_loggers() -> None:
    """
    Reduce noise from third-party libraries.
    """
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("minio").setLevel(logging.WARNING)
    logging.getLogger("kombu").setLevel(logging.WARNING)


def setup_logging() -> None:
    """
    Configure structlog and standard logging.

    Safe to call multiple times:
    - existing root handlers are replaced;
    - structlog is reconfigured to current settings.
    """
    shared_processors = _shared_processors()
    renderer = _build_renderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = _build_formatter(shared_processors, renderer)

    handlers: list[logging.Handler] = []

    if settings.LOG_TO_STDOUT:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        handlers.append(stdout_handler)

    if settings.LOG_TO_FILE and settings.LOG_FILE_DIR:
        file_handler = _build_rotating_file_handler(
            base_dir=settings.LOG_FILE_DIR,
            file_name=settings.LOG_FILE_NAME,
            formatter=formatter,
        )
        handlers.append(file_handler)

    if not handlers:
        fallback_handler = logging.StreamHandler(sys.stdout)
        fallback_handler.setFormatter(formatter)
        handlers.append(fallback_handler)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    for handler in handlers:
        root_logger.addHandler(handler)

    root_logger.setLevel(settings.LOG_LEVEL.upper())

    _configure_noisy_loggers()

    if settings.LOG_TO_FILE and not settings.LOG_FILE_DIR:
        logging.getLogger(__name__).warning(
            "LOG_TO_FILE is enabled but LOG_FILE_DIR is not set; file logging skipped"
        )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Return a structured logger instance.

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing document", document_id="123", pages=45)
    """
    return structlog.get_logger(name)



