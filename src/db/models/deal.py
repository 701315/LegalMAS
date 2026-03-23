# src/db/models/deal.py

"""
ORM-модель Deal описывает сделку (проект due diligence) в системе.

Сделка — это верхнеуровневый объект, к которому привязаны:
- арендатор (tenant), от имени которого ведётся проект;
- базовые атрибуты сделки: название, тип, юрисдикция, языки документов;
- технический статус прохождения пайплайна (created, в работе и т.п.);
- режим обработки ПДн (pii_mode) — только локально или с облачным fallback;
- профиль проверки (profile) — core/full/max на уровне методологии;
- выбранная версия плейбука (playbook_version_id), которая задаёт набор проверок;
- явный профиль моделей ИИ (model_config_id), если он выбран для этой сделки;
- последний запущенный анализ (last_run_id) для быстрого доступа к результатам;
- произвольные дополнительные метаданные (metadata_).

Эта модель используется:
- в репозитории сделок (DealRepository) для CRUD-операций;
- в REST-API сделок для создания проектов, смены плейбука и профиля модели,
  запуска анализа и отображения статуса;
- как корневая сущность, к которой косвенно привязаны документы, запуски (Run),
  результаты проверок, экспортируемые отчёты и аудит-логи.
"""

import uuid

from sqlalchemy import Index, String, ForeignKey, Enum  # <— добавили Enum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import DealStatus, PIIMode
from ..base import Base


class Deal(Base):
    __tablename__ = "deals"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    deal_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="E.g. SPA, SHA, Asset Purchase",
    )

    jurisdiction: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="E.g. RU, EN, RU/EN",
    )

    languages: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(10)),
        nullable=True,
        comment="Document languages: ['RU', 'EN']",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DealStatus.CREATED.value,
    )

    pii_mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=PIIMode.LOCAL_ONLY.value,
        comment="152-FZ: local_only or cloud_fallback_allowed",
    )

    profile: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="full",
        comment="Check profile: core, full, max",
    )

    playbook_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Selected playbook version (FK added after PlaybookVersion model)",
    )

    # Новый атрибут: явный профиль модели для сделки
    model_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_configs.id", ondelete="SET NULL"),
        nullable=True,
        comment=(
            "Explicit ModelConfig selected for this deal; "
            "if NULL, profile from PlaybookVersion is used"
        ),
    )

    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID of the latest analysis run for this deal",
    )


    last_run_checks_mode: Mapped[str | None] = mapped_column(
        Enum(
            "global_only",
            "doc_type_only",
            "global_and_doc_type",
            name="run_checks_mode",
        ),
        nullable=True,
        comment=(
            "Checks mode of the latest run: "
            "global_only / doc_type_only / global_and_doc_type"
        ),
    )

    last_run_pipeline_strategy: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Pipeline strategy of the latest run (e.g. REUSE_STRUCTURE, FULL_RERUN)",
    )

    # Флаг: есть ли незакрытые ручные переклассификации документов по сделке,
    # требующие запуска нового анализа.
    has_pending_manual_reclassifications: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
        comment=(
            "True — есть документы, переклассифицированные вручную, "
            "и анализ по сделке ещё не был перезапущен после этого"
        ),
    )

    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment="Arbitrary deal metadata",
    )

    __table_args__ = (
        Index("idx_deals_tenant_status", "tenant_id", "status"),
    )

