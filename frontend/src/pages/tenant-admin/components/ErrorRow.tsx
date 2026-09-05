// =============================================================
// src/pages/tenant-admin/components/ErrorRow.tsx
//
// Error row in the "Problems & Errors" table inside
// ProjectDrillDown. Displays: error type (Document/Run),
// object (name + time), status/stage, error message,
// and "Logs" action button.
//
// Expandable: clicking expands a second <tr> with MetaFields
// (Document ID, Run ID, Stage, Error type, Reason, Time) and
// raw error_details JSON.
//
// Design contract:
// - Clickable row → toggle expand
// - "Logs" button → open logs tab with correlation filter (no toggle)
// - Chevron icon indicates expand state
// - Semantic tone for status: failed = error, quarantine/completed_with_errors = warn
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ProjectErrorItem } from "../../../api/tenantAdmin";
import Button from "../../../components/ui/Button";
import { LABEL_XS } from "../constants";
import { formatDateTime } from "../utils";
import MetaField from "./MetaField";

export interface ErrorRowProps {
  /** Error item to display */
  item: ProjectErrorItem;
  /** Whether the row is expanded to show details and raw JSON */
  expanded: boolean;
  /** Callback to toggle expand/collapse state */
  onToggle: () => void;
  /** Callback on "Logs" click — opens logs tab with correlation filter */
  onOpenLogs: () => void;
}

const ErrorRow: React.FC<ErrorRowProps> = ({
  item,
  expanded,
  onToggle,
  onOpenLogs,
}) => {
  const { t, i18n } = useTranslation("tenantAdmin");
  const isDoc = item.kind === "document";

  const title = isDoc
    ? item.document_filename ||
      t("errorRow.documentFallback", { id: item.document_id?.slice(0, 8) ?? "" })
    : t("errorRow.runFallback", { id: item.run_id?.slice(0, 8) ?? "" });

  const rawStatus = isDoc ? item.document_status : item.run_status;

  const statusText = isDoc
    ? t(`documentStatusLabels.${rawStatus}`, { defaultValue: rawStatus ?? "—" })
    : t(`runStatusLabels.${rawStatus}`, { defaultValue: rawStatus ?? "—" });

  const statusTone: "error" | "warn" | "neutral" =
    (isDoc && item.document_status === "failed") ||
    (!isDoc && item.run_status === "failed")
      ? "error"
      : (isDoc && item.document_status === "quarantine") ||
          (!isDoc && item.run_status === "completed_with_errors")
        ? "warn"
        : "neutral";

  return (
    <>
      <tr
        className="cursor-pointer border-b border-[var(--border-subtle)] transition-colors hover:bg-[var(--bg-elevated-soft)]"
        onClick={onToggle}
      >
        <td className="px-4 py-3 align-top">
          <div className="flex items-center gap-2">
            {expanded ? (
              <ChevronDown
                size={14}
                className="shrink-0 text-[var(--text-muted)]"
              />
            ) : (
              <ChevronRight
                size={14}
                className="shrink-0 text-[var(--text-muted)]"
              />
            )}
            <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
              {isDoc ? t("errorRow.document") : t("errorRow.run")}
            </span>
          </div>
        </td>
        <td className="px-4 py-3 align-top">
          <p className="truncate text-sm font-medium text-[var(--text-primary)]">
            {title}
          </p>
          <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
            {formatDateTime(item.occurred_at, i18n.language)}
          </p>
        </td>
        <td className="px-4 py-3 align-top">
          <span
            className={`text-xs font-medium ${
              statusTone === "error"
                ? "text-[var(--color-error-text)]"
                : statusTone === "warn"
                  ? "text-[var(--color-warning-text)]"
                  : "text-[var(--text-secondary)]"
            }`}
          >
            {statusText}
          </span>
          {item.stage && (
            <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
              {t("errorRow.stageLabel", { stage: item.stage })}
            </p>
          )}
        </td>
        <td className="px-4 py-3 align-top">
          <div className="max-w-[420px]">
            <p className="truncate text-sm text-[var(--text-primary)]">
              {item.error_message || item.error_type || item.error_reason || "—"}
            </p>
            {item.error_type && item.error_message && (
              <p className="mt-0.5 truncate text-[10px] text-[var(--text-muted)]">
                {item.error_type}
                {item.error_reason ? ` · ${item.error_reason}` : ""}
              </p>
            )}
          </div>
        </td>
        <td className="px-4 py-3 align-top text-right">
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              onOpenLogs();
            }}
          >
            {t("errorRow.logs")}
          </Button>
        </td>
      </tr>

      {expanded && (
        <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]">
          <td colSpan={5} className="px-4 py-3">
            <div className="ml-6 space-y-2">
              <div className="grid gap-2 sm:grid-cols-2">
                {isDoc && (
                  <>
                    <MetaField
                      label={t("errorRow.documentId")}
                      value={item.document_id}
                    />
                    <MetaField
                      label={t("errorRow.file")}
                      value={item.document_filename}
                    />
                  </>
                )}
                {!isDoc && (
                  <MetaField
                    label={t("errorRow.runId")}
                    value={item.run_id}
                  />
                )}
                <MetaField
                  label={t("errorRow.stage")}
                  value={item.stage}
                />
                <MetaField
                  label={t("errorRow.errorType")}
                  value={item.error_type}
                />
                <MetaField
                  label={t("errorRow.reason")}
                  value={item.error_reason}
                />
                <MetaField
                  label={t("errorRow.time")}
                  value={formatDateTime(item.occurred_at, i18n.language)}
                />
              </div>

              {item.error_details &&
                Object.keys(item.error_details).length > 0 && (
                  <div>
                    <p className={LABEL_XS}>{t("errorRow.rawDetails")}</p>
                    <pre className="mt-1.5 overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-[10px] leading-5 text-[var(--text-secondary)]">
                      {JSON.stringify(item.error_details, null, 2)}
                    </pre>
                  </div>
                )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
};

export default ErrorRow;


