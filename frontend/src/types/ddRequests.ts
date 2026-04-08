// =============================================================
// src/types/ddRequests.ts
// Типы для DD requests.
// =============================================================

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

  structured_values?: Record<string, unknown>[];

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

