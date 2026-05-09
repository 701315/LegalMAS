# src/api/schemas/qc.py

"""
Pydantic‑схемы для QC‑действий в review mode.

Зачем нужен этот модуль:
- описывает format запросов и ответов для approve / reject finding'ов в review UI;
- отделяет новый review‑ориентированный контракт от legacy QC API,
  который может работать через result_id;
- делает mutation‑контракт явным и segment-aware;
- поддерживает как одиночные, так и массовые QC‑действия из DD Grid.

Что считается finding'ом в review mode:
- на фронте DD Matrix и review panel работают не с raw row id,
  а с логической ячейкой review‑матрицы;
- backend строит такую ячейку как группу результатов с ключом:
    (run_id, document_id, check_id, segment_id)
- поэтому approve / reject должны применяться ко всей этой группе,
  а не к одной строке CheckResult.
"""

from pydantic import BaseModel, Field, field_validator, model_validator


_ALLOWED_QC_STATUSES = {"approved", "rejected", "needs_review"}


class ReviewFindingKey(BaseModel):
    """
    Ключ одной логической review‑ячейки.

    Именно этот набор полей должен однозначно указывать на finding,
    который пользователь видит в DD Matrix или review panel.
    """

    run_id: str
    document_id: str
    check_id: str = Field(min_length=1, max_length=100)
    segment_id: str | None = Field(default=None, max_length=200)

    @field_validator("run_id", "document_id", "check_id", mode="before")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @field_validator("segment_id", mode="before")
    @classmethod
    def normalize_segment_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ReviewQCUpdateRequest(BaseModel):
    """
    Запрос на QC‑действие над одним finding'ом в review mode.
    """

    finding: ReviewFindingKey
    qc_status: str = Field(description="approved / rejected / needs_review")
    comment: str | None = Field(default=None, max_length=4000)

    @field_validator("qc_status")
    @classmethod
    def validate_qc_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _ALLOWED_QC_STATUSES:
            raise ValueError(
                "qc_status must be one of: approved, rejected, needs_review"
            )
        return normalized

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ReviewQCUpdateResponse(BaseModel):
    """
    Ответ на одиночное QC‑действие в review mode.
    """

    run_id: str
    deal_id: str
    document_id: str
    check_id: str
    segment_id: str | None = None
    qc_status: str
    qc_by: str
    qc_at: str | None = None
    qc_comment: str | None = None
    updated_rows_count: int


class ReviewQCBulkUpdateRequest(BaseModel):
    """
    Массовое QC‑действие над несколькими finding'ами review‑матрицы.

    Все finding'и в bulk‑операции должны относиться к одному и тому же run_id.
    Это упрощает permission check, audit trail и транзакционную семантику.
    """

    findings: list[ReviewFindingKey] = Field(min_length=1, max_length=1000)
    qc_status: str = Field(description="approved / rejected / needs_review")
    comment: str | None = Field(default=None, max_length=4000)

    @field_validator("qc_status")
    @classmethod
    def validate_qc_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _ALLOWED_QC_STATUSES:
            raise ValueError(
                "qc_status must be one of: approved, rejected, needs_review"
            )
        return normalized

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_single_run_scope(self) -> "ReviewQCBulkUpdateRequest":
        run_ids = {item.run_id for item in self.findings}
        if len(run_ids) != 1:
            raise ValueError(
                "all findings in bulk request must belong to the same run_id"
            )
        return self


class ReviewQCBulkItemResponse(BaseModel):
    """
    Результат обновления одного finding'а внутри bulk‑операции.
    """

    run_id: str
    deal_id: str
    document_id: str
    check_id: str
    segment_id: str | None = None
    qc_status: str
    qc_by: str
    qc_at: str | None = None
    qc_comment: str | None = None
    updated_rows_count: int


class ReviewQCBulkUpdateResponse(BaseModel):
    """
    Ответ на массовое QC‑действие.
    """

    run_id: str
    deal_id: str
    qc_status: str
    qc_by: str
    qc_at: str | None = None
    qc_comment: str | None = None
    total_findings: int
    updated_findings: int
    changed_findings: int
    updated_rows_count: int
    items: list[ReviewQCBulkItemResponse]


    