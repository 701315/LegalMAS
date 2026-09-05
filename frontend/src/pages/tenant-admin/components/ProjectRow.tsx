// =============================================================
// src/pages/tenant-admin/components/ProjectRow.tsx
//
// Project row in the "Projects" table of the admin panel.
// Displays: project name, document statistics, last run status,
// checks progress, and "Open" action button.
//
// Design contract:
// - Clickable row (cursor-pointer + hover effect)
// - AlertTriangle icon before title if there are issues
// - Progress bar color reflects run status
// - "Open" button stops propagation (doesn't trigger row click)
//
// Business logic:
// - hasProblems: failed_documents > 0 OR quarantine_documents > 0 OR run.has_errors
// - progress %: completed_checks / total_checks * 100 (only if total > 0)
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import type { ProjectHealthDTO } from "../../../api/tenantAdmin";
import Button from "../../../components/ui/Button";
import { RUN_STATUS_CONFIG } from "../constants";
import { formatDate, formatDateTime, toneClass } from "../utils";

export interface ProjectRowProps {
  /** Project to display */
  project: ProjectHealthDTO;
  /** Callback when clicking row or "Open" button */
  onOpen: (id: string) => void;
}

const ProjectRow: React.FC<ProjectRowProps> = ({ project, onOpen }) => {
  const { t, i18n } = useTranslation("tenantAdmin");
  const run = project.last_run;
  const cfg = run?.status ? RUN_STATUS_CONFIG[run.status] : null;

  const pct =
    run && run.total_checks > 0
      ? Math.round((run.completed_checks / run.total_checks) * 100)
      : null;

  const hasProblems =
    project.failed_documents > 0 ||
    project.quarantine_documents > 0 ||
    run?.has_errors === true;

  const barColor =
    run?.status === "failed"
      ? "bg-[var(--color-error)]"
      : run?.status === "completed"
        ? "bg-[var(--color-success)]"
        : run?.status === "completed_with_errors"
          ? "bg-[var(--color-warning)]"
          : "bg-[var(--accent-primary)]";

  const statusLabel = run?.status
    ? t(`runStatusLabels.${run.status}`, { defaultValue: cfg?.label ?? run.status })
    : null;

  return (
    <tr
      className="cursor-pointer border-b border-[var(--border-subtle)] transition-colors hover:bg-[var(--bg-elevated-soft)]"
      onClick={() => onOpen(project.deal_id)}
    >
      <td className="px-4 py-3">
        <div className="flex items-start gap-2">
          {hasProblems && (
            <AlertTriangle
              size={14}
              className="mt-0.5 shrink-0 text-[var(--color-warning-text)]"
            />
          )}
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
              {project.deal_name}
            </p>
            <p className="text-[10px] text-[var(--text-muted)]">
              {t("projectRow.createdAt", {
                date: formatDate(project.created_at, i18n.language) ?? "—",
              })}
            </p>
          </div>
        </div>
      </td>

      <td className="px-4 py-3 text-center">
        <p className="text-sm font-semibold tabular-nums text-[var(--text-primary)]">
          {project.total_documents}
        </p>
        {(project.failed_documents > 0 ||
          project.quarantine_documents > 0) && (
          <p className="text-[10px]">
            {project.failed_documents > 0 && (
              <span className="text-[var(--color-error-text)]">
                {t("projectRow.errorsInline", {
                  count: project.failed_documents,
                })}
              </span>
            )}
            {project.failed_documents > 0 &&
              project.quarantine_documents > 0 &&
              " · "}
            {project.quarantine_documents > 0 && (
              <span className="text-[var(--color-warning-text)]">
                {t("projectRow.quarantineInline", {
                  count: project.quarantine_documents,
                })}
              </span>
            )}
          </p>
        )}
      </td>

      <td className="px-4 py-3">
        {cfg && run ? (
          <div className="space-y-0.5">
            <p className={`text-xs font-medium ${toneClass(cfg.tone)}`}>
              {statusLabel}
            </p>
            {run.completed_at && (
              <p className="text-[10px] text-[var(--text-muted)]">
                {formatDateTime(run.completed_at, i18n.language)}
              </p>
            )}
          </div>
        ) : (
          <span className="text-[10px] text-[var(--text-muted)]">
            {t("projectRow.notLaunched")}
          </span>
        )}
      </td>

      <td className="px-4 py-3">
        {pct !== null && run ? (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[10px] tabular-nums">
              <span className="text-[var(--text-muted)]">
                {run.completed_checks}/{run.total_checks}
              </span>
              <span className="font-semibold text-[var(--text-primary)]">
                {pct}%
              </span>
            </div>
            <div className="h-1 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">
              <div
                className={`h-1 rounded-full transition-all duration-500 ease-out ${barColor}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        ) : (
          <span className="text-[10px] text-[var(--text-muted)]">—</span>
        )}
      </td>

      <td className="px-4 py-3">
        <Button
          size="sm"
          variant="secondary"
          onClick={(e) => {
            e.stopPropagation();
            onOpen(project.deal_id);
          }}
        >
          {t("projectRow.open")}
        </Button>
      </td>
    </tr>
  );
};

export default ProjectRow;


