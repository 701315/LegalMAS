// =============================================================
// src/pages/tenant-admin/components/LogsTable.tsx
//
// Таблица log entries с selection. Используется в двух местах:
// - Main admin panel → tab "Логи" (compact = false)
// - ProjectDrillDown → tab "Логи" (compact = true)
//
// Compact mode: скрывает колонки Queue и Worker, использует меньший
// max-width для Event колонки. Применяется в drill down где меньше
// horizontal space.
//
// Design contract:
// - Sticky header (top-0) с elevated-soft background
// - Row selection через selectedIdx (null = ничего не выбрано)
// - Selected row подсвечена accent-muted
// - Grouped entries (count > 1) показывают Layers icon с ×N
// - Timestamp, Level, Event, Stage — всегда видны
// - Queue, Worker — только в non-compact mode
// =============================================================

import React from "react";
import { Layers } from "lucide-react";
import type { LogEntry } from "../../../api/tenantAdmin";
import { LABEL_XS } from "../constants";
import { formatDateTime } from "../utils";
import LevelBadge from "./LevelBadge";

export interface LogsTableProps {
  /** Массив log entries для отображения */
  logs: LogEntry[];
  /** Индекс выбранной строки (null если ничего не выбрано) */
  selectedIdx: number | null;
  /** Callback при клике на строку */
  onSelect: (idx: number) => void;
  /**
   * Compact mode: скрывает Queue и Worker колонки.
   * Используется в drill down где меньше horizontal space.
   * Default: false (полная таблица)
   */
  compact?: boolean;
}

const LogsTable: React.FC<LogsTableProps> = ({
  logs,
  selectedIdx,
  onSelect,
  compact = false,
}) => (
  <table
    className={`w-full ${compact ? "min-w-[720px]" : "min-w-[920px]"} border-collapse`}
  >
    <thead className="sticky top-0 z-10 bg-[var(--bg-elevated-soft)]">
      <tr className="border-b border-[var(--border)]">
        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Timestamp</th>
        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Level</th>
        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Event</th>
        <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Stage</th>
        {!compact && (
          <>
            <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Queue</th>
            <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>Worker</th>
          </>
        )}
      </tr>
    </thead>
    <tbody>
      {logs.map((entry, idx) => {
        const sel = selectedIdx === idx;
        const grouped = (entry.count ?? 1) > 1;

        return (
          <tr
            key={idx}
            className={`cursor-pointer border-b border-[var(--border-subtle)] transition-colors ${
              sel
                ? "bg-[var(--accent-muted)]"
                : "hover:bg-[var(--bg-elevated-soft)]"
            }`}
            onClick={() => onSelect(idx)}
          >
            <td className="px-4 py-2.5 align-top text-[10px] text-[var(--text-secondary)]">
              {formatDateTime(entry.timestamp)}
            </td>
            <td className="px-4 py-2.5 align-top">
              <div className="flex flex-wrap items-center gap-1">
                <LevelBadge level={entry.level} />
                {grouped && (
                  <span
                    className="inline-flex items-center gap-0.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]"
                    title="Группа повторяющихся событий"
                  >
                    <Layers size={9} />×{entry.count}
                  </span>
                )}
              </div>
            </td>
            <td className="px-4 py-2.5 align-top">
              <div className={compact ? "max-w-[340px]" : "max-w-[400px]"}>
                <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                  {entry.event || "—"}
                </p>
                <p className="mt-0.5 truncate text-[10px] text-[var(--text-muted)]">
                  {entry.logger || "—"}
                  {entry.run_id ? ` · run ${entry.run_id.slice(0, 8)}…` : ""}
                </p>
              </div>
            </td>
            <td className="px-4 py-2.5 align-top text-sm text-[var(--text-secondary)]">
              {entry.stage || "—"}
            </td>
            {!compact && (
              <>
                <td className="px-4 py-2.5 align-top text-sm text-[var(--text-secondary)]">
                  {entry.queue || "—"}
                </td>
                <td className="px-4 py-2.5 align-top text-sm text-[var(--text-secondary)]">
                  <span className="inline-block max-w-[180px] truncate">
                    {entry.worker_hostname || "—"}
                  </span>
                </td>
              </>
            )}
          </tr>
        );
      })}
    </tbody>
  </table>
);

export default LogsTable;


