// =============================================================
// src/pages/tabs/grid/gridTab.sections.tsx
// =============================================================

import React from "react";

import type { CheckResult } from "../../../types";

import ExportButtons from "../../../components/grid/ExportButtons";
import Button from "../../../components/ui/Button";

import { INLINE_PANEL_ACTIVE_CLASS } from "./gridTab.constants";
import type { GridScope } from "./gridTab.types";
import { toExportChecksMode } from "./gridTab.utils";

export function SectionCard({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="px-6 pt-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              {title}
            </h2>
            {description ? (
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                {description}
              </p>
            ) : null}
          </div>

          {actions ? (
            <div className="flex flex-wrap items-center gap-2">{actions}</div>
          ) : null}
        </div>

        <div className="mt-4 border-t border-[var(--border-subtle)]" />
      </div>

      <div className="px-6 py-5">
        {children}
      </div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "critical" | "accent";
}) {
  const valueClass =
    tone === "critical"
      ? "text-[var(--color-error)]"
      : tone === "accent"
        ? "text-[var(--accent-primary)]"
        : "text-[var(--text-primary)]";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
        {label}
      </div>
      <div className={`mt-2 text-lg font-semibold tracking-tight ${valueClass}`}>
        {value}
      </div>
    </div>
  );
}

export function ExportStatCard({
  allResults,
  selectedResults,
  dealId,
  runId,
  runChecksMode,
  runPipelineStrategy,
}: {
  allResults: CheckResult[];
  selectedResults: CheckResult[];
  dealId: string;
  runId?: string;
  runChecksMode?: string | null;
  runPipelineStrategy?: string | null;
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
        Экспорт результатов
      </div>

      <div className="mt-3">
        <ExportButtons
          allResults={allResults}
          selectedResults={selectedResults}
          dealName={dealId}
          runId={runId}
          runChecksMode={toExportChecksMode(runChecksMode)}
          runPipelineStrategy={runPipelineStrategy ?? undefined}
        />
      </div>
    </div>
  );
}

export const ScopeInlinePanel: React.FC<{
  gridScope: GridScope;
  setGridScope: (value: GridScope) => void;
  scopeDoctypes: string[];
  selectedScopeDocTypes: string[];
  toggleScopeDocType: (docType: string) => void;
  resetScopeDocTypes: () => void;
  onClose: () => void;
}> = ({
  gridScope,
  setGridScope,
  scopeDoctypes,
  selectedScopeDocTypes,
  toggleScopeDocType,
  resetScopeDocTypes,
  onClose,
}) => (
  <div className="mt-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)]">
    <div className="border-b border-[var(--border-subtle)] px-4 py-3">
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        Область проверок
      </p>
      <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
        Выберите, какие результаты показывать в DD Grid
      </p>
    </div>

    <div className="space-y-4 px-4 py-4">
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant={gridScope === "all" ? "outline" : "secondary"}
          onClick={() => setGridScope("all")}
          className={gridScope === "all" ? INLINE_PANEL_ACTIVE_CLASS : ""}
        >
          Все
        </Button>

        <Button
          type="button"
          size="sm"
          variant={gridScope === "global" ? "outline" : "secondary"}
          onClick={() => setGridScope("global")}
          className={gridScope === "global" ? INLINE_PANEL_ACTIVE_CLASS : ""}
        >
          Глобальный плейбук
        </Button>

        <Button
          type="button"
          size="sm"
          variant={gridScope === "doctype" ? "outline" : "secondary"}
          onClick={() => setGridScope("doctype")}
          className={gridScope === "doctype" ? INLINE_PANEL_ACTIVE_CLASS : ""}
        >
          По типу документа
        </Button>
      </div>

      {gridScope === "doctype" && scopeDoctypes.length > 0 ? (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-4 py-3">
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Типы документов
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant={selectedScopeDocTypes.length === 0 ? "outline" : "ghost"}
              onClick={resetScopeDocTypes}
              className={
                selectedScopeDocTypes.length === 0
                  ? INLINE_PANEL_ACTIVE_CLASS
                  : ""
              }
            >
              Все типы
            </Button>

            {scopeDoctypes.map((dt) => {
              const checked = selectedScopeDocTypes.includes(dt);

              return (
                <Button
                  key={dt}
                  type="button"
                  size="sm"
                  variant={checked ? "outline" : "secondary"}
                  onClick={() => toggleScopeDocType(dt)}
                  aria-pressed={checked}
                  className={checked ? INLINE_PANEL_ACTIVE_CLASS : ""}
                >
                  {dt}
                </Button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>

    <div className="flex items-center justify-between gap-2 border-t border-[var(--border-subtle)] px-4 py-3">
      <Button size="sm" variant="ghost" onClick={resetScopeDocTypes}>
        Сбросить типы
      </Button>

      <div className="flex gap-2">
        <Button size="sm" variant="secondary" onClick={onClose}>
          Закрыть
        </Button>
      </div>
    </div>
  </div>
);


