# src/core/metrics.py

"""
Prometheus metrics for PII sanitization (Stage 5 of the pipeline).

Описывает счётчики и гистограмму, которые измеряют, как работает стадия
обезличивания (PII Sanitization) для документов.

Метрики:
- pii_entities_detected_total{entity_type} —
  общее количество найденных PII‑сущностей по типам
  (например, phone, email, passport, inn и т.п.);
- pii_entities_tokenized_total{entity_type} —
  сколько сущностей данного типа было заменено на токены/плейсхолдеры;
- pii_entities_preserved_total{entity_type} —
  сколько сущностей сохранено как есть (ИНН, ОГРН, кадастровые номера
  и другие PII, которые по бизнес‑логике не нужно затирать);
- pii_role_map_used_total —
  сколько раз применялась карта ролей контрагентов (party‑role mapping)
  при замене PII (например, вместо имён — «Покупатель», «Продавец»);
- pii_sanitization_duration_seconds —
  гистограмма времени обезличивания одного документа по бакетам
  (0.1, 0.5, 1, 2, 5, 10 секунд);
- pii_sanitization_skipped_total —
  количество документов, где стадия PII была пропущена, потому что
  документ уже был ранее санитизирован.

Назначение:
- мониторить объём и качество работы PII‑санитайзера;
- отслеживать производительность Stage 5;
- видеть влияние party‑role mapping и случаев пропуска обезличивания.
"""

from prometheus_client import Counter, Histogram

# ═══════════════════════════════════════════════════════════════════════════════
# PII Sanitization metrics (Stage 5)
# ═══════════════════════════════════════════════════════════════════════════════

pii_entities_detected_total = Counter(
    "pii_entities_detected_total",
    "Total PII entities detected",
    ["entity_type"],
)

pii_entities_tokenized_total = Counter(
    "pii_entities_tokenized_total",
    "Total PII entities replaced with tokens",
    ["entity_type"],
)

pii_entities_preserved_total = Counter(
    "pii_entities_preserved_total",
    "Total PII entities preserved (INN, OGRN, cadastral)",
    ["entity_type"],
)

pii_role_map_used_total = Counter(
    "pii_role_map_used_total",
    "Times party-role mapping was applied",
)

pii_sanitization_duration_seconds = Histogram(
    "pii_sanitization_duration_seconds",
    "Duration of PII sanitization per document",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

pii_sanitization_skipped_total = Counter(
    "pii_sanitization_skipped_total",
    "Documents skipped (already sanitized)",
)
