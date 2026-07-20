# src/engine/checks/snapshot_policy.py

"""
Snapshot policy: централизованная политика допустимости filesystem fallback.

Единственное место в системе, где принимается решение:
- разрешён ли filesystem fallback для данного Run
- как обрабатывать отсутствие payload в snapshot

Правила:
    Run.snapshot_schema_version IS NULL → legacy, filesystem fallback разрешён
    Run.snapshot_schema_version >= 1    → strict, filesystem fallback запрещён

Legacy Run:
    - is_reproducible = False
    - предупреждение в логах и в API ответе
    - filesystem fallback разрешён ТОЛЬКО для rendering/read-only

Strict Run:
    - is_reproducible = True
    - отсутствие payload для doc_type = ConfigurationIntegrityError
    - filesystem fallback запрещён полностью
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SNAPSHOT_SCHEMA_VERSION_CURRENT = 1


class ConfigurationIntegrityError(Exception):
    """
    Поднимается когда strict Run не имеет frozen payload для требуемого doc_type.

    Filesystem fallback запрещён для strict Run.
    """

    def __init__(self, run_id: str, doc_type: str):
        super().__init__(
            f"Run {run_id} (snapshot_schema_version >= 1) "
            f"has no frozen payload for doc_type='{doc_type}'. "
            f"Filesystem fallback is forbidden for strict snapshot runs."
        )
        self.run_id = run_id
        self.doc_type = doc_type


@dataclass(frozen=True, slots=True)
class SnapshotResolutionResult:
    payload: dict | None
    is_legacy: bool
    warning: str | None = None

    @property
    def is_reproducible(self) -> bool:
        return not self.is_legacy


def resolve_doc_type_payload(
    *,
    run_id: str,
    snapshot_schema_version: int | None,
    instruction_snapshot_payload: dict | None,
    doc_type: str,
) -> SnapshotResolutionResult:
    """
    Resolves payload для конкретного doc_type с учётом snapshot policy.

    Args:
        run_id: ID Run (для логов и ошибок)
        snapshot_schema_version: None=legacy, >=1=strict
        instruction_snapshot_payload: frozen payload из Run
        doc_type: код типа документа

    Returns:
        SnapshotResolutionResult

    Raises:
        ConfigurationIntegrityError: если strict Run не имеет payload
    """
    is_legacy = snapshot_schema_version is None

    if is_legacy:
        logger.warning(
            "snapshot_policy: legacy run without frozen snapshot, "
            "filesystem fallback permitted. Results marked is_reproducible=False.",
            extra={
                "run_id": run_id,
                "doc_type": doc_type,
                "snapshot_schema_version": snapshot_schema_version,
            },
        )
        payload = (
            (instruction_snapshot_payload or {}).get(doc_type)
            if instruction_snapshot_payload
            else None
        )
        return SnapshotResolutionResult(
            payload=payload,
            is_legacy=True,
            warning=(
                f"Run {run_id} was created before immutable snapshots. "
                "Historical accuracy cannot be guaranteed."
            ),
        )

    # Strict mode
    if not instruction_snapshot_payload:
        raise ConfigurationIntegrityError(run_id=run_id, doc_type=doc_type)

    doc_type_payload = instruction_snapshot_payload.get(doc_type)
    if doc_type_payload is None:
        raise ConfigurationIntegrityError(run_id=run_id, doc_type=doc_type)

    return SnapshotResolutionResult(
        payload=doc_type_payload,
        is_legacy=False,
        warning=None,
    )


def check_snapshot_integrity(
    *,
    run_id: str,
    snapshot_schema_version: int | None,
    instruction_snapshot_payload: dict | None,
) -> tuple[bool, str | None]:
    """
    Проверяет общую integrity snapshot для Run (не для конкретного doc_type).

    Returns:
        (is_valid, warning_message)
    """
    if snapshot_schema_version is None:
        return True, (
            f"Run {run_id} is a legacy run without immutable snapshot. "
            "is_reproducible=False."
        )

    if not instruction_snapshot_payload:
        return False, (
            f"Run {run_id} has snapshot_schema_version={snapshot_schema_version} "
            "but no instruction_snapshot_payload. ConfigurationIntegrity violated."
        )

    return True, None


