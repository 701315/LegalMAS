"""
Structured logging setup using structlog.

In development: pretty console output with colors.
In production:  JSON output for log aggregation (ELK, etc.).
"""

import logging
import structlog
import sys

from contextvars import ContextVar

from .config import settings

# Context variables for request tracing.
# These are set by workers/API handlers and automatically
# included in every log message.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
deal_id_var: ContextVar[str | None] = ContextVar("deal_id", default=None)
document_id_var: ContextVar[str | None] = ContextVar("document_id", default=None)


def add_context(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Add context variables to every log entry."""
    request_id = request_id_var.get()
    if request_id:
        event_dict["request_id"] = request_id

    deal_id = deal_id_var.get()
    if deal_id:
        event_dict["deal_id"] = deal_id

    document_id = document_id_var.get()
    if document_id:
        event_dict["document_id"] = document_id

    return event_dict


def setup_logging() -> None:
    """
    Configure structlog and standard logging.
    Call this once at application startup.
    """
    # Shared processors for both structlog and standard logging
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_context,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.LOG_FORMAT == "json":
        # Production: JSON output
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: pretty console output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to use structlog formatting
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.LOG_LEVEL.upper())

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("minio").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger.

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing document", doc_id="123", pages=45)
    """
    return structlog.get_logger(name)
