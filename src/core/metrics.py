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
