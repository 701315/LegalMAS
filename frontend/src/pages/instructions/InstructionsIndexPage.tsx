// src/pages/instructions/InstructionsIndexPage.tsx
// Главная страница управления инструкциями для superadmin.
// Точка входа в базовые инструкции платформы, Playbook Studio
// и базовые playbooks.

import React, { useState } from "react";
import { NavLink } from "react-router-dom";
import { BookOpen, FileText, RefreshCw, Shield, X } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import {
  syncGlobalChecks,
  syncDocTypes,
} from "../../api/instructions/globalInstructions";
import { useInstructionPermissions } from "../../hooks/instructions/useInstructionPermissions";
import Button from "../../components/ui/Button";
import type { SyncResultUnion } from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// Sync summary helpers
// ─────────────────────────────────────────────────────────────

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

function syncKindLabel(kind: "global-checks" | "doc-types"): string {
  return kind === "global-checks"
    ? "Global Instructions"
    : "Doc-type Instructions";
}

// ─────────────────────────────────────────────────────────────
// SyncResultBanner
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
  const label = syncKindLabel(result.kind);

  return (
    <div
      className={[
        "flex items-start justify-between gap-3 rounded-2xl border px-4 py-3 text-sm",
        hasErrors
          ? "border-rose-200 bg-rose-50 text-rose-700"
          : "border-emerald-200 bg-emerald-50 text-emerald-700",
      ].join(" ")}
    >
      <div className="min-w-0 space-y-0.5">
        <div className="font-medium">
          {hasErrors
            ? `Обновление БД ${label}: завершено с ошибками`
            : `Обновление БД ${label}: успешно`}
        </div>
        <div className="text-xs text-[var(--text-secondary)]">
          {formatSyncSummary(result)}
        </div>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Закрыть"
        className="shrink-0 rounded-md p-1 opacity-60 transition-opacity hover:opacity-100"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// SyncErrorBanner
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
  const label = syncKindLabel(kind);

  return (
    <div className="flex items-start justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      <div className="min-w-0 space-y-0.5">
        <div className="font-medium">
          Обновление БД {label}: ошибка запроса
        </div>
        <div className="break-all text-xs text-[var(--text-secondary)]">
          {error.message}
        </div>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Закрыть"
        className="shrink-0 rounded-md p-1 opacity-60 transition-opacity hover:opacity-100"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// SyncActionsPanel
//
// Обе кнопки одной ширины (min-w-[260px]), выравниваются
// на одной строке при достаточной ширине экрана и переносятся
// на мобильных.
// ─────────────────────────────────────────────────────────────

interface SyncActionsPanelProps {
  isGlobalPending: boolean;
  isDocTypesPending: boolean;
  onSyncGlobal: () => void;
  onSyncDocTypes: () => void;
}

const SyncActionsPanel: React.FC<SyncActionsPanelProps> = ({
  isGlobalPending,
  isDocTypesPending,
  onSyncGlobal,
  onSyncDocTypes,
}) => {
  const isAnyPending = isGlobalPending || isDocTypesPending;

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Синхронизация с источником
          </h2>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            Обновляет базы данных Global Instructions и Doc-type Instructions
            из репозитория конфигураций платформы.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={onSyncGlobal}
            disabled={isAnyPending}
            isLoading={isGlobalPending}
            leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            className="min-w-[260px] justify-center"
          >
            Обновить БД Global Instructions
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={onSyncDocTypes}
            disabled={isAnyPending}
            isLoading={isDocTypesPending}
            leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            className="min-w-[260px] justify-center"
          >
            Обновить БД Doc-type Instructions
          </Button>
        </div>
      </div>
    </section>
  );
};

// ─────────────────────────────────────────────────────────────
// NavCard — карточка навигации
// ─────────────────────────────────────────────────────────────

interface NavCardProps {
  to: string;
  title: string;
  description: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
}

const NavCard: React.FC<NavCardProps> = ({
  to,
  title,
  description,
  icon: Icon,
}) => (
  <NavLink
    to={to}
    className="group rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md"
  >
    <div className="flex items-start gap-3">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] transition-colors group-hover:bg-[var(--accent-muted)] group-hover:text-[var(--accent-primary)]">
        <Icon className="h-4 w-4" aria-hidden="true" />
      </div>
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
          {title}
        </h3>
        <p className="mt-0.5 text-xs text-[var(--text-muted)]">
          {description}
        </p>
      </div>
    </div>
  </NavLink>
);

// ─────────────────────────────────────────────────────────────
// SectionHeading — заголовок раздела
// Единый стиль для всех трёх разделов страницы.
// ─────────────────────────────────────────────────────────────

const SectionHeading: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => (
  <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
    {children}
  </h2>
);

// ─────────────────────────────────────────────────────────────
// InstructionsIndexPage
// ─────────────────────────────────────────────────────────────

const InstructionsIndexPage: React.FC = () => {
  const { canEditGlobalBase } = useInstructionPermissions();

  // Последний результат/ошибка sync — один за раз (последний победитель)
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

  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-6">

        {/* ── Заголовок страницы (на фоне) ─────────────────── */}
        <header>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            Инструкции
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Управление базовыми инструкциями платформы, playbook studio и
            версиями базовых playbooks. Изменения публикуются через flow
            draft&nbsp;→&nbsp;validate&nbsp;→&nbsp;publish.
          </p>
        </header>

        {/* ── Синхронизация — только superadmin ─────────────── */}
        {canEditGlobalBase && (
          <SyncActionsPanel
            isGlobalPending={globalSyncMutation.isPending}
            isDocTypesPending={docTypesSyncMutation.isPending}
            onSyncGlobal={() => globalSyncMutation.mutate()}
            onSyncDocTypes={() => docTypesSyncMutation.mutate()}
          />
        )}

        {/* ── Sync result / error banners ──────────────────── */}
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

        {/* ── Раздел 1: Базовые инструкции платформы ──────── */}
        <section className="space-y-3">
          <SectionHeading>Базовые инструкции платформы</SectionHeading>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <NavCard
              to="/admin/instructions/global-checks"
              title="Global Instructions"
              description="Универсальные проверки для любых документов: конфиденциальность, применимое право, срок действия и др."
              icon={Shield}
            />
            <NavCard
              to="/admin/instructions/doc-types"
              title="Doc-type Instructions"
              description="Инструкции по типам документов. Базовые настройки extraction, checks, retrieval."
              icon={FileText}
            />
          </div>
        </section>

        {/* ── Раздел 2: Playbook Studio ─────────────────────── */}
        <section className="space-y-3">
          <SectionHeading>Playbook Studio</SectionHeading>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <NavCard
              to="/admin/instructions/playbook-studio"
              title="Playbook Studio"
              description="Единая встроенная среда: templates, version builder, compiled preview, publish и дальнейшее применение в проектах."
              icon={BookOpen}
            />
          </div>
        </section>

        {/* ── Раздел 3: Реестр стандартных playbook ─────── */}
        <section className="space-y-3">
          <SectionHeading>Базовые playbooks платформы</SectionHeading>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <NavCard
              to="/admin/instructions/playbooks-registry"
              title="Реестр стандартных playbook"
              description="Опубликованные playbook, доступные пользователям в проектах. Просмотр состава и экспорт в Excel / Word."
              icon={BookOpen}
            />
          </div>
        </section>
      </div>
    </div>
  );
};

export default InstructionsIndexPage;



