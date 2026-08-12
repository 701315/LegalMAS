// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1ViewSettings.tsx
// Панель настроек отображения DD Grid V1.
//
// Содержит три независимых toggle:
// - Формат представления данных     (matrix / list)
// - Отображение результатов проверок (all / global_only / doc_type_only)
// - Группировка документов           (all_docs / by_type)
//
// Правила:
// - каждый toggle имеет свою подпись сверху;
// - "Группировка документов" скрывается когда format = list (Q23 = C);
// - все state читаются/пишутся через useDDGridV1UIStore.
// =============================================================

import React from "react";
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
  /**
   * Полный лейбл для десктопа (натуральная ширина сегментов).
   * Может быть многословным и описательным ("Только по типу документа").
   */
  label: string;
  /**
   * Опциональный короткий лейбл для мобильных viewport
   * (когда ToggleGroup рендерится в stretch-режиме с равными
   * долями по 100% ширины). Гарантирует, что даже на самом узком
   * мобильном экране (~320px) все сегменты умещаются в одну строку
   * без переноса текста внутри кнопки.
   *
   * Если не задан — используется полный label.
   *
   * Полное описание всегда остаётся доступным через title (tooltip)
   * и aria-label, поэтому семантика сохраняется для UX и a11y.
   */
  shortLabel?: string;
  title: string;
}

const FORMAT_OPTIONS: readonly ToggleOption<DDGridV1GridFormat>[] = [
  {
    value: "matrix",
    label: "Матрица",
    title: "Табличное представление документов и проверок",
  },
  {
    value: "list",
    label: "Список",
    title: "Плоский список findings",
  },
] as const;

const CHECKS_SCOPE_OPTIONS: readonly ToggleOption<DDGridV1ChecksScope>[] = [
  {
    value: "all",
    label: "Все проверки",
    shortLabel: "Все",
    title: "Показывать global и doc-type проверки",
  },
  {
    value: "global_only",
    label: "Только глобальные",
    shortLabel: "Глобальные",
    title: "Только global playbook проверки",
  },
  {
    value: "doc_type_only",
    label: "Только по типу документа",
    shortLabel: "По типу",
    title: "Только проверки, специфичные для типа документа",
  },
] as const;

const DOC_GROUPING_OPTIONS: readonly ToggleOption<DDGridV1DocGrouping>[] = [
  {
    value: "all_docs",
    label: "Все документы",
    title: "Все документы в одной таблице",
  },
  {
    value: "by_type",
    label: "По типам документов",
    title: "Отдельная таблица на каждый тип документа",
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
  // Desktop (stretch=false): натуральный padding px-3, лейблы —
  // полная форма ("Только по типу документа") в inline-flex.
  //
  // Mobile (stretch=true): компактный padding px-2, block-режим
  // для корректного centering в grid-доле, text-center. Лейблы
  // при этом уже короткие ("По типу") из shortLabel — переносов
  // текста не возникает.
  //
  // whitespace-nowrap — защита на случай, если у какого-то option
  // shortLabel не задан (fallback на label): даже длинный label
  // не будет ломаться на 2 строки.
  // truncate — safety net для экстремально узких viewport или
  // будущих option с длинными short-лейблами: overflow скрывается
  // с ellipsis вместо wrap.
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
  /**
   * Режим полной ширины: контейнер сегментов растягивается на 100%
   * родителя, а сами сегменты распределяются равными долями через
   * grid. Кнопки получают компактный padding (px-2) и text-center,
   * чтобы длинные лейблы (например "Только по типу документа")
   * лучше умещались.
   */
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
  // ─────────────────────────────────────────────────────────────
  // Универсальное поведение сегментов на всех viewport:
  //
  // Desktop (stretch=false):
  //   - inline-flex по натуральной ширине;
  //   - полные лейблы (label);
  //   - привычный компактный сегментированный контрол.
  //
  // Mobile (stretch=true):
  //   - grid с равными долями (grid-cols-N), w-full;
  //   - короткие лейблы (shortLabel) с fallback на label;
  //   - гарантированно 1 строка по высоте на любом мобильном экране
  //     от 320px (iPhone SE) и шире, потому что короткие лейблы
  //     ("Все", "Глобальные", "По типу") заведомо помещаются
  //     в долю ~90-100px.
  //
  // Полное описание всегда доступно через title (tooltip) и
  // aria-label — семантика не теряется при сокращении лейбла.
  // ─────────────────────────────────────────────────────────────

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
          const displayLabel =
            stretch && option.shortLabel ? option.shortLabel : option.label;
          return (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={value === option.value}
              aria-label={option.label}
              title={option.title}
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
  /**
   * Скрывает переключатель "Формат представления данных" (Матрица/Список)
   * и вместо него показывает информационный баннер о принудительном
   * использовании режима "Список".
   *
   * Используется на мобильных viewport (< lg), где матричное
   * представление нечитаемо из-за горизонтальной плотности данных,
   * и родительский компонент (DDGridV1TabPage) принудительно
   * фиксирует gridMode = "list" независимо от значения format в store.
   */
  hideFormatToggle?: boolean;

  /**
   * Режим полной ширины: все секции (info-баннер, каждый ToggleGroup)
   * занимают 100% ширины родителя, вертикальный стек. Сегменты внутри
   * ToggleGroup распределяются равными долями (grid, не inline-flex).
   *
   * Предназначен для мобильных viewport, где горизонтальный wrap
   * inline-flex сегментов приводит к переносу длинных лейблов и
   * визуальному беспорядку.
   */
  stretch?: boolean;
}

export const DDGridV1ViewSettings: React.FC<DDGridV1ViewSettingsProps> = ({
  hideFormatToggle = false,
  stretch = false,
}) => {
  const format = useDDGridV1UIStore((state) => state.format);
  const setFormat = useDDGridV1UIStore((state) => state.setFormat);

  const checksScope = useDDGridV1UIStore((state) => state.checksScope);
  const setChecksScope = useDDGridV1UIStore((state) => state.setChecksScope);

  const docGrouping = useDDGridV1UIStore((state) => state.docGrouping);
  const setDocGrouping = useDDGridV1UIStore((state) => state.setDocGrouping);

  // Q23 = C: группировка скрывается когда format = list.
  // При hideFormatToggle=true эффективный формат — "list", поэтому
  // группировка скрывается автоматически.
  const showGrouping = !hideFormatToggle && format === "matrix";

  const rootClassName = stretch
    ? "flex flex-col gap-4"
    : "flex flex-wrap items-start gap-6";

  return (
    <div className={rootClassName}>
      {hideFormatToggle ? (
        <FormatUnavailableNotice stretch={stretch} />
      ) : (
        <ToggleGroup
          label="Формат представления данных"
          ariaLabel="Формат представления данных"
          value={format}
          options={FORMAT_OPTIONS}
          onChange={setFormat}
          stretch={stretch}
        />
      )}

      <ToggleGroup
        label="Отображение результатов проверок"
        ariaLabel="Отображение результатов проверок"
        value={checksScope}
        options={CHECKS_SCOPE_OPTIONS}
        onChange={setChecksScope}
        stretch={stretch}
      />

      {showGrouping ? (
        <ToggleGroup
          label="Группировка документов"
          ariaLabel="Группировка документов"
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
 * Информационный баннер о принудительном использовании представления "Список"
 * на узких viewport. Занимает место переключателя "Формат представления данных".
 *
 * При stretch=true растягивается на всю ширину родителя.
 */
const FormatUnavailableNotice: React.FC<{ stretch?: boolean }> = ({
  stretch = false,
}) => (
  <div className={`flex min-w-0 flex-col gap-1.5 ${stretch ? "w-full" : ""}`}>
    <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
      Формат представления данных
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
      <span>
        Матричное представление доступно только на широких экранах. На этом
        устройстве данные отображаются в виде списка.
      </span>
    </div>
  </div>
);

export default DDGridV1ViewSettings;



