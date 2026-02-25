"""Tests for structured logging setup."""

from src.core.logging import deal_id_var, get_logger, request_id_var, setup_logging


def test_logger_can_be_created():
    """get_logger should return a bound logger."""
    setup_logging()
    logger = get_logger("test_module")
    assert logger is not None


def test_logger_accepts_structured_data(capsys):
    """Logger should accept keyword arguments as structured data."""
    setup_logging()
    logger = get_logger("test_structured")
    # This should not raise
    logger.info("test event", doc_id="123", pages=45, status="ok")


def test_context_vars_have_defaults():
    """Context variables should have None as default."""
    assert request_id_var.get() is None
    assert deal_id_var.get() is None
