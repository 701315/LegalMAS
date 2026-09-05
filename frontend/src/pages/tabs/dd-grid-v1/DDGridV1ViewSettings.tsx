// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1ViewSettings.tsx
// View settings panel for DD Grid V1.
//
// Contains three independent toggles:
// - Data presentation format    (matrix / list)
// - Checks scope display        (all / global_only / doc_type_only)
// - Document grouping           (all_docs / by_type)
//
// Rules:
// - each toggle has its own header label;
// - "Document grouping" is hidden when format = list (Q23 = C);
// - all state is read/written via useDDGridV1UIStore.
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

import {
  useDDGridV1UIStore,
  type DDGridV1ChecksScope,
  type DDGridV1DocGrouping,
  type DDGridV1GridFormat,
} from "./ddGridV1.collapseStore";

// -------------------------------------------------------------
// Toggle option types
// -------------------------------------------------------------

interface ToggleOption<T extends string> {
  value: T;
  labelKey: string;
  shortLabelKey?: string;
  titleKey: string;
}

const FORMAT_OPTIONS: readonly ToggleOption<DDGridV1GridFormat>[] = [
  {
    value: "matrix",
    labelKey: "viewSettings.format.matrix.label",
    titleKey: "viewSettings.format.matrix.title",
  },
  {
    value: "list",
    labelKey: "viewSettings.format.list.label",
    titleKey: "viewSettings.format.list.title",
  },
] as const;

const CHECKS_SCOPE_OPTIONS: readonly ToggleOption<DDGridV1ChecksScope>[] = [
  {
    value: "all",
    labelKey: "viewSettings.checksScope.all.label",
    shortLabelKey: "viewSettings.checksScope.all.shortLabel",
    titleKey: "viewSettings.checksScope.all.title",
  },
  {
    value: "global_only",
    labelKey: "viewSettings.checksScope.global_only.label",
    shortLabelKey: "viewSettings.checksScope.global_only.shortLabel",
    titleKey: "viewSettings.checksScope.global_only.title",
  },
  {
    value: "doc_type_only",
    labelKey: "viewSettings.checksScope.doc_type_only.label",
    shortLabelKey: "viewSettings.checksScope.doc_type_only.shortLabel",
    titleKey: "viewSettings.checksScope.doc_type_only.title",
  },
] as const;

const DOC_GROUPING_OPTIONS: readonly ToggleOption<DDGridV1DocGrouping>[] = [
  {
    value: "all_docs",
    labelKey: "viewSettings.docGrouping.all_docs.label",
    titleKey: "viewSettings.docGrouping.all_docs.title",
  },
  {
    value: "by_type",
    labelKey: "viewSettings.docGrouping.by_type.label",
    titleKey: "viewSettings.docGrouping.by_type.title",
  },
] as const;

// -------------------------------------------------------------
// Toggle button visual
// -------------------------------------------------------------

function getTabClassName<T extends string>(
  current: T,
  value: T,
  stretch = false,
): string {
  const layoutClass = stretch
    ? "block w-full truncate whitespace-nowrap rounded-lg px-2 py-1.5 text-center text-xs font-medium"
    : "whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium";

  return current === value
    ? `${layoutClass} bg-[var(--bg-card)] text-[var(--text-primary)] shadow-sm`
    : `${layoutClass} text-[var(--text-muted)] hover:text-[var(--text-primary)]`;
}

interface ToggleGroupProps<T extends string> {
  label: string;
  ariaLabel: string;
  value: T;
  options: readonly ToggleOption<T>[];
  onChange: (value: T) => void;
  stretch?: boolean;
}

function ToggleGroup<T extends string>({
  label,
  ariaLabel,
  value,
  options,
  onChange,
  stretch = false,
}: ToggleGroupProps<T>) {
  const { t } = useTranslation("ddGrid");

  const containerClassName = stretch
    ? "grid w-full rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-1"
    : "inline-flex items-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-1";

  const containerStyle = stretch
    ? { gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }
    : undefined;

  return (
    <div className={`flex flex-col gap-1.5 ${stretch ? "w-full min-w-0" : ""}`}>
      <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </span>
      <div
        className={containerClassName}
        style={containerStyle}
        role="tablist"
        aria-label={ariaLabel}
      >
        {options.map((option) => {
          const rawLabel = t(option.labelKey);
          const rawTitle = t(option.titleKey);
          
          const displayLabel =
            stretch && option.shortLabelKey ? t(option.shortLabelKey) : rawLabel;
            
          return (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={value === option.value}
              aria-label={rawLabel}
              title={rawTitle}
              onClick={() => onChange(option.value)}
              className={getTabClassName(value, option.value, stretch)}
            >
              {displayLabel}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------

interface DDGridV1ViewSettingsProps {
  hideFormatToggle?: boolean;
  stretch?: boolean;
}

export const DDGridV1ViewSettings: React.FC<DDGridV1ViewSettingsProps> = ({
  hideFormatToggle = false,
  stretch = false,
}) => {
  const { t } = useTranslation("ddGrid");

  const format = useDDGridV1UIStore((state) => state.format);
  const setFormat = useDDGridV1UIStore((state) => state.setFormat);

  const checksScope = useDDGridV1UIStore((state) => state.checksScope);
  const setChecksScope = useDDGridV1UIStore((state) => state.setChecksScope);

  const docGrouping = useDDGridV1UIStore((state) => state.docGrouping);
  const setDocGrouping = useDDGridV1UIStore((state) => state.setDocGrouping);

  const showGrouping = !hideFormatToggle && format === "matrix";

  const rootClassName = stretch
    ? "flex flex-col gap-4"
    : "flex flex-wrap items-center gap-6";

  return (
    <div className={rootClassName}>
      {hideFormatToggle ? (
        <FormatUnavailableNotice stretch={stretch} />
      ) : (
        <ToggleGroup
          label={t("viewSettings.formatLabel")}
          ariaLabel={t("viewSettings.formatLabel")}
          value={format}
          options={FORMAT_OPTIONS}
          onChange={setFormat}
          stretch={stretch}
        />
      )}

      <ToggleGroup
        label={t("viewSettings.checksScopeLabel")}
        ariaLabel={t("viewSettings.checksScopeLabel")}
        value={checksScope}
        options={CHECKS_SCOPE_OPTIONS}
        onChange={setChecksScope}
        stretch={stretch}
      />

      {showGrouping ? (
        <ToggleGroup
          label={t("viewSettings.docGroupingLabel")}
          ariaLabel={t("viewSettings.docGroupingLabel")}
          value={docGrouping}
          options={DOC_GROUPING_OPTIONS}
          onChange={setDocGrouping}
          stretch={stretch}
        />
      ) : null}
    </div>
  );
};

/**
 * Informational notice banner indicating that "List" format is forced
 * on narrow viewports. Takes the place of the "Data presentation format" toggle.
 */
const FormatUnavailableNotice: React.FC<{ stretch?: boolean }> = ({
  stretch = false,
}) => {
  const { t } = useTranslation("ddGrid");

  return (
    <div className={`flex min-w-0 flex-col gap-1.5 ${stretch ? "w-full" : ""}`}>
      <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {t("viewSettings.formatLabel")}
      </span>
      <div
        role="note"
        className={`flex items-start gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-[11px] leading-[1.35] text-[var(--text-secondary)] ${
          stretch ? "w-full" : ""
        }`}
      >
        <Info
          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]"
          aria-hidden
        />
        <span>{t("viewSettings.notice")}</span>
      </div>
    </div>
  );
};

export default DDGridV1ViewSettings;

