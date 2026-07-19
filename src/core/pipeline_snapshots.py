# src/core/pipeline_snapshots.py

"""
Shared immutable pipeline snapshots.

Зачем нужен этот модуль:
- orchestration/service слой не должен зависеть от "живучести" ORM-объектов;
- Async SQLAlchemy ORM нельзя безопасно таскать через await/UoW boundaries;
- поэтому после read-phase ORM-объекты нужно немедленно превращать
  в обычные Python value objects (snapshots).

Этот модуль хранит общие snapshot-контракты для pipeline / orchestration / checks слоёв.

Правило использования:
1) сначала загрузили ORM-объект;
2) сразу вызвали snapshot_*();
3) дальше работаем только со snapshot/примитивами.

Важно:
- snapshots не делают I/O;
- snapshots не зависят от SQLAlchemy;
- snapshots можно безопасно передавать:
  * через await-границы,
  * между разными UnitOfWork,
  * в helper/service/engine слой.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Internal normalization helpers
# ──────────────────────────────────────────────────────────────────────────────


def _normalize_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_optional_lower_str(value: Any) -> str | None:
    text = _normalize_optional_str(value)
    return text.lower() if text else None


def _normalize_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _normalize_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_bool(value: Any) -> bool:
    return bool(value)


def _normalize_str_tuple(value: Any) -> tuple[str, ...]:
    """
    Нормализовать sequence-подобное значение в immutable tuple[str].

    Для непрофессионального программиста:
    - если значение не список/кортеж/итерируемая коллекция — вернём пустой tuple;
    - берём только строковые элементы;
    - tuple используется для immutability snapshot'а.
    """
    if isinstance(value, Iterable) and not isinstance(value, str | bytes):
        return tuple(item for item in value if isinstance(item, str))
    return ()


# ──────────────────────────────────────────────────────────────────────────────
# Run snapshot
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    id: uuid.UUID
    status: str

    deal_id: uuid.UUID | None = None

    # tenant_id — первичный источник истины для orchestration/audit.
    # Читается из Run.tenant_id при снятии snapshot.
    # Не должен передаваться через task kwargs или logging context.
    tenant_id: uuid.UUID | None = None

    pipeline_strategy: str | None = None

    checks_mode: str | None = None
    checks_scope: dict[str, Any] | None = None

    playbook_version_id: uuid.UUID | None = None
    instruction_versions: dict[str, str] | None = None  # {doc_type: version_id_str}
    instruction_snapshot_manifest: dict[str, Any] | None = None  # {doc_type: {version_id, content_hash, override_id}}
    instruction_snapshot_payload: dict[str, Any] | None = None  # {doc_type: full_yaml_dict}


    total_checks: int = 0
    completed_checks: int = 0
    has_errors: bool = False

    @property
    def run_id(self) -> uuid.UUID:
        return self.id

    @property
    def run_id_str(self) -> str:
        return str(self.id)

    @property
    def deal_id_str(self) -> str | None:
        return str(self.deal_id) if self.deal_id else None


def snapshot_run(run: Any) -> RunSnapshot:
    """
    Снять immutable snapshot с ORM-объекта Run.

    Вызывать сразу после загрузки ORM-объекта, до первого await.
    tenant_id читается напрямую из Run — это первичный источник истины
    для orchestration/audit цепочки.
    """
    return RunSnapshot(
        id=run.id,
        status=str(getattr(run, "status", "") or ""),
        deal_id=getattr(run, "deal_id", None),
        tenant_id=getattr(run, "tenant_id", None),
        pipeline_strategy=_normalize_optional_str(getattr(run, "pipeline_strategy", None)),
        checks_mode=_normalize_optional_str(getattr(run, "checks_mode", None)),
        checks_scope=getattr(run, "checks_scope", None),
        playbook_version_id=getattr(run, "playbook_version_id", None),
        total_checks=_normalize_int(getattr(run, "total_checks", 0), default=0),
        completed_checks=_normalize_int(getattr(run, "completed_checks", 0), default=0),
        has_errors=_normalize_bool(getattr(run, "has_errors", False)),
        instruction_versions=getattr(run, "instruction_versions", None),
        instruction_snapshot_manifest=getattr(run, "instruction_snapshot_manifest", None),
        instruction_snapshot_payload=getattr(run, "instruction_snapshot_payload", None),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Document snapshot
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    """
    Immutable snapshot Document.

    Содержит superset полей, которые реально нужны в:
    - run_orchestrator
    - language_discovery_orchestrator
    - checks execution stack
    """

    id: uuid.UUID

    status: str = ""

    doc_type: str | None = None
    classification_level: str | None = None
    classification_confidence: float | None = None

    applicable_triggers: tuple[str, ...] = ()
    detected_languages: tuple[str, ...] = ()

    @property
    def document_id(self) -> uuid.UUID:
        return self.id

    @property
    def document_id_str(self) -> str:
        return str(self.id)


def snapshot_document(doc: Any) -> DocumentSnapshot:
    """
    Снять immutable snapshot с ORM-объекта Document.

    Вызывать сразу после загрузки ORM-объекта, до первого await.
    """
    return DocumentSnapshot(
        id=doc.id,
        status=str(getattr(doc, "status", "") or ""),
        doc_type=_normalize_optional_str(getattr(doc, "doc_type", None)),
        classification_level=_normalize_optional_str(getattr(doc, "classification_level", None)),
        classification_confidence=_normalize_float(getattr(doc, "classification_confidence", None)),
        applicable_triggers=_normalize_str_tuple(getattr(doc, "applicable_triggers", None)),
        detected_languages=_normalize_str_tuple(getattr(doc, "detected_languages", None)),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Version snapshot
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class VersionSnapshot:
    """
    Immutable snapshot DocumentVersion.

    Содержит superset полей, которые реально нужны в:
    - run_orchestrator
    - language_discovery_orchestrator
    """

    id: uuid.UUID

    origin_filetype: str | None = None
    original_ref: str | None = None
    converted_pdf_ref: str | None = None
    primary_source_ref: str | None = None
    layout_primary_ref: str | None = None
    layout_primary_sanitized_ref: str | None = None
    file_graph_ref: str | None = None
    chunks_manifest_v2_ref: str | None = None
    segments_count: int | None = None

    pipeline_strategy: str | None = None
    extraction_strategy: str | None = None
    ocr_confidence: float | None = None

    @property
    def version_id(self) -> uuid.UUID:
        return self.id

    @property
    def version_id_str(self) -> str:
        return str(self.id)


def snapshot_version(version: Any) -> VersionSnapshot:
    """
    Снять immutable snapshot с ORM-объекта DocumentVersion.

    Вызывать сразу после загрузки ORM-объекта, до первого await.
    """
    segments_count_raw = getattr(version, "segments_count", None)
    segments_count = (
        _normalize_int(segments_count_raw, default=0) if segments_count_raw is not None else None
    )

    return VersionSnapshot(
        id=version.id,
        origin_filetype=_normalize_optional_lower_str(getattr(version, "origin_filetype", None)),
        original_ref=_normalize_optional_str(getattr(version, "original_ref", None)),
        converted_pdf_ref=_normalize_optional_str(getattr(version, "converted_pdf_ref", None)),
        primary_source_ref=_normalize_optional_str(getattr(version, "primary_source_ref", None)),
        layout_primary_ref=_normalize_optional_str(getattr(version, "layout_primary_ref", None)),
        layout_primary_sanitized_ref=_normalize_optional_str(
            getattr(version, "layout_primary_sanitized_ref", None)
        ),
        file_graph_ref=_normalize_optional_str(getattr(version, "file_graph_ref", None)),
        chunks_manifest_v2_ref=_normalize_optional_str(
            getattr(version, "chunks_manifest_v2_ref", None)
        ),
        segments_count=segments_count,
        pipeline_strategy=_normalize_optional_lower_str(
            getattr(version, "pipeline_strategy", None)
        ),
        extraction_strategy=_normalize_optional_lower_str(
            getattr(version, "extraction_strategy", None)
        ),
        ocr_confidence=_normalize_float(getattr(version, "ocr_confidence", None)),
    )
