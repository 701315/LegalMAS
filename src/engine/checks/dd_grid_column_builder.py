# src/engine/checks/dd_grid_column_builder.py

"""
DD Grid Column Builder (V1.7).

Универсальный автомаппинг ExtractionConfig.fields → runtime DD Grid columns.

Ответственность:
- по CheckDefinition вернуть список колонок для отображения в DD Grid V1;
- разделить fields на 3 группы: columns / metadata / display_summary;
- применить универсальные правила автомаппинга;
- уважать explicit ExtractionConfig.dd_grid_columns если он задан.

Универсальные правила (не хардкодятся под конкретные check_id):

1. Если extraction.dd_grid_columns задан → используем его как есть,
   auto-mapping не запускается.

2. Auto-mapping классифицирует каждое field:

   a) skip / metadata:
      - role == "subgroup_metadata"
      - name in {reason, evidence, explanation, notes}
      - type == EVIDENCE_LIST
      - presentation == "diagnostic"

   b) display summary (свёрнутое представление):
      - name.endswith("_display") И display_in_grid != True
      - presentation == "summary"

   Если поле с name.endswith("_display") помечено display_in_grid=True,
   оно становится полноценной колонкой, а не display summary.

   c) columns:
      - В playbook-driven mode (хотя бы одно поле с display_in_grid=True):
        только поля с display_in_grid=True и presentation in {fact, summary}.
      - В legacy auto-mapping mode:
        всё остальное по правилам A-F.

      A. paired <prefix>_status + <prefix>_details  → text column
      B. paired <prefix>_status + <prefix>_value    → text column
      C. standalone <prefix>_status                 → presence_only column
      D. allowed_values ⊇ {yes, no}                 → yes_no column
      E. allowed_values (другой enum)               → enum column
      F. одиночное text/number/date поле            → text column

Runtime DTO (DDGridColumnRuntime) — immutable dataclass.
НЕ является API DTO. Frontend contract будет сделан отдельно в V1.8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from engine.playbook.models import (
    AllowedValueSpec,
    CheckDefinition,
    DDGridColumnSpec,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)

logger = get_logger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────────

# Metadata field names, которые универсально не попадают в колонки DD Grid.
# Совпадает с _RESERVED_METADATA_FIELDS из result_semantics.py — это осознанное
# дублирование, чтобы не создавать циклический импорт между модулями.
_RESERVED_METADATA_FIELD_NAMES: frozenset[str] = frozenset({
    "reason",
    "evidence",
    "explanation",
    "notes",
})

# Универсальные ru-локализованные labels для типовых enum values.
# Применяются только когда AllowedValueSpec.label не задан в YAML.
_GENERIC_ENUM_LABELS: dict[str, str] = {
    # yes/no
    "yes": "Да",
    "no": "Нет",
    # presence-family
    "present": "Указано",
    "missing": "Не указано",
    "unclear": "Не удалось определить",
    "not_specified": "Не указано",
    "not_addressed": "Не урегулировано",
    "defined": "Определено",
    "not_defined": "Не определено",
    "not_found": "Не найдено",
    "absent": "Отсутствует",
}

# Yes/No detection markers — используются в правиле D для определения yes_no колонки.
_YES_NO_MARKERS: frozenset[str] = frozenset({"yes", "no"})

# Fallback display для ячейки без значения.
_DEFAULT_FALLBACK_DISPLAY = "—"

# Шаг display_order при автомаппинге. Умножаем index на этот шаг,
# чтобы оставить возможность вставлять колонки между существующими.
_DISPLAY_ORDER_STEP = 10


# ─── Runtime DTO ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DDGridColumnRuntime:
    """
    Runtime column specification для DD Grid V1.

    Строится либо из explicit ExtractionConfig.dd_grid_columns (YAML),
    либо автомаппингом из ExtractionConfig.fields.

    Универсальный контракт для V1.7 (DD Grid Builder):
    не зависит от структуры конкретного check'а.

    Fields:
        column_id:
            Уникальный id в формате '{check_id}__{field_or_column_key}'.
        label:
            Человекочитаемый заголовок колонки для UI.
        value_field:
            Имя extraction field, откуда брать значение ячейки.
            None для presence_only колонки (используется только status_field).
        status_field:
            Имя extraction field со статусом (paired pattern).
            None для одиночных text/enum/yes_no колонок.
        status_present_value:
            Значение status_field, означающее "данные присутствуют".
            Например: 'present', 'defined', 'yes'.
            None если status_field не используется.
        format:
            Формат отображения: 'text' | 'enum' | 'yes_no' | 'presence_only'.
        fallback_display:
            Текст ячейки при отсутствии значения. По умолчанию '—'.
        display_order:
            Порядок колонки слева направо. Меньше = раньше.
        enum_labels:
            canonical value → человекочитаемый label. Пусто для non-enum колонок.
        unit:
            Единица измерения из ExtractionFieldConfig.unit (например 'дней', 'RUB').
            None если не задано.
    """

    column_id: str
    label: str
    value_field: str | None
    status_field: str | None
    status_present_value: str | None
    format: str
    fallback_display: str
    display_order: int
    enum_labels: dict[str, str] = field(default_factory=dict)
    unit: str | None = None


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _humanize(name: str) -> str:
    """
    snake_case → 'Snake case'.

    Универсальный fallback для UI labels, когда явный label не задан.
    """
    if not name:
        return ""
    return name.replace("_", " ").strip().capitalize()


def _normalize_allowed_values(
    allowed_values: list[Any] | None,
) -> tuple[list[str], dict[str, str]]:
    """
    Нормализовать allowed_values к канонической форме.

    Поддерживает оба формата ExtractionFieldConfig.allowed_values:
    - list[str]                — legacy
    - list[AllowedValueSpec]   — с explicit labels

    Returns:
        (canonical_values, explicit_labels)
        canonical_values — список canonical string values
        explicit_labels  — value → label (только для AllowedValueSpec с непустым label)
    """
    if not allowed_values:
        return [], {}

    canonical_values: list[str] = []
    explicit_labels: dict[str, str] = {}

    for item in allowed_values:
        if isinstance(item, AllowedValueSpec):
            value = item.value
            canonical_values.append(value)
            if item.label and item.label.strip():
                explicit_labels[value] = item.label.strip()
        elif isinstance(item, str):
            canonical_values.append(item)
        else:
            # Defensive: игнорируем некорректные записи
            logger.debug(
                "DDGridColumnBuilder: unexpected allowed_values item type, skipping",
                item_type=type(item).__name__,
            )

    return canonical_values, explicit_labels


def _build_enum_labels(
    canonical_values: list[str],
    explicit_labels: dict[str, str],
) -> dict[str, str]:
    """
    Построить canonical value → human label mapping.

    Приоритет:
    1. AllowedValueSpec.label (explicit из YAML)
    2. _GENERIC_ENUM_LABELS (универсальные ru fallback)
    3. _humanize(value) (fallback)
    """
    labels: dict[str, str] = {}
    for value in canonical_values:
        if value in explicit_labels:
            labels[value] = explicit_labels[value]
        elif value in _GENERIC_ENUM_LABELS:
            labels[value] = _GENERIC_ENUM_LABELS[value]
        else:
            labels[value] = _humanize(value)
    return labels


def _resolve_status_present_value(canonical_values: list[str]) -> str | None:
    """
    Определить значение status_field, означающее 'данные присутствуют'.

    Приоритет:
    1. 'present' если есть в allowed_values
    2. 'defined' если есть
    3. 'yes' если есть
    4. первое значение из списка
    5. None если список пуст
    """
    if not canonical_values:
        return None

    for preferred in ("present", "defined", "yes"):
        if preferred in canonical_values:
            return preferred

    return canonical_values[0]


def _is_metadata_field(cfg: ExtractionFieldConfig) -> bool:
    """
    Определить, является ли поле metadata (не колонка, но идёт в drawer).

    Rules (universal):
    - role == "subgroup_metadata"
    - name in reserved metadata names (reason/evidence/explanation/notes)
    - type == EVIDENCE_LIST
    - presentation == "diagnostic"
    """
    if getattr(cfg, "role", None) == "subgroup_metadata":
        return True
    if cfg.name in _RESERVED_METADATA_FIELD_NAMES:
        return True
    if cfg.type == ExtractionFieldType.EVIDENCE_LIST:
        return True
    if getattr(cfg, "presentation", None) == "diagnostic":
        return True
    return False


def _is_display_summary_field(cfg: ExtractionFieldConfig) -> bool:
    """
    Определить, является ли поле compact display summary
    (не колонка, но используется в свёрнутом представлении).

    Rules (universal):
    - name.endswith("_display")
    - presentation == "summary"
    """
    if cfg.name.endswith("_display"):
        return True
    if getattr(cfg, "presentation", None) == "summary":
        return True
    return False


def _has_explicit_display_grid_fields(
    fields: list[ExtractionFieldConfig],
) -> bool:
    """
    Return True if playbook explicitly opts into display_in_grid mode.

    We switch to playbook-driven DD Grid contract only when
    at least one field is explicitly marked display_in_grid=True.
    This preserves backward compatibility for legacy checks.
    """
    return any(
        bool(getattr(cfg, "display_in_grid", False))
        for cfg in fields
    )


def _is_human_display_field(cfg: ExtractionFieldConfig) -> bool:
    """
    Return True if field is safe for user-facing DD Grid display.

    signal/diagnostic fields must never become grid columns,
    even if misconfigured with display_in_grid=True.
    """
    presentation = str(getattr(cfg, "presentation", None) or "").strip().lower()
    if presentation in {"signal", "diagnostic"}:
        return False
    if cfg.type == ExtractionFieldType.EVIDENCE_LIST:
        return False
    return True


def _get_label(cfg: ExtractionFieldConfig, fallback_name: str | None = None) -> str:
    """
    Получить human-readable label для колонки.

    Приоритет:
    1. cfg.label (explicit из YAML)
    2. humanize(cfg.name)
    3. humanize(fallback_name) если задан

    fallback_name используется для paired-колонок, где имя может быть
    prefix без _status/_details/_value.
    """
    if cfg.label and cfg.label.strip():
        return cfg.label.strip()

    if cfg.name:
        return _humanize(cfg.name)

    if fallback_name:
        return _humanize(fallback_name)

    return ""


# ─── Column builder ───────────────────────────────────────────────────────────


class DDGridColumnBuilder:
    """
    Универсальный builder DD Grid колонок из CheckDefinition.

    Использование:
        builder = DDGridColumnBuilder()
        columns, metadata_fields, display_summary_field = builder.build_columns(check)

    Contract:
    - columns              — list[DDGridColumnRuntime] в порядке display_order
    - metadata_fields      — list[str] имён fields для drawer
    - display_summary_field — str | None имя поля для compact summary
    """

    def build_columns(
        self,
        check: CheckDefinition,
    ) -> tuple[list[DDGridColumnRuntime], list[str], str | None]:
        """
        Построить колонки, metadata fields и display summary field для check.

        Returns:
            (columns, metadata_field_names, display_summary_field_name)
        """
        extraction: ExtractionConfig | None = getattr(check, "extraction", None)

        if extraction is None or not extraction.enabled:
            logger.debug(
                "DDGridColumnBuilder: check has no extraction, returning empty",
                check_id=check.id,
            )
            return [], [], None

        fields = extraction.fields or []

        # Приоритет 1: explicit dd_grid_columns из YAML
        if extraction.dd_grid_columns:
            columns = self._build_from_explicit_spec(
                check_id=check.id,
                specs=extraction.dd_grid_columns,
                fields=fields,
            )
            metadata_fields, display_summary_field = \
                self._classify_non_column_fields(fields)
            return columns, metadata_fields, display_summary_field

        # Приоритет 2: playbook-driven mode через display_in_grid
        if _has_explicit_display_grid_fields(fields):
            return self._build_from_display_flags(check.id, fields)

        # Приоритет 3: legacy auto-mapping
        return self._auto_map_columns(check.id, fields)

    # ─── Explicit spec path ───────────────────────────────────────────

    def _build_from_explicit_spec(
        self,
        check_id: str,
        specs: list[DDGridColumnSpec],
        fields: list[ExtractionFieldConfig],
    ) -> list[DDGridColumnRuntime]:
        """
        Построить колонки из явно заданного DDGridColumnSpec list.

        Для enum-format колонок собираем enum_labels из соответствующих fields.
        """
        # Индекс fields по имени для быстрого lookup
        fields_by_name = {f.name: f for f in fields}

        columns: list[DDGridColumnRuntime] = []
        for spec in specs:
            enum_labels: dict[str, str] = {}
            unit: str | None = None

            if spec.value_field and spec.value_field in fields_by_name:
                field_cfg = fields_by_name[spec.value_field]
                unit = field_cfg.unit

                if spec.format in ("enum", "yes_no") and field_cfg.allowed_values:
                    canonical_values, explicit_labels = _normalize_allowed_values(
                        field_cfg.allowed_values
                    )
                    enum_labels = _build_enum_labels(canonical_values, explicit_labels)

            columns.append(
                DDGridColumnRuntime(
                    column_id=f"{check_id}__{spec.column_id}",
                    label=spec.label,
                    value_field=spec.value_field,
                    status_field=spec.status_field,
                    status_present_value=spec.status_present_value,
                    format=spec.format or "text",
                    fallback_display=spec.fallback_display or _DEFAULT_FALLBACK_DISPLAY,
                    display_order=spec.display_order,
                    enum_labels=enum_labels,
                    unit=unit,
                )
            )

        # Сортируем по display_order для детерминизма
        columns.sort(key=lambda c: (c.display_order, c.column_id))
        return columns

    def _classify_non_column_fields(
        self,
        fields: list[ExtractionFieldConfig],
    ) -> tuple[list[str], str | None]:
        """
        Определить metadata fields и display summary field.
        Используется в explicit spec path (где columns строятся отдельно).
        """
        metadata_fields: list[str] = []
        display_summary_field: str | None = None

        for cfg in fields:
            if _is_metadata_field(cfg):
                metadata_fields.append(cfg.name)
            elif _is_display_summary_field(cfg):
                # Берём первое найденное display summary field
                if display_summary_field is None:
                    display_summary_field = cfg.name

        return metadata_fields, display_summary_field

    # ─── Auto-mapping path ────────────────────────────────────────────

    def _build_from_display_flags(
        self,
        check_id: str,
        fields: list[ExtractionFieldConfig],
    ) -> tuple[list[DDGridColumnRuntime], list[str], str | None]:
        """
        Build columns from explicit playbook display_in_grid flags.

        Rules:
        - only fields with display_in_grid=True become visible columns;
        - only human-displayable presentations are allowed:
          presentation in {fact, summary} — signal/diagnostic excluded;
        - display_priority controls ordering;
        - *_display fields may also become real columns here
          (no longer automatically excluded as display_summary).
        """
        metadata_fields: list[str] = []
        display_summary_field: str | None = None
        visible_fields: list[tuple[int, ExtractionFieldConfig]] = []

        for idx, cfg in enumerate(fields):
            # Metadata — всегда в drawer
            if _is_metadata_field(cfg):
                metadata_fields.append(cfg.name)
                continue

            # Display summary — только если поле НЕ помечено display_in_grid
            is_display = _is_display_summary_field(cfg)
            is_visible = bool(getattr(cfg, "display_in_grid", False))

            if is_display and not is_visible:
                if display_summary_field is None:
                    display_summary_field = cfg.name
                continue

            if not is_visible:
                continue

            # Защита от signal/diagnostic в колонках
            if not _is_human_display_field(cfg):
                logger.warning(
                    "DDGridColumnBuilder: signal/diagnostic field "
                    "marked display_in_grid=True, skipping",
                    check_id=check_id,
                    field_name=cfg.name,
                    presentation=getattr(cfg, "presentation", None),
                )
                continue

            visible_fields.append((idx, cfg))

        if not visible_fields:
            logger.debug(
                "DDGridColumnBuilder: no visible playbook-driven fields found",
                check_id=check_id,
            )
            return [], metadata_fields, display_summary_field

        def sort_key(
            item: tuple[int, ExtractionFieldConfig],
        ) -> tuple[int, int, str]:
            idx, cfg = item
            priority = getattr(cfg, "display_priority", None)
            priority_value = priority if isinstance(priority, int) else 10_000
            return (priority_value, idx, cfg.name)

        visible_fields.sort(key=sort_key)

        columns: list[DDGridColumnRuntime] = []
        for idx, cfg in visible_fields:
            column = self._build_singleton_column(check_id=check_id, cfg=cfg)

            priority = getattr(cfg, "display_priority", None)
            display_order = (
                priority * _DISPLAY_ORDER_STEP
                if isinstance(priority, int)
                else idx * _DISPLAY_ORDER_STEP
            )
            columns.append(self._with_display_order(column, display_order))

        columns.sort(key=lambda c: (c.display_order, c.column_id))
        return columns, metadata_fields, display_summary_field

    def _auto_map_columns(
        self,
        check_id: str,
        fields: list[ExtractionFieldConfig],
    ) -> tuple[list[DDGridColumnRuntime], list[str], str | None]:
        """
        Универсальный автомаппинг fields → columns.

        Порядок обработки:
        1. Классификация fields на metadata / display / column-candidates.
        2. Идентификация paired patterns среди column-candidates.
        3. Построение колонок в порядке первого встреченного field каждой пары.
        """
        # Step 1: классификация
        metadata_fields: list[str] = []
        display_summary_field: str | None = None
        column_candidates: list[ExtractionFieldConfig] = []
        candidate_positions: dict[str, int] = {}  # name → index in extraction.fields

        for idx, cfg in enumerate(fields):
            if _is_metadata_field(cfg):
                metadata_fields.append(cfg.name)
                continue
            if _is_display_summary_field(cfg):
                if display_summary_field is None:
                    display_summary_field = cfg.name
                continue
            column_candidates.append(cfg)
            candidate_positions[cfg.name] = idx

        if not column_candidates:
            return [], metadata_fields, display_summary_field

        # Step 2: идентификация пар
        candidates_by_name = {c.name: c for c in column_candidates}
        used_names: set[str] = set()

        # Индексы префиксов
        status_prefixes: dict[str, str] = {}   # prefix → status_field_name
        details_prefixes: dict[str, str] = {}  # prefix → details_field_name
        value_prefixes: dict[str, str] = {}    # prefix → value_field_name

        for name in candidates_by_name:
            if name.endswith("_status"):
                status_prefixes[name[: -len("_status")]] = name
            elif name.endswith("_details"):
                details_prefixes[name[: -len("_details")]] = name
            elif name.endswith("_value"):
                value_prefixes[name[: -len("_value")]] = name

        # Step 3: построение колонок
        columns: list[DDGridColumnRuntime] = []
        emitted_positions: set[int] = set()

        for prefix, status_name in status_prefixes.items():
            details_name = details_prefixes.get(prefix)
            value_name = value_prefixes.get(prefix)

            if details_name and details_name in candidates_by_name:
                # Правило A: paired status + details
                column = self._build_paired_column(
                    check_id=check_id,
                    prefix=prefix,
                    status_cfg=candidates_by_name[status_name],
                    value_cfg=candidates_by_name[details_name],
                )
                columns.append(column)
                used_names.add(status_name)
                used_names.add(details_name)
                first_pos = min(
                    candidate_positions[status_name],
                    candidate_positions[details_name],
                )
                emitted_positions.add(first_pos)
                # Для стабильной сортировки — присваиваем display_order по first_pos
                columns[-1] = self._with_display_order(
                    columns[-1], first_pos * _DISPLAY_ORDER_STEP
                )
                continue

            if value_name and value_name in candidates_by_name:
                # Правило B: paired status + value
                column = self._build_paired_column(
                    check_id=check_id,
                    prefix=prefix,
                    status_cfg=candidates_by_name[status_name],
                    value_cfg=candidates_by_name[value_name],
                )
                columns.append(column)
                used_names.add(status_name)
                used_names.add(value_name)
                first_pos = min(
                    candidate_positions[status_name],
                    candidate_positions[value_name],
                )
                emitted_positions.add(first_pos)
                columns[-1] = self._with_display_order(
                    columns[-1], first_pos * _DISPLAY_ORDER_STEP
                )
                continue

            # Правило C: standalone status
            column = self._build_standalone_status_column(
                check_id=check_id,
                status_cfg=candidates_by_name[status_name],
            )
            columns.append(column)
            used_names.add(status_name)
            pos = candidate_positions[status_name]
            emitted_positions.add(pos)
            columns[-1] = self._with_display_order(
                columns[-1], pos * _DISPLAY_ORDER_STEP
            )

        # Оставшиеся одиночные поля (не в парах)
        for cfg in column_candidates:
            if cfg.name in used_names:
                continue

            column = self._build_singleton_column(check_id=check_id, cfg=cfg)
            columns.append(column)
            pos = candidate_positions[cfg.name]
            columns[-1] = self._with_display_order(
                columns[-1], pos * _DISPLAY_ORDER_STEP
            )

        # Финальная сортировка по display_order
        columns.sort(key=lambda c: (c.display_order, c.column_id))

        return columns, metadata_fields, display_summary_field

    # ─── Column builders per rule ─────────────────────────────────────

    def _build_paired_column(
        self,
        check_id: str,
        prefix: str,
        status_cfg: ExtractionFieldConfig,
        value_cfg: ExtractionFieldConfig,
    ) -> DDGridColumnRuntime:
        """
        Правило A/B: paired status + details/value → одна text колонка.

        label берётся из value_cfg (details/value поле) если задан,
        иначе humanize(prefix).
        """
        canonical_values, _explicit = _normalize_allowed_values(
            status_cfg.allowed_values
        )
        status_present_value = _resolve_status_present_value(canonical_values)

        label = _get_label(value_cfg, fallback_name=prefix)

        return DDGridColumnRuntime(
            column_id=f"{check_id}__{prefix}",
            label=label,
            value_field=value_cfg.name,
            status_field=status_cfg.name,
            status_present_value=status_present_value,
            format="text",
            fallback_display=_DEFAULT_FALLBACK_DISPLAY,
            display_order=0,  # будет перезаписан в auto_map_columns
            enum_labels={},
            unit=value_cfg.unit,
        )

    def _build_standalone_status_column(
        self,
        check_id: str,
        status_cfg: ExtractionFieldConfig,
    ) -> DDGridColumnRuntime:
        """
        Правило C: одиночный <prefix>_status → presence_only колонка.
        """
        canonical_values, explicit_labels = _normalize_allowed_values(
            status_cfg.allowed_values
        )
        status_present_value = _resolve_status_present_value(canonical_values)
        enum_labels = _build_enum_labels(canonical_values, explicit_labels)

        return DDGridColumnRuntime(
            column_id=f"{check_id}__{status_cfg.name}",
            label=_get_label(status_cfg),
            value_field=None,
            status_field=status_cfg.name,
            status_present_value=status_present_value,
            format="presence_only",
            fallback_display=_DEFAULT_FALLBACK_DISPLAY,
            display_order=0,
            enum_labels=enum_labels,
            unit=status_cfg.unit,
        )

    def _build_singleton_column(
        self,
        check_id: str,
        cfg: ExtractionFieldConfig,
    ) -> DDGridColumnRuntime:
        """
        Правила D/E/F для одиночного поля.

        D. allowed_values ⊇ {yes, no} → yes_no
        E. allowed_values (другой enum) → enum
        F. text/number/date без allowed_values → text
        """
        canonical_values, explicit_labels = _normalize_allowed_values(
            cfg.allowed_values
        )
        canonical_set = set(canonical_values)

        # Правило D: yes/no
        if canonical_set >= _YES_NO_MARKERS:
            enum_labels = _build_enum_labels(canonical_values, explicit_labels)
            return DDGridColumnRuntime(
                column_id=f"{check_id}__{cfg.name}",
                label=_get_label(cfg),
                value_field=cfg.name,
                status_field=None,
                status_present_value=None,
                format="yes_no",
                fallback_display=_DEFAULT_FALLBACK_DISPLAY,
                display_order=0,
                enum_labels=enum_labels,
                unit=cfg.unit,
            )

        # Правило E: enum
        if canonical_values:
            enum_labels = _build_enum_labels(canonical_values, explicit_labels)
            return DDGridColumnRuntime(
                column_id=f"{check_id}__{cfg.name}",
                label=_get_label(cfg),
                value_field=cfg.name,
                status_field=None,
                status_present_value=None,
                format="enum",
                fallback_display=_DEFAULT_FALLBACK_DISPLAY,
                display_order=0,
                enum_labels=enum_labels,
                unit=cfg.unit,
            )

        # Правило F: одиночное text/number/date
        return DDGridColumnRuntime(
            column_id=f"{check_id}__{cfg.name}",
            label=_get_label(cfg),
            value_field=cfg.name,
            status_field=None,
            status_present_value=None,
            format="text",
            fallback_display=_DEFAULT_FALLBACK_DISPLAY,
            display_order=0,
            enum_labels={},
            unit=cfg.unit,
        )

    # ─── Utility ──────────────────────────────────────────────────────

    @staticmethod
    def _with_display_order(
        column: DDGridColumnRuntime,
        display_order: int,
    ) -> DDGridColumnRuntime:
        """
        Возвращает копию column с обновлённым display_order.
        DDGridColumnRuntime frozen, поэтому создаём новый экземпляр.
        """
        return DDGridColumnRuntime(
            column_id=column.column_id,
            label=column.label,
            value_field=column.value_field,
            status_field=column.status_field,
            status_present_value=column.status_present_value,
            format=column.format,
            fallback_display=column.fallback_display,
            display_order=display_order,
            enum_labels=column.enum_labels,
            unit=column.unit,
        )



        