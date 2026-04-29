// =============================================================
// src/types/exports.ts
// Типы для экспортов и audit log.
// Синхронизировано с текущим API-контрактом экспортов.
// =============================================================

export type ExportType =
  | "grid_xlsx"
  | "deal_summary_xlsx"
  | "report_docx"
  | "report_pdf"
  | "requests_docx"
  | "aggregated_json"
  | string;

export type ExportStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | string;

export interface ExportRecord {
  id: string;
  deal_id: string;
  run_id: string;

  export_type: ExportType;
  status: ExportStatus;

  file_ref: string | null;
  file_refs: Record<string, unknown> | null;

  requested_by: string | null;
  requester_role: string | null;

  file_size_bytes: number | null;

  created_at: string | null;
  updated_at: string | null;

  download_url: string | null;
  error_message: string | null;
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


