// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1ExportLayoutPicker.tsx
// Inline UI для выбора layout экспорта PDF/Word (matrix mode).
// =============================================================

import React from "react";
import { AlertTriangle } from "lucide-react";
import Button from "../../../components/ui/Button";

// -------------------------------------------------------------
// Public types
// -------------------------------------------------------------

export type DDGridV1MatrixLayout = "single" | "byDocument" | "byScopeGroup";

export interface DDGridV1ExportLayoutPickerProps {
  format: "pdf" | "docx";
  onCancel: () => void;
  onApply: (layout: DDGridV1MatrixLayout) => void;
}

// -------------------------------------------------------------
// Layout catalog
// -------------------------------------------------------------

interface LayoutOption {
  id: DDGridV1MatrixLayout;
  title: string;
  description: string;
  warning?: string;
  preview: React.ReactNode;
}

const LAYOUT_OPTIONS: readonly LayoutOption[] = [
  {
    id: "single",
    title: "Единая таблица",
    description:
      "Одна большая таблица со всеми проверками и параметрами. Точное отображение матрицы как на экране.",
    warning:
      "Таблица очень широкая. Некоторые колонки могут быть плохо читаемыми в PDF/Word из-за ограничений формата страницы.",
    preview: (
      <svg viewBox="0 0 120 60" className="h-14 w-full">
        <rect
          x="2"
          y="2"
          width="116"
          height="56"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
          opacity="0.4"
        />
        <rect
          x="2"
          y="2"
          width="116"
          height="10"
          fill="currentColor"
          opacity="0.5"
        />
        {Array.from({ length: 12 }).map((_, i) => (
          <line
            key={i}
            x1={2 + i * 9.7}
            y1={2}
            x2={2 + i * 9.7}
            y2={58}
            stroke="currentColor"
            strokeWidth="0.3"
            opacity="0.3"
          />
        ))}
        {Array.from({ length: 4 }).map((_, i) => (
          <line
            key={i}
            x1={2}
            y1={12 + i * 11.5}
            x2={118}
            y2={12 + i * 11.5}
            stroke="currentColor"
            strokeWidth="0.3"
            opacity="0.3"
          />
        ))}
      </svg>
    ),
  },
  {
    id: "byDocument",
    title: "По документам (секции)",
    description:
      "Каждый документ — отдельная секция. Внутри секции — таблица его проверок в формате «Проверка / Параметр / Значение». Подходит когда документов немного, а проверок много.",
    preview: (
      <svg viewBox="0 0 120 60" className="h-14 w-full">
        <text
          x="2"
          y="8"
          fontSize="4"
          fill="currentColor"
          opacity="0.7"
          fontWeight="bold"
        >
          Документ 1
        </text>
        <rect
          x="2"
          y="10"
          width="55"
          height="16"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.6"
          opacity="0.5"
        />
        <rect
          x="2"
          y="10"
          width="55"
          height="4"
          fill="currentColor"
          opacity="0.5"
        />
        <line
          x1="20"
          y1="10"
          x2="20"
          y2="26"
          stroke="currentColor"
          strokeWidth="0.3"
          opacity="0.4"
        />
        <line
          x1="38"
          y1="10"
          x2="38"
          y2="26"
          stroke="currentColor"
          strokeWidth="0.3"
          opacity="0.4"
        />
        <line
          x1="2"
          y1="18"
          x2="57"
          y2="18"
          stroke="currentColor"
          strokeWidth="0.3"
          opacity="0.4"
        />
        <line
          x1="2"
          y1="22"
          x2="57"
          y2="22"
          stroke="currentColor"
          strokeWidth="0.3"
          opacity="0.4"
        />

        <text
          x="2"
          y="36"
          fontSize="4"
          fill="currentColor"
          opacity="0.7"
          fontWeight="bold"
        >
          Документ 2
        </text>
        <rect
          x="2"
          y="38"
          width="55"
          height="16"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.6"
          opacity="0.5"
        />
        <rect
          x="2"
          y="38"
          width="55"
          height="4"
          fill="currentColor"
          opacity="0.5"
        />
        <line
          x1="20"
          y1="38"
          x2="20"
          y2="54"
          stroke="currentColor"
          strokeWidth="0.3"
          opacity="0.4"
        />
        <line
          x1="38"
          y1="38"
          x2="38"
          y2="54"
          stroke="currentColor"
          strokeWidth="0.3"
          opacity="0.4"
        />
        <line
          x1="2"
          y1="46"
          x2="57"
          y2="46"
          stroke="currentColor"
          strokeWidth="0.3"
          opacity="0.4"
        />
        <line
          x1="2"
          y1="50"
          x2="57"
          y2="50"
          stroke="currentColor"
          strokeWidth="0.3"
          opacity="0.4"
        />

        <text
          x="65"
          y="8"
          fontSize="4"
          fill="currentColor"
          opacity="0.7"
          fontWeight="bold"
        >
          Документ 3
        </text>
        <rect
          x="65"
          y="10"
          width="53"
          height="16"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.6"
          opacity="0.5"
        />
        <rect
          x="65"
          y="10"
          width="53"
          height="4"
          fill="currentColor"
          opacity="0.5"
        />

        <text
          x="65"
          y="36"
          fontSize="4"
          fill="currentColor"
          opacity="0.7"
          fontWeight="bold"
        >
          Документ 4
        </text>
        <rect
          x="65"
          y="38"
          width="53"
          height="16"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.6"
          opacity="0.5"
        />
        <rect
          x="65"
          y="38"
          width="53"
          height="4"
          fill="currentColor"
          opacity="0.5"
        />
      </svg>
    ),
  },
  {
    id: "byScopeGroup",
    title: "По группам проверок",
    description:
      "Каждая группа проверок (например, Confidentiality, Governing Law, проверки по типу документа) — отдельная таблица. Позволяет удобно сравнить одну тему между документами.",
    preview: (
      <svg viewBox="0 0 120 60" className="h-14 w-full">
        <text
          x="2"
          y="7"
          fontSize="4"
          fill="currentColor"
          opacity="0.7"
          fontWeight="bold"
        >
          Confidentiality
        </text>
        <rect
          x="2"
          y="9"
          width="116"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.6"
          opacity="0.5"
        />
        <rect
          x="2"
          y="9"
          width="116"
          height="3"
          fill="currentColor"
          opacity="0.5"
        />
        {Array.from({ length: 6 }).map((_, i) => (
          <line
            key={i}
            x1={2 + i * 19.5}
            y1={9}
            x2={2 + i * 19.5}
            y2={23}
            stroke="currentColor"
            strokeWidth="0.3"
            opacity="0.4"
          />
        ))}

        <text
          x="2"
          y="31"
          fontSize="4"
          fill="currentColor"
          opacity="0.7"
          fontWeight="bold"
        >
          Governing Law
        </text>
        <rect
          x="2"
          y="33"
          width="116"
          height="10"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.6"
          opacity="0.5"
        />
        <rect
          x="2"
          y="33"
          width="116"
          height="3"
          fill="currentColor"
          opacity="0.5"
        />
        {Array.from({ length: 5 }).map((_, i) => (
          <line
            key={i}
            x1={2 + i * 23.4}
            y1={33}
            x2={2 + i * 23.4}
            y2={43}
            stroke="currentColor"
            strokeWidth="0.3"
            opacity="0.4"
          />
        ))}

        <text
          x="2"
          y="51"
          fontSize="4"
          fill="currentColor"
          opacity="0.7"
          fontWeight="bold"
        >
          Договор к-п
        </text>
        <rect
          x="2"
          y="53"
          width="116"
          height="5"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.6"
          opacity="0.5"
        />
        <rect
          x="2"
          y="53"
          width="116"
          height="3"
          fill="currentColor"
          opacity="0.5"
        />
      </svg>
    ),
  },
];

// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------

export const DDGridV1ExportLayoutPicker: React.FC<
  DDGridV1ExportLayoutPickerProps
> = ({ format, onCancel, onApply }) => {
  const [selected, setSelected] =
    React.useState<DDGridV1MatrixLayout>("single");

  const handleApply = () => {
    onApply(selected);
  };

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Формат экспорта в {format === "pdf" ? "PDF" : "Word"}
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
            Выберите, как структурировать данные в файле.
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={onCancel}
          >
            Отменить
          </Button>
          <Button
            type="button"
            size="sm"
            variant="primary"
            onClick={handleApply}
          >
            Экспортировать
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {LAYOUT_OPTIONS.map((option) => {
          const isSelected = selected === option.id;
          return (
            <label
              key={option.id}
              className={[
                "cursor-pointer rounded-lg border p-3 transition-colors",
                isSelected
                  ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-card)] hover:bg-[var(--bg-card-hover)]",
              ].join(" ")}
            >
              <div className="flex items-start gap-3">
                <input
                  type="radio"
                  name="matrix-layout"
                  checked={isSelected}
                  onChange={() => setSelected(option.id)}
                  className="mt-1 h-3.5 w-3.5 shrink-0 cursor-pointer text-[var(--accent-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
                />

                <div className="w-24 shrink-0 text-[var(--text-muted)]">
                  {option.preview}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold text-[var(--text-primary)]">
                    {option.title}
                  </div>
                  <p className="mt-0.5 text-[11px] leading-4 text-[var(--text-muted)]">
                    {option.description}
                  </p>
                  {option.warning && (
                    <div className="mt-1.5 flex items-start gap-1 rounded border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-1.5 py-1 text-[10px] text-[var(--color-warning-text)]">
                      <AlertTriangle
                        className="mt-0.5 h-3 w-3 shrink-0"
                        aria-hidden
                      />
                      <span>{option.warning}</span>
                    </div>
                  )}
                </div>
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
};

export default DDGridV1ExportLayoutPicker;



