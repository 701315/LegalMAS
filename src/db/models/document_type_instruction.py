# src/db/models/document_type_instruction.py

"""
Document type instruction version model.

Хранит исторический snapshot YAML-инструкции для конкретного doc_type.

Зачем это нужно:
- чтобы понимать, по какой именно версии YAML-инструкции был классифицирован документ;
- чтобы можно было воспроизвести или показать пользователю использованную инструкцию;
- чтобы не зависеть от текущего состояния runtime YAMLRegistry для historical analysis.
"""

from __future__ import annotations

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class DocumentTypeInstructionVersion(Base):
    """
    Историческая версия YAML-инструкции для одного типа документа.

    Для непрофессионального программиста:
    - одна запись = один сохранённый snapshot YAML;
    - doc_type_code говорит, к какому типу документа относится инструкция;
    - source_yaml хранит полный текст YAML;
    - source_sha256 позволяет понять, что это именно эта версия файла.
    """

    __tablename__ = "document_type_instruction_versions"

    doc_type_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Machine-readable document type code, e.g. 'nda', 'real_estate_sale'.",
    )

    name: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
        comment="Optional display name of the document type instruction.",
    )

    source_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="yaml",
        comment="Source format of the instruction snapshot, currently 'yaml'.",
    )

    source_yaml: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full raw YAML snapshot used for classification.",
    )

    source_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA256 hash of the raw YAML snapshot.",
    )

    source_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Original repository/registry path of the YAML file, if known.",
    )

    git_commit: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="Git commit hash of the source repository, if available.",
    )

    semver: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Optional human-readable semantic version, if maintained manually.",
    )

    compiled_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Optional normalized/compiled representation of the instruction.",
    )

    __table_args__ = (
        Index(
            "idx_doc_type_instruction_versions_doc_type_code",
            "doc_type_code",
        ),
        Index(
            "idx_doc_type_instruction_versions_sha256",
            "source_sha256",
        ),
        UniqueConstraint(
            "doc_type_code",
            "source_sha256",
            name="uq_doc_type_instruction_versions_doc_type_code_sha256",
        ),
    )
