# src/api/schemas/runs.py

"""
Pydantic‑схемы для запусков анализа (Run) и их статуса.

Зачем нужен этот модуль:
- описывает формат запросов и ответов для работы с Run:
  - создание нового запуска анализа по сделке;
  - получение текущего статуса Run и прогресса выполнения;
  - получение агрегированной статистики по классификации;
- фронтенд использует эти схемы, чтобы:
  - показывать юристу, что происходит с анализом сделки (status, progress);
  - отображать, насколько хорошо отработала классификация (coverage, confidence);
  - подсвечивать Run'ы с проблемами (completed_with_errors, failed).

Важно про статусы Run (status: str):
- "pending"  — Run создан, но пайплайн ещё не запускался;
- "running"  — оркестратор поставил задачи, анализ в процессе;
- "completed" — все документы, запланированные в Run,
                успешно прошли checks (нет FAILED/QUARANTINE);
- "completed_with_errors" — анализ в целом завершён, но часть документов
                             в статусах FAILED или QUARANTINE;
- "failed" — Run не смог корректно выполниться из‑за
             критической ошибки пайплайна (например,
             проблемы с БД/MinIO или неконсистентная конфигурация).

Поле error_details (dict | None):
- описывает ошибку уровня Run (не отдельного документа);
- формат согласован с backend'ом и включает, как минимум:
    {
        "type": "infrastructure_error" | "config_error" | "...",
        "stage": "orchestrator" | "checks" | "...",
        "reason": "<краткий код причины>",
        "message": "<человекочитаемое описание>",
        "timestamp": "<ISO8601 UTC>"
    }
- фронт использует это поле, чтобы показать юристу понятное сообщение
  («Run не удалось запустить из‑за ошибки конфигурации плейбука» и т.п.).

Основные схемы:
- RunCreate — запрос на запуск анализа (profile, playbook_version_id,
  флаг force_reclassify для принудительного переклассифицирования).
- RunResponse — краткий статус конкретного Run (для карточки сделки/страницы Run).
- RunProgressResponse — лёгкая схема прогресса для SSE/поллинга.
- ClassificationReportResponse — полный отчёт по качеству классификации
  для одного Run (low_confidence_docs, unknown_type_docs, trigger_coverage).
- DealRunSummaryResponse — агрегированный статус последнего Run по сделке
  для отображения в карточке сделки.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    """
    Запрос на запуск анализа по сделке.

    profile:
      - "core"  — минимальный набор проверок;
      - "full"  — полный набор;
      - "max"   — максимум, что умеет система (может быть медленнее/дороже).

    checks_mode:
      - "global_only"          — запускать только проверки из глобального плейбука;
      - "doc_type_only"        — запускать только проверки из инструкций по типам;
      - "global_and_doc_type"  — запускать оба слоя (текущая логика по умолчанию).

    force_reclassify:
      - False (по умолчанию) — переиспользовать уже готовую классификацию,
        запускать только checks;
      - True — перед запуском checks ещё раз прогнать классификацию по всем
        документам (hybrid/LLM), чтобы учесть новые модели/правила.
    """

    playbook_version_id: UUID | None = None
    profile: str = Field(default="core", description="core / full / max")

    # Новый режим: какие проверки включать в Run
    checks_mode: str = Field(
        default="global_and_doc_type",
        description=("Режим проверок: " "global_only / doc_type_only / global_and_doc_type"),
    )

    # Новый флаг: перед запуском проверок заново классифицировать документы
    force_reclassify: bool = Field(
        default=False,
        description="Re-run HybridClassifier on all documents before checks",
    )


class ClassificationStats(BaseModel):
    """
    Статистика качества классификации для одного Run.

    Показывает, сколько документов попало на каждый уровень L0-L4,
    сколько низкоуверенных и сколько с неизвестным типом.
    """

    total_documents: int = 0
    l0_no_match: int = 0
    l1_filename: int = 0
    l2_keyword: int = 0
    l3_semantic: int = 0
    l4_llm: int = 0
    low_confidence_count: int = 0  # confidence < 0.6
    unknown_doc_type_count: int = 0  # doc_type = "Generic" или None


class RunResponse(BaseModel):
    """
    Краткий статус запуска анализа.

    Используется в UI для отображения прогресса и качества классификации
    по конкретному Run (например, в карточке сделки или на странице Run).

    Основные поля для фронта:

    - status:
        "pending" / "running" / "completed" / "completed_with_errors" / "failed";
    - total_checks / completed_checks:
        сколько документов должны пройти checks и сколько уже прошли;
        по этим полям UI может рисовать прогрессбар (процент выполнения);
    - error_details:
        агрегированная ошибка уровня Run (если есть);
    - classification_stats:
        summary по качеству классификации (если рассчитано);
    - pipeline_strategy:
        как запуск использует уже существующие артефакты:
        REUSE_STRUCTURE, FULL_RERUN и т.п.
    """

    id: UUID
    deal_id: UUID
    status: str
    profile: str

    # Новый атрибут: режим, в котором выполнялись проверки
    checks_mode: str

    pipeline_strategy: str
    total_checks: int
    completed_checks: int
    started_at: datetime | None
    completed_at: datetime | None
    error_details: dict | None
    error_user_message: str | None = None
    classification_stats: ClassificationStats | None = None

    model_config = {"from_attributes": True}


class RunProgressResponse(BaseModel):
    """
    Упрощённая схема прогресса (можно использовать в SSE/поллинге).

    На её основе фронт может просто и дёшево обновлять прогрессбар:

    - status — текущий статус Run;
    - completed_checks / total_checks — счётчики по документам;
    - percent — заранее посчитанный процент выполнения (0–100).
    """

    status: str
    completed_checks: int
    total_checks: int
    percent: float


class ClassificationReportResponse(BaseModel):
    """
    Полный отчёт о качестве классификации для Run.

    Используется в:
      GET /runs/{run_id}/classification-report.

    Позволяет:
    - найти документы с низкой уверенностью;
    - найти документы с неизвестным типом;
    - посмотреть покрытие триггеров (trigger_coverage).
    """

    run_id: UUID
    deal_id: UUID
    total_documents: int
    stats: ClassificationStats
    low_confidence_docs: list[
        dict
    ]  # [{doc_id, filename, doc_type, confidence, classification_level}]
    unknown_type_docs: list[dict]  # [{doc_id, filename, detected_type}]
    trigger_coverage: dict[str, int]  # {trigger_name: doc_count}


class DealRunSummaryResponse(BaseModel):
    """
    Агрегированный статус последнего Run по сделке.

    Используется в:
      GET /runs/deal/{deal_id}?include_classification_stats=true.

    Это «сводка по последнему запуску» для карточки сделки:

    - status:
        "pending" / "running" / "completed" / "completed_with_errors" / "failed";
    - total_checks / completed_checks:
        статус прогресса последнего Run;
    - error_details:
        агрегированная ошибка уровня Run (если Run в статусе failed
        или completed_with_errors и есть общее описание проблемы);
    - classification_stats:
        summary по классификации (если считалось для этого Run);
    - pipeline_strategy:
        режим запуска (быстрый/полный пересчёт и т.п.).
    """

    deal_id: UUID
    run_id: UUID
    status: str
    profile: str

    # Новый атрибут: режим проверок последнего Run по сделке
    checks_mode: str

    pipeline_strategy: str
    total_checks: int
    completed_checks: int
    started_at: datetime | None
    completed_at: datetime | None
    error_details: dict | None
    error_user_message: str | None = None
    classification_stats: ClassificationStats | None = None


class RunProgressEvent(BaseModel):
    """
    Событие прогресса Run для SSE-подписки.

    Формат выровнен с фронтовым типом ProgressEvent:
    - run_id: UUID run'а;
    - status: текущий статус ("pending", "running", "completed"...);
    - completed_checks / total_checks: счётчики проверок;
    - current_document: опциональное имя текущего документа;
    - error: краткое текстовое описание ошибки, если есть.
    """

    run_id: UUID
    status: str
    completed_checks: int
    total_checks: int
    current_document: str | None = None
    error: str | None = None
