"""
Модели данных агрегатора и экспортёра LegalMAS.

Содержит датаклассы для:

── Базовые модели (используются агрегатором и Excel-экспортом) ──────────────
  SeverityCounts      — счётчики результатов по уровню риска
  TopRisk             — одна критическая/высокая находка для сводки
  DDRequest           — запрос доп. информации, генерируется по fail-результатам
  ExportRow           — одна строка плоского DD Grid Excel (документ × чек)
  ConditionalCheckRow — строка для листа «Условные проверки» в Excel
  StructuredValueRow  — извлечённое структурированное значение (сумма, дата и т.п.)
  DocTypeSummary      — сводка по типу документа с метриками классификации
  AggregatedResults   — полная агрегация результатов одного рана сделки

── Модели DD Matrix (используются эндпоинтом /dd-matrix и матричным Excel) ──
  CheckMeta           — метаданные одного чека = описание столбца матрицы
  MatrixCell          — содержимое одной ячейки матрицы (документ × чек)
  DocumentMatrixRow   — одна строка матрицы = один документ со всеми результатами
  DDMatrixResponse    — полный ответ эндпоинта GET /dd-matrix

Архитектурный принцип:
  Бэкенд строит ОДНУ полную таблицу (AggregatedResults.rows) содержащую
  все результаты всех чеков по всем документам. DDMatrixResponse перепаковывает
  эти данные в матричную структуру {document → {check_id → результат}}.
  Фронтенд получает готовую структуру и только рендерит её — никаких
  вычислений на клиенте не требуется.

Источник origin у чеков:
  "GLOBAL_PLAYBOOK"  — глобальный плейбук, применим ко ВСЕМ документам сделки
  "DOCUMENT_TYPE"    — YAML-инструкция конкретного типа документа
  "CONDITIONAL"      — условный чек, активирован триггером из applicable_triggers
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SeverityCounts:
    """
    Счётчики результатов проверок по уровню критичности.

    Используется в:
    - AggregatedResults.severity_counts (итого по сделке)
    - DDMatrixResponse.severity_counts (итого по матрице)
    - DocTypeSummary (итого по типу документа)
    """

    critical: int = 0
    high: int = 0
    medium: int = 0
    pass_count: int = 0
    unclear: int = 0

    @property
    def total(self) -> int:
        return self.critical + self.high + self.medium + self.pass_count + self.unclear

    @property
    def fail_total(self) -> int:
        return self.critical + self.high + self.medium

    def to_dict(self) -> dict:
        return {
            "critical": self.critical,
            "high": self.high,
            "medium": self.medium,
            "pass": self.pass_count,
            "unclear": self.unclear,
            "total": self.total,
            "fail_total": self.fail_total,
        }


@dataclass
class TopRisk:
    """
    Одна критическая или высокая находка для раздела Executive Summary.

    Заполняется агрегатором из fail-результатов отсортированных по severity.
    Используется в Word-отчёте (report_builder.py) и Summary Excel.

    Segment/chunk provenance (NEW):
    Для multi-document файлов и chunked retrieval позволяет точно указать,
    в каком логическом сегменте и чанке найдена проблема.
    """

    check_id: str
    check_name: str
    severity: str
    document_name: str
    document_id: str
    doc_type: str
    evidence_snippet: str
    page: int | None = None
    clause_uid: str = ""
    confidence: float = 0.0
    structured_data: dict[str, Any] = field(default_factory=dict)
    conditional_check_triggered: bool = False
    trigger_name: str = ""
    segment_id: str = ""
    segment_type: str = ""
    segment_title: str = ""
    segment_order: int | None = None
    is_primary_segment: bool | None = None
    chunk_id: str = ""
    chunk_index: int | None = None

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "severity": self.severity,
            "document_name": self.document_name,
            "document_id": self.document_id,
            "doc_type": self.doc_type,
            "evidence_snippet": self.evidence_snippet[:300],
            "page": self.page,
            "clause_uid": self.clause_uid,
            "confidence": round(self.confidence, 3),
            "structured_data": self.structured_data,
            "conditional_check_triggered": self.conditional_check_triggered,
            "trigger_name": self.trigger_name,
            "segment_id": self.segment_id,
            "segment_type": self.segment_type,
            "segment_title": self.segment_title,
            "segment_order": self.segment_order,
            "is_primary_segment": self.is_primary_segment,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
        }


@dataclass
class DDRequest:
    """
    Запрос дополнительных документов/сведений по результатам DD.

    Создаётся агрегатором для каждого уникального fail-чека уровня critical/high.
    Текст запроса загружается из секции dd_request_templates YAML-инструкции.
    Дедуплицируется по check_id — один запрос на чек, даже если fail в нескольких
    документах.

    addressee — адресат запроса из YAML (например: «Продавец», «Юридический советник»).
    structured_values — извлечённые значения (суммы, даты) для подстановки в текст.

    Segment/chunk provenance (NEW):
    Для multi-document файлов и chunked retrieval позволяет точно указать, в каком
    логическом сегменте и чанке найдена проблема.

    При дедупликации (EXPORT_DD_REQUEST_DEDUP=True) берётся provenance ПЕРВОГО
    fail-результата для данного check_id (sorted by severity asc, confidence desc).
    Это означает, что если один и тот же чек сработал в нескольких сегментах/чанках,
    в запросе будет указан только первый наиболее приоритетный.

    Для получения полной картины юрист должен смотреть DD Matrix или Document Detail.
    """

    request_id: str
    check_id: str
    check_name: str
    priority: str
    text: str
    addressee: str = "Юридический советник"
    document_ids: list[str] = field(default_factory=list)
    document_names: list[str] = field(default_factory=list)
    doc_types: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    structured_values: list[dict] = field(default_factory=list)
    dedup_key: str = ""
    segment_id: str = ""
    segment_type: str = ""
    segment_title: str = ""
    segment_order: int | None = None
    is_primary_segment: bool | None = None
    chunk_id: str = ""
    chunk_index: int | None = None

    @property
    def document_count(self) -> int:
        return len(self.document_ids)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "check_id": self.check_id,
            "check_name": self.check_name,
            "priority": self.priority,
            "text": self.text,
            "addressee": self.addressee,
            "document_ids": self.document_ids,
            "document_names": self.document_names,
            "doc_types": self.doc_types,
            "document_count": self.document_count,
            "structured_values": self.structured_values,
            "segment_id": self.segment_id,
            "segment_type": self.segment_type,
            "segment_title": self.segment_title,
            "segment_order": self.segment_order,
            "is_primary_segment": self.is_primary_segment,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
        }


@dataclass
class ExportRow:
    """
    Одна строка плоского DD Grid Excel.

    Плоский формат: каждая строка = одна проверка одного документа.
    Используется в листе «DD Grid» (плоский список для фильтрации/сортировки).
    Для матричного представления используется DDMatrixResponse.

    origin:
        "GLOBAL_PLAYBOOK"  — чек из глобального плейбука
        "DOCUMENT_TYPE"    — чек из YAML-инструкции типа документа
        "CONDITIONAL"      — условный чек по триггеру

    Segment/chunk provenance (NEW):
    - single-document: segment_id/chunk_id обычно пустые
    - multi-document: позволяют понять, к какому логическому сегменту/чанку относится строка
    """

    document_name: str
    folder_path: str
    doc_type: str
    check_name: str
    check_id: str
    result: str
    severity: str
    evidence_snippet: str
    page: int | None = None
    clause_uid: str = ""
    confidence: float = 0.0
    detector_used: str = ""
    quality_flags: str = ""
    qc_status: str = "pending"
    qc_by: str | None = None
    qc_comment: str | None = None
    qc_at: str | None = None  # ISO string
    document_id: str = ""
    run_id: str = ""
    structured_data_preview: str = ""
    conditional_check_triggered: bool = False
    trigger_name: str = ""
    classification_level: str = ""
    classification_confidence: float = 0.0
    origin: str | None = None
    segment_id: str = ""
    segment_type: str = ""
    segment_title: str = ""
    segment_order: int | None = None
    is_primary_segment: bool | None = None
    chunk_id: str = ""
    chunk_index: int | None = None


@dataclass
class ConditionalCheckRow:
    """
    Строка для листа «Условные проверки» в Excel.

    Содержит только те чеки которые были активированы триггерами
    (conditional_check_triggered=True). Выносится на отдельный лист
    чтобы не засорять основной DD Grid.
    """

    document_name: str
    doc_type: str
    trigger_name: str
    check_id: str
    check_name: str
    result: str
    severity: str
    evidence_snippet: str
    page: int | None = None
    confidence: float = 0.0
    quality_flags: str = ""


@dataclass
class StructuredValueRow:
    """
    Одно структурированное значение извлечённое из документа.

    Используется в листе «Extracted Values» в Excel и в MatrixCell.extracted.
    Примеры: сумма договора, дата подписания, наименование стороны,
    кадастровый номер, ставка НДС и т.п.

    field_format определяет способ отображения на фронте:
        "money"       — денежная сумма (форматировать с разделителями)
        "date"        — дата (форматировать по локали)
        "entity_name" — наименование юридического лица
        "text"        — произвольный текст

    Segment/chunk provenance (NEW):
    Позволяет на фронтенде показать, в каком сегменте/чанке найдено значение.
    """

    document_name: str
    doc_type: str
    check_name: str
    field_name: str
    field_value: str
    field_format: str
    page: int | None = None
    clause_uid: str = ""
    document_id: str = ""
    check_id: str = ""
    segment_id: str = ""
    segment_type: str = ""
    segment_title: str = ""
    segment_order: int | None = None
    is_primary_segment: bool | None = None
    chunk_id: str = ""
    chunk_index: int | None = None


@dataclass
class DocTypeSummary:
    """
    Сводная строка по одному типу документа для листа «Summary» в Excel.

    Включает счётчики результатов проверок и метрики качества классификации.
    low_confidence_count — документы с confidence < 0.6, требуют ручной проверки.
    """

    doc_type: str
    document_count: int = 0
    check_count: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    pass_count: int = 0
    unclear: int = 0
    avg_classification_confidence: float = 0.0
    low_confidence_count: int = 0
    conditional_checks_triggered: int = 0


@dataclass
class AggregatedResults:
    """
    Полная агрегация результатов одного рана (Run) по сделке.

    Строится функцией aggregate_results() в services/export/aggregator.py.
    Является единственным источником данных для всех форматов экспорта:
    - Excel DD Grid (grid_builder.py)
    - Excel Summary (summary_builder.py)
    - Word Report (report_builder.py)
    - API эндпоинты deal review (deal_review_service.py)
    - API эндпоинт DD Matrix (deal_review_service.py → build_dd_matrix)

    rows — плоский список всех результатов, каждая запись = один CheckResult
    (документ, чек, сегмент, chunk). Для одного (document_id, check_id) может
    быть несколько записей, если чек срабатывал в разных сегментах или чанках
    одного физического файла. На основе этого списка строятся как плоский DD Grid,
    так и матричные представления (включая сегмент-ориентированную DD Matrix).
    """

    deal_id: str
    deal_name: str
    run_id: str
    severity_counts: SeverityCounts = field(default_factory=SeverityCounts)
    top_risks: list[TopRisk] = field(default_factory=list)
    dd_requests: list[DDRequest] = field(default_factory=list)
    rows: list[ExportRow] = field(default_factory=list)
    conditional_rows: list[ConditionalCheckRow] = field(default_factory=list)
    structured_value_rows: list[StructuredValueRow] = field(default_factory=list)
    doc_type_summaries: list[DocTypeSummary] = field(default_factory=list)
    total_documents: int = 0
    total_checks: int = 0
    quarantine_count: int = 0
    degraded_count: int = 0
    evidence_validity_rate: float = 1.0
    conditional_checks_total: int = 0
    conditional_checks_triggered: int = 0

    def to_dict(self) -> dict:
        return {
            "deal_id": self.deal_id,
            "deal_name": self.deal_name,
            "run_id": self.run_id,
            "severity_counts": self.severity_counts.to_dict(),
            "top_risks": [r.to_dict() for r in self.top_risks],
            "dd_requests": [r.to_dict() for r in self.dd_requests],
            "total_documents": self.total_documents,
            "total_checks": self.total_checks,
            "quarantine_count": self.quarantine_count,
            "degraded_count": self.degraded_count,
            "evidence_validity_rate": round(self.evidence_validity_rate, 3),
            "conditional_checks_total": self.conditional_checks_total,
            "conditional_checks_triggered": self.conditional_checks_triggered,
        }


# ---------------------------------------------------------------------------
# DD Matrix models
# Используются эндпоинтом GET /deals/{deal_id}/runs/{run_id}/dd-matrix
# и матричными листами в grid_builder.py
# ---------------------------------------------------------------------------


@dataclass
class ExtractedField:
    """
    Одно извлечённое поле внутри ячейки матрицы.

    Отдельный класс (а не dict[str, str]) нужен чтобы фронтенд знал
    как форматировать значение — сумму иначе чем дату иначе чем имя.

    Примеры:
        field_name="сумма",         field_value="5 000 000", field_format="money"
        field_name="дата",          field_value="01.01.2025", field_format="date"
        field_name="кадастровый №", field_value="77:01:0001001:123", field_format="text"
    """

    field_name: str
    field_value: str
    field_format: str


@dataclass
class MatrixCell:
    """
    Содержимое одной ячейки DD Matrix — пересечение строки (документ) и столбца (чек).

    Отсутствие ячейки в словаре DocumentMatrixRow.results означает что чек
    НЕ ПРИМЕНЯЛСЯ к документу (n/a) — это не то же самое что result="unclear".

    Поля:
        result     — итог проверки: "fail" | "pass" | "unclear"
        severity   — уровень риска: "critical" | "high" | "medium"
                     (для pass/unclear берётся из определения чека, не из результата)
        snippet    — цитата из текста документа (pinpoint evidence, до 300 символов)
        page       — номер страницы где найдено доказательство
        clause_uid — UID параграфа/пункта договора (например "§4.1", "п.3.2.1")
        extracted  — список структурированных значений извлечённых этим чеком
        confidence — уверенность модели (0.0–1.0)
        qc_status  — статус ручной проверки: "pending" | "approved" | "rejected"
        conditional_check_triggered — True если чек сработал по триггеру
        trigger_name — имя триггера который активировал чек
        
    Segment/chunk provenance (NEW):
        segment_id, chunk_id — позволяют точно указать, откуда взят результат
    """

    result: str
    severity: str
    snippet: str = ""
    page: int | None = None
    clause_uid: str = ""
    extracted: list[ExtractedField] = field(default_factory=list)
    confidence: float = 0.0
    qc_status: str = "pending"
    conditional_check_triggered: bool = False
    trigger_name: str = ""
    segment_id: str = ""
    segment_type: str = ""
    segment_title: str = ""
    segment_order: int | None = None
    is_primary_segment: bool | None = None
    chunk_id: str = ""
    chunk_index: int | None = None


@dataclass
class CheckMeta:
    """
    Метаданные одного чека — описание столбца DD Matrix.

    Используется фронтендом для:
    - построения заголовков столбцов матрицы
    - фильтрации столбцов по вкладкам (глобальные / по типу документа)
    - отображения severity-цвета в заголовке столбца

    origin:
        "GLOBAL_PLAYBOOK"  — глобальный плейбук, столбец присутствует
                             на вкладке «Глобальные» и во всех вкладках по типам
        "DOCUMENT_TYPE"    — YAML-инструкция, столбец только на вкладке
                             своего типа документа
        "CONDITIONAL"      — условный чек, показывается только если сработал
                             хотя бы для одного документа

    applicable_doc_types:
        None   — применим ко всем типам (только GLOBAL_PLAYBOOK)
        [...]  — список типов документов (только DOCUMENT_TYPE / CONDITIONAL)

    order_index:
        Порядок отображения столбца. Глобальные чеки идут первыми (меньший индекс),
        затем doc-type чеки в порядке их объявления в YAML.
        Без этого поля порядок столбцов будет недетерминированным между запусками.
    """

    check_id: str
    check_name: str
    origin: str
    severity: str
    order_index: int = 0
    applicable_doc_types: list[str] | None = None


@dataclass
class DocumentMatrixRow:
    """
    Одна строка DD Matrix — один документ со всеми результатами проверок.

    results — словарь check_id → MatrixCell.
    Отсутствие ключа означает что чек не применялся к документу (n/a).
    Фронтенд отображает пустую/серую ячейку без статуса.

    status — текущий статус обработки документа из Document.status:
        "completed"  — обработан полностью
        "quarantine" — изолирован (повреждённый файл, превышение порога OCR и т.п.)
        "failed"     — ошибка обработки

    Строки в DDMatrixResponse.documents отсортированы по убыванию critical_count,
    затем fail_count — наиболее рискованные документы идут первыми.
    """

    document_id: str
    document_name: str
    doc_type: str
    folder_path: str
    status: str = "completed"
    classification_level: str = ""
    classification_confidence: float = 0.0
    results: dict[str, MatrixCell] = field(default_factory=dict)

    @property
    def fail_count(self) -> int:
        """Количество чеков с результатом fail — для сортировки строк по риску."""
        return sum(1 for c in self.results.values() if c.result == "fail")

    @property
    def critical_count(self) -> int:
        """Количество критических провалов — для сортировки и цветовой индикации строки."""
        return sum(
            1 for c in self.results.values()
            if c.result == "fail" and c.severity == "critical"
        )


@dataclass
class SegmentMatrixRow:
    """
    Одна строка DD Matrix на уровне логического документа (сегмента).

    document_id  — физический файл, внутри которого находится сегмент.
    segment_*    — идентификация логического документа (договор, приложение, акт).
    results      — чек-результаты для этого логического документа.

    В отличие от DocumentMatrixRow, который агрегирует результаты на уровне
    физического файла, SegmentMatrixRow соответствует тому уровню, на котором
    юрист фактически воспринимает документ (contract / appendix / act и т.п.).
    """

    document_id: str
    document_name: str
    doc_type: str
    folder_path: str

    segment_id: str
    segment_type: str | None = None
    segment_title: str | None = None
    segment_order: int | None = None
    is_primary_segment: bool | None = None

    status: str = "completed"
    classification_level: str = ""
    classification_confidence: float = 0.0

    results: dict[str, MatrixCell] = field(default_factory=dict)

    @property
    def fail_count(self) -> int:
        """Количество чеков с результатом fail — для сортировки строк по риску."""
        return sum(1 for c in self.results.values() if c.result == "fail")

    @property
    def critical_count(self) -> int:
        """Количество критических провалов — для сортировки и цветовой индикации строки."""
        return sum(
            1 for c in self.results.values()
            if c.result == "fail" and c.severity == "critical"
        )
    

@dataclass
class DDMatrixResponse:
    """
    Полный ответ эндпоинта GET /deals/{deal_id}/runs/{run_id}/dd-matrix.

    Структура разделена на три части для удобства фронтенда:

    1. checks — полный реестр всех чеков этого рана (описания столбцов).
       Фронтенд строит заголовки матрицы из этого списка.

    2. global_check_ids — check_id с origin=GLOBAL_PLAYBOOK.
       Фронтенд использует для вкладки «Глобальные проверки»
       (показывает только эти столбцы, строки = все документы).

    3. doc_type_check_ids — {doc_type: [check_id, ...]} с origin=DOCUMENT_TYPE.
       Фронтенд использует для вкладок по типам документов
       (показывает только эти столбцы, строки = только документы этого типа).
       Глобальные чеки на вкладках типов НЕ повторяются — только специфичные.

    4. documents — строки матрицы, отсортированы по убыванию рисков
       (сначала документы с наибольшим количеством critical fail).

    Метрики качества:
        quarantine_count  — документы в карантине (не проверялись)
        degraded_count    — документы с деградированным OCR (низкое качество)
        evidence_validity_rate — доля критических/высоких находок с цитатой (0–1)

    Фронтенд получает этот объект один раз и рендерит любое представление
    без повторных запросов к серверу.
    """

    deal_id: str
    run_id: str
    deal_name: str
    checks: list[CheckMeta] = field(default_factory=list)
    global_check_ids: list[str] = field(default_factory=list)
    doc_type_check_ids: dict[str, list[str]] = field(default_factory=dict)
    documents: list[DocumentMatrixRow] = field(default_factory=list)
    # NEW: строки матрицы на уровне логического документа (сегмента).
    # Именно этот список должен стать основным источником данных для DD Grid на фронте.
    segment_documents: list[SegmentMatrixRow] = field(default_factory=list)

    total_documents: int = 0
    total_checks: int = 0
    severity_counts: SeverityCounts = field(default_factory=SeverityCounts)
    quarantine_count: int = 0
    degraded_count: int = 0
    evidence_validity_rate: float = 1.0

