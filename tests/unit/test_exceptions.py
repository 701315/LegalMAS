"""Tests for exception hierarchy."""

from src.core.exceptions import (
    CircuitOpenError,
    EvidenceNotFoundError,
    IdempotencyConflictError,
    MASBaseError,
    PermanentError,
    QuarantineError,
    TransientError,
)


def test_transient_error_is_mas_error():
    """TransientError should be a subclass of MASBaseError."""
    err = TransientError("network timeout")
    assert isinstance(err, MASBaseError)
    assert err.message == "network timeout"
    assert err.details == {}


def test_permanent_error_is_mas_error():
    """PermanentError should be a subclass of MASBaseError."""
    err = PermanentError("invalid format", details={"file": "test.xyz"})
    assert isinstance(err, MASBaseError)
    assert err.details == {"file": "test.xyz"}


def test_quarantine_error_has_document_info():
    """QuarantineError should carry document_id and reason."""
    err = QuarantineError(
        "OCR confidence too low",
        document_id="doc-123",
        reason="ocr_low_confidence",
    )
    assert err.document_id == "doc-123"
    assert err.reason == "ocr_low_confidence"


def test_evidence_not_found_is_permanent():
    """EvidenceNotFoundError should be a PermanentError (no retry)."""
    err = EvidenceNotFoundError("snippet not in raw text")
    assert isinstance(err, PermanentError)
    assert isinstance(err, MASBaseError)


def test_circuit_open_is_transient():
    """CircuitOpenError should be a TransientError (will retry/fallback)."""
    err = CircuitOpenError("openai")
    assert isinstance(err, TransientError)
    assert err.circuit_name == "openai"
    assert "openai" in str(err)


def test_idempotency_conflict_is_permanent():
    """IdempotencyConflictError should be a PermanentError."""
    err = IdempotencyConflictError("duplicate key with different payload")
    assert isinstance(err, PermanentError)


def test_exception_inheritance_chain():
    """Verify the full inheritance chain matches the specification."""
    # TransientError -> MASBaseError -> Exception
    assert issubclass(TransientError, MASBaseError)
    assert issubclass(TransientError, Exception)

    # PermanentError -> MASBaseError -> Exception
    assert issubclass(PermanentError, MASBaseError)

    # CircuitOpenError -> TransientError -> MASBaseError
    assert issubclass(CircuitOpenError, TransientError)

    # EvidenceNotFoundError -> PermanentError -> MASBaseError
    assert issubclass(EvidenceNotFoundError, PermanentError)

    # QuarantineError -> MASBaseError (NOT TransientError or PermanentError)
    assert issubclass(QuarantineError, MASBaseError)
    assert not issubclass(QuarantineError, TransientError)
    assert not issubclass(QuarantineError, PermanentError)
