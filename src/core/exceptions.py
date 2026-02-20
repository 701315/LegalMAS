"""
Exception hierarchy for the MAS DD system.

TransientError  -> will be retried automatically (network issues, timeouts)
PermanentError  -> will NOT be retried, goes to DLQ (bad data, logic errors)
"""


class MASBaseError(Exception):
    """Base exception for all MAS DD errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class TransientError(MASBaseError):
    """
    Retryable error.
    Examples: network timeout, service temporarily unavailable,
    database connection lost.
    """

    pass


class PermanentError(MASBaseError):
    """
    Non-retryable error.
    Examples: invalid file format, missing required field,
    business logic violation.
    """

    pass


class QuarantineError(MASBaseError):
    """
    Document should be placed in quarantine.
    Examples: OCR confidence too low, corrupted PDF,
    unsupported format.
    """

    def __init__(
        self,
        message: str,
        document_id: str | None = None,
        reason: str = "unknown",
        details: dict | None = None,
    ):
        super().__init__(message, details)
        self.document_id = document_id
        self.reason = reason


class EvidenceNotFoundError(PermanentError):
    """
    Evidence was not found in raw text.
    Result must be set to UNCLEAR per Evidence First principle.
    """

    pass


class CircuitOpenError(TransientError):
    """
    Circuit breaker is in OPEN state.
    External service is considered unavailable,
    fallback should be used.
    """

    def __init__(self, circuit_name: str):
        super().__init__(
            message=f"Circuit breaker '{circuit_name}' is OPEN",
            details={"circuit_name": circuit_name},
        )
        self.circuit_name = circuit_name


class IdempotencyConflictError(PermanentError):
    """
    Duplicate request with same idempotency key but different payload.
    """

    pass
