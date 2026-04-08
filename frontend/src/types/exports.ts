// =============================================================
// src/types/exports.ts
// Типы для экспортов и audit log.
// =============================================================

export interface ExportRecord {
  id: string;
  deal_id: string;
  run_id: string;
  export_type: string; // "grid_xlsx" | "deal_summary_xlsx" | "report_docx" | "report_pdf" и т.п.
  file_ref: string;
  file_size_bytes: number;
  status: "pending" | "processing" | "completed" | "failed";
  requested_by: string;
  requester_role: string;
  created_at: string;
  download_url?: string;
}

export interface AuditLogEntry {
  id: string;
  tenant_id: string;
  deal_id: string | null;
  action: string;
  actor: string;
  actor_role: string;
  details: Record<string, unknown>;
  created_at: string;
}

