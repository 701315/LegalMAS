// =============================================================
// src/types/ddRequests.ts
// Типы для DD requests.
// =============================================================

// =============================================================
// Structured value normalization
// Единый helper для нормализации structured_values.
// Используется в RequestSidePanel и ReviewRequestSidePanel.
// Источник типизации: поддерживает оба формата —
//   новый: { field_name, field_value, field_format? }
//   legacy: { [key: string]: unknown }
// =============================================================

export type StructuredValue =
  | { field_name: string; field_value: unknown; field_format?: string | null }
  | Record<string, unknown>;

export function isTypedStructuredValue(
  sv: StructuredValue,
): sv is { field_name: string; field_value: unknown; field_format?: string | null } {
  return (
    typeof sv === "object" &&
    sv !== null &&
    "field_name" in sv &&
    typeof (sv as Record<string, unknown>).field_name === "string"
  );
}

export function normalizeStructuredValue(sv: StructuredValue): {
  key: string;
  value: string;
  format: string | null;
} {
  if (isTypedStructuredValue(sv)) {
    return {
      key: sv.field_name,
      value: sv.field_value != null ? String(sv.field_value) : "—",
      format: sv.field_format ?? null,
    };
  }
  // Legacy: берём первую пару ключ-значение
  const entries = Object.entries(sv);
  if (entries.length === 0) return { key: "?", value: "—", format: null };
  const [k, v] = entries[0];
  return {
    key: String(k),
    value: v != null ? String(v) : "—",
    format: null,
  };
}


/** Один DD-запрос — требование предоставить документ/информацию */
export interface DDRequest {
  id: string;
  deal_id: string;
  priority: "critical" | "high" | "medium";
  text: string;
  status: "open" | "in_progress" | "resolved";

  // Расширенные поля
  check_id?: string;

  /** Адресат запроса (из YAML dd_request_templates) */
  addressee?: string;

  structured_values?: StructuredValue[];

  /** Источник запроса */
  source?: "yaml_template" | "manual" | "aggregator";

  document_refs: string[];
  evidence_refs: string[];
  created_at: string;
  updated_at?: string;
}

export interface DDRequestCreateInput {
  check_id: string;
  check_name: string;
  text: string;
  priority: "critical" | "high" | "medium";
  addressee?: string;
  source?: "manual";
}

