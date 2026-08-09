// =============================================================
// src/pages/tenant-admin/components/LogDetailsPane.tsx
//
// Панель деталей выбранного log entry. Показывается справа от
// LogsTable на xl+ viewport, или снизу (as card) на меньших.
//
// Отображает:
// - Header с timestamp + "JSON" (copy) + "✕" (clear) buttons
// - Level badge + Stage/Queue chips + Grouped indicator
// - Event card (full text)
// - MetaFields grid (Logger, Worker, Deal ID, Run ID, Document ID, ...)
// - Raw JSON pre-block
//
// Correlation actions:
// - Run ID / Document ID / Task ID имеют action buttons
// - Клик применяет correlation фильтр в parent logs list
//
// Design contract:
// - Empty state если entry === null
// - Scroll внутри panel (overflow-auto на body)
// - Copy button показывает "Скопировано" на 1.8s (управляется в parent)
// =============================================================

import React from "react";
import { Copy, Layers } from "lucide-react";
import type { LogEntry } from "../../../api/tenantAdmin";
import Button from "../../../components/ui/Button";
import {
  LABEL_XS,
  SECTION_HEADER_WRAP,
  SECTION_HEADER_INNER,
  SECTION_DIVIDER,
} from "../constants";
import { formatDateTime } from "../utils";
import LevelBadge from "./LevelBadge";
import MetaField from "./MetaField";

export interface LogDetailsCorrelations {
  onFilterByRun?: (runId: string) => void;
  onFilterByDocument?: (documentId: string) => void;
  onFilterByTask?: (taskId: string) => void;
}

export interface LogDetailsPaneProps {
  /** Выбранный log entry (null = показать empty state) */
  entry: LogEntry | null;
  /** Показать "Скопировано" вместо "JSON" на button */
  copied: boolean;
  /** Callback для copy to clipboard */
  onCopy: () => void;
  /** Callback для закрытия panel (unselect entry) */
  onClear: () => void;
  /** Опциональные correlation handlers для Run/Document/Task ID */
  correlations?: LogDetailsCorrelations;
}

const LogDetailsPane: React.FC<LogDetailsPaneProps> = ({
  entry,
  copied,
  onCopy,
  onClear,
  correlations,
}) => {
  if (!entry) {
    return (
      <div className="flex h-full items-center justify-center p-5">
        <div className="text-center">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            Выберите запись лога
          </p>
          <p className="mt-1 text-[10px] text-[var(--text-muted)]">
            Нажмите на строку в таблице, чтобы увидеть подробности
          </p>
        </div>
      </div>
    );
  }

  const isGrouped = (entry.count ?? 1) > 1;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={SECTION_HEADER_WRAP}>
        <div
          className={`flex items-start justify-between gap-3 ${SECTION_HEADER_INNER}`}
        >
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              Детали лога
            </p>
            <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
              {formatDateTime(entry.timestamp)}
            </p>
          </div>
          <div className="flex shrink-0 gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              onClick={onCopy}
              leftIcon={<Copy size={12} />}
            >
              {copied ? "Скопировано" : "JSON"}
            </Button>
            <Button size="sm" variant="ghost" onClick={onClear}>
              ✕
            </Button>
          </div>
        </div>
        <div className={SECTION_DIVIDER} />
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-4">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <LevelBadge level={entry.level} />
            {entry.stage && (
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
                {entry.stage}
              </span>
            )}
            {entry.queue && (
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
                {entry.queue}
              </span>
            )}
            {isGrouped && (
              <span
                className="inline-flex items-center gap-1 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]"
                title="Группа повторяющихся событий"
              >
                <Layers size={10} />×{entry.count}
              </span>
            )}
          </div>

          <div className="rounded-xl border border-[var(--border)] px-3 py-2">
            <p className={LABEL_XS}>Event</p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-primary)]">
              {entry.event || "—"}
            </p>
            {isGrouped && entry.first_seen && entry.last_seen && (
              <p className="mt-2 text-[10px] text-[var(--text-muted)]">
                Первое: {formatDateTime(entry.first_seen)} · Последнее:{" "}
                {formatDateTime(entry.last_seen)}
              </p>
            )}
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <MetaField label="Logger" value={entry.logger} />
            <MetaField label="Worker" value={entry.worker_hostname} />
            <MetaField label="Deal ID" value={entry.deal_id} />
            <MetaField
              label="Run ID"
              value={entry.run_id}
              onClick={
                entry.run_id && correlations?.onFilterByRun
                  ? () => correlations.onFilterByRun?.(entry.run_id as string)
                  : undefined
              }
              actionLabel="Все логи run"
            />
            <MetaField
              label="Document ID"
              value={entry.document_id}
              onClick={
                entry.document_id && correlations?.onFilterByDocument
                  ? () =>
                      correlations.onFilterByDocument?.(
                        entry.document_id as string,
                      )
                  : undefined
              }
              actionLabel="Все логи документа"
            />
            <MetaField
              label="Task ID"
              value={entry.task_id}
              onClick={
                entry.task_id && correlations?.onFilterByTask
                  ? () => correlations.onFilterByTask?.(entry.task_id as string)
                  : undefined
              }
              actionLabel="Все логи task"
            />
            <MetaField label="Task name" value={entry.task_name} />
            <MetaField label="Timestamp" value={entry.timestamp} />
          </div>

          <div>
            <p className={LABEL_XS}>Raw JSON</p>
            <pre className="mt-1.5 overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--bg-base)] px-4 py-3 text-[10px] leading-5 text-[var(--text-secondary)]">
              {JSON.stringify(entry.raw, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LogDetailsPane;


