import React, { useState } from "react";
import { NavLink } from "react-router-dom";
import { BookOpen, FileText, RefreshCw, Shield } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import { syncGlobalChecks, syncDocTypes } from "../../api/instructions/globalInstructions";
import { useInstructionPermissions } from "../../hooks/instructions/useInstructionPermissions";
import type { SyncResultUnion } from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// Sync result display helpers
// ─────────────────────────────────────────────────────────────

/**
 * Форматирует строку-итог для конкретного типа sync.
 * Разные поля у global (repaired) и doc-types (promoted).
 */
function formatSyncSummary(result: SyncResultUnion): string {
  const parts: string[] = [];

  if (result.created > 0) parts.push(`создано: ${result.created}`);

  if (result.kind === "global-checks" && result.repaired > 0) {
    parts.push(`обновлено: ${result.repaired}`);
  }
  if (result.kind === "doc-types" && result.promoted > 0) {
    parts.push(`промоутировано: ${result.promoted}`);
  }

  if (result.skipped > 0) parts.push(`пропущено: ${result.skipped}`);
  if (result.errors > 0) parts.push(`ошибок: ${result.errors}`);

  const summary = parts.length > 0 ? parts.join(", ") : "изменений нет";
  const prefix = result.dry_run ? "[Preview] " : "";
  return `${prefix}${summary} (всего: ${result.total})`;
}

// ─────────────────────────────────────────────────────────────
// Sync result banner
// ─────────────────────────────────────────────────────────────

interface SyncResultBannerProps {
  result: SyncResultUnion;
  onDismiss: () => void;
}

const SyncResultBanner: React.FC<SyncResultBannerProps> = ({
  result,
  onDismiss,
}) => {
  const hasErrors = result.errors > 0;
  const label =
    result.kind === "global-checks" ? "Global Checks" : "Doc-Types";

  return (
    <div
      className={[
        "flex items-start justify-between gap-3 rounded-lg border px-3 py-2.5 text-xs",
        hasErrors
          ? "border-[var(--color-error)]/30 bg-[var(--color-error)]/8 text-[var(--color-error)]"
          : "border-[var(--color-success)]/30 bg-[var(--color-success)]/8 text-[var(--color-success)]",
      ].join(" ")}
    >
      <div className="min-w-0 space-y-0.5">
        <div className="font-medium">
          {hasErrors
            ? `Sync ${label}: завершено с ошибками`
            : `Sync ${label}: успешно`}
        </div>
        <div className="text-[var(--text-secondary)]">
          {formatSyncSummary(result)}
        </div>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="shrink-0 leading-none opacity-60 hover:opacity-100"
        aria-label="Закрыть"
      >
        ×
      </button>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Error banner
// ─────────────────────────────────────────────────────────────

interface SyncErrorBannerProps {
  kind: "global-checks" | "doc-types";
  error: Error;
  onDismiss: () => void;
}

const SyncErrorBanner: React.FC<SyncErrorBannerProps> = ({
  kind,
  error,
  onDismiss,
}) => {
  const label = kind === "global-checks" ? "Global Checks" : "Doc-Types";

  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/8 px-3 py-2.5 text-xs text-[var(--color-error)]">
      <div className="min-w-0 space-y-0.5">
        <div className="font-medium">Sync {label}: ошибка запроса</div>
        <div className="break-all text-[var(--text-secondary)]">
          {error.message}
        </div>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="shrink-0 leading-none opacity-60 hover:opacity-100"
        aria-label="Закрыть"
      >
        ×
      </button>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Sync action button
// ─────────────────────────────────────────────────────────────

interface SyncButtonProps {
  label: string;
  isPending: boolean;
  onClick: () => void;
}

const SyncButton: React.FC<SyncButtonProps> = ({
  label,
  isPending,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    disabled={isPending}
    className={[
      "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5",
      "text-xs font-medium transition-colors",
      "border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-secondary)]",
      "hover:border-[var(--accent-primary)]/40 hover:text-[var(--text-primary)]",
      "disabled:cursor-not-allowed disabled:opacity-50",
    ].join(" ")}
  >
    <RefreshCw
      className={["h-3 w-3", isPending ? "animate-spin" : ""].join(" ")}
      aria-hidden="true"
    />
    {isPending ? "Синхронизация…" : label}
  </button>
);

// ─────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────

const InstructionsIndexPage: React.FC = () => {
  const { canEditGlobalBase } = useInstructionPermissions();

  // Последний успешный результат sync (один за раз — последний победитель)
  const [lastResult, setLastResult] = useState<SyncResultUnion | null>(null);
  const [lastError, setLastError] = useState<{
    kind: "global-checks" | "doc-types";
    error: Error;
  } | null>(null);

  // ── Mutations ──────────────────────────────────────────────

  const globalSyncMutation = useMutation({
    mutationFn: () => syncGlobalChecks(false),
    onSuccess: (data) => {
      setLastError(null);
      setLastResult({ kind: "global-checks", ...data });
    },
    onError: (error: Error) => {
      setLastResult(null);
      setLastError({ kind: "global-checks", error });
    },
  });

  const docTypesSyncMutation = useMutation({
    mutationFn: () => syncDocTypes({ dryRun: false }),
    onSuccess: (data) => {
      setLastError(null);
      setLastResult({ kind: "doc-types", ...data });
    },
    onError: (error: Error) => {
      setLastResult(null);
      setLastError({ kind: "doc-types", error });
    },
  });

  const isAnySyncPending =
    globalSyncMutation.isPending || docTypesSyncMutation.isPending;

  // ── Render ─────────────────────────────────────────────────

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">

        {/* Header */}
        <div className="space-y-1">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
            Admin · Instructions
          </p>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-0.5">
              <h1 className="text-base font-semibold tracking-tight text-[var(--text-primary)]">
                Управление инструкциями
              </h1>
              <p className="text-xs text-[var(--text-secondary)]">
                Глобальные playbooks, universal checks и инструкции по типам
                документов. Изменения публикуются через draft → validate →
                publish flow.
              </p>
            </div>

            {/* Sync panel — только superadmin */}
            {canEditGlobalBase && (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <span className="text-[11px] text-[var(--text-muted)]">
                  Синхронизировать с источником:
                </span>
                <SyncButton
                  label="Global Checks"
                  isPending={globalSyncMutation.isPending}
                  onClick={() => {
                    if (!isAnySyncPending) globalSyncMutation.mutate();
                  }}
                />
                <SyncButton
                  label="Doc-Types"
                  isPending={docTypesSyncMutation.isPending}
                  onClick={() => {
                    if (!isAnySyncPending) docTypesSyncMutation.mutate();
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {/* Sync result / error banners */}
        {lastResult && (
          <SyncResultBanner
            result={lastResult}
            onDismiss={() => setLastResult(null)}
          />
        )}
        {lastError && (
          <SyncErrorBanner
            kind={lastError.kind}
            error={lastError.error}
            onDismiss={() => setLastError(null)}
          />
        )}

        {/* Navigation cards — без изменений */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">

          <NavLink
            to="/admin/instructions/global-playbooks"
            className="block rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
                <BookOpen
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  Global Playbooks
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Базовые playbooks для всех tenant. Управление версиями,
                  draft/publish flow.
                </div>
              </div>
            </div>
          </NavLink>

          <NavLink
            to="/admin/instructions/global-checks"
            className="block rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
                <Shield
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  Global Instructions
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Универсальные проверки для любых документов:
                  конфиденциальность, применимое право, срок действия и др.
                </div>
              </div>
            </div>
          </NavLink>

          <NavLink
            to="/admin/instructions/doc-types"
            className="block rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
                <FileText
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  Doc-Type Instructions
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Инструкции по типам документов. Базовые настройки
                  extraction, checks, retrieval.
                </div>
              </div>
            </div>
          </NavLink>

        </div>
      </div>
    </div>
  );
};

export default InstructionsIndexPage;


