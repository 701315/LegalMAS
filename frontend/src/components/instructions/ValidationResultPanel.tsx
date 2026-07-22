// src/components/instructions/ValidationResultPanel.tsx
// Показывает результат server-side валидации draft.
// Поддерживает оба типа инструкций: doc-type и global.
// checks_count опционален — у global instructions его может не быть.

import React from "react";
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react";

// ── Минимальный тип для result ────────────────────────────────
// Принимаем любой объект с is_valid, validation_report
// и опциональным checks_count.
// Это позволяет использовать компонент и с InstructionVersionValidationResponse,
// и с GlobalInstructionVersionValidationResponse без приведения типов.

interface ValidationResult {
  is_valid: boolean;
  checks_count?: number | null;
  validation_report: Record<string, unknown> | null;
}

interface ValidationResultPanelProps {
  result: ValidationResult;
}

const ValidationResultPanel: React.FC<ValidationResultPanelProps> = ({
  result,
}) => {
  const { is_valid, checks_count, validation_report } = result;

  // Извлекаем диагностики из validation_report.
  // Поддерживаем два формата:
  //
  // Doc-type format:
  //   { errors: string[], warnings: string[], error?: string }
  //
  // Global instruction format:
  //   { diagnostics: [{ level: "error"|"warning"|"info", message: string, path?: string }] }
  //
  // Оба формата сводим к errors[] и warnings[] для отображения.

  const errors: string[] = [];
  const warnings: string[] = [];

  if (validation_report && typeof validation_report === "object") {
    const report = validation_report as Record<string, unknown>;

    // ── Doc-type format ────────────────────────────────────
    if (Array.isArray(report.errors)) {
      errors.push(
        ...(report.errors as unknown[]).map((e) =>
          typeof e === "string" ? e : JSON.stringify(e),
        ),
      );
    }
    if (Array.isArray(report.warnings)) {
      warnings.push(
        ...(report.warnings as unknown[]).map((w) =>
          typeof w === "string" ? w : JSON.stringify(w),
        ),
      );
    }
    if (typeof report.error === "string") {
      errors.push(report.error);
    }

    // ── Global instruction format ──────────────────────────
    // diagnostics: [{ level: "error"|"warning"|"info", message: string }]
    if (Array.isArray(report.diagnostics)) {
      for (const d of report.diagnostics as unknown[]) {
        if (!d || typeof d !== "object") continue;
        const diagnostic = d as Record<string, unknown>;
        const level = typeof diagnostic.level === "string" ? diagnostic.level : "";
        const message =
          typeof diagnostic.message === "string"
            ? diagnostic.message
            : JSON.stringify(diagnostic);

        if (level === "error") {
          errors.push(message);
        } else if (level === "warning") {
          warnings.push(message);
        }
        // level === "info" — не показываем как ошибку/предупреждение
      }
    }
  }

  // checks_count показываем только если задан и > 0
  const showChecksCount =
    checks_count !== null && checks_count !== undefined && checks_count > 0;

  return (
    <div
      className={[
        "rounded-xl border px-4 py-3 space-y-3",
        is_valid
          ? "border-[color:var(--color-success-border)] bg-[color:var(--color-success-bg)]"
          : "border-[#dc2626]/30 bg-[#fef2f2]",
      ].join(" ")}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {is_valid ? (
            <CheckCircle
              className="h-4 w-4 shrink-0 text-[color:var(--color-success-text)]"
              aria-hidden="true"
            />
          ) : (
            <XCircle
              className="h-4 w-4 shrink-0 text-[#b91c1c]"
              aria-hidden="true"
            />
          )}
          <span
            className={[
              "text-xs font-semibold",
              is_valid
                ? "text-[color:var(--color-success-text)]"
                : "text-[#b91c1c]",
            ].join(" ")}
          >
            {is_valid ? "Валидация прошла успешно" : "Валидация не прошла"}
          </span>
        </div>

        {showChecksCount && (
          <span className="text-[11px] text-[var(--text-muted)]">
            Checks: {checks_count}
          </span>
        )}
      </div>

      {/* Errors */}
      {errors.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#b91c1c]">
            Ошибки ({errors.length})
          </div>
          <ul className="space-y-1">
            {errors.map((error, index) => (
              <li
                key={index}
                className="flex items-start gap-1.5 text-[11px] text-[#b91c1c]"
              >
                <span className="mt-0.5 shrink-0">•</span>
                <span>{error}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--color-warning-text,#92400e)]">
            Предупреждения ({warnings.length})
          </div>
          <ul className="space-y-1">
            {warnings.map((warning, index) => (
              <li
                key={index}
                className="flex items-start gap-1.5 text-[11px] text-[color:var(--color-warning-text,#92400e)]"
              >
                <AlertTriangle
                  className="mt-0.5 h-3 w-3 shrink-0"
                  aria-hidden="true"
                />
                <span>{warning}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Valid + no issues */}
      {is_valid && errors.length === 0 && warnings.length === 0 && (
        <p className="text-[11px] text-[color:var(--color-success-text)]">
          Все проверки пройдены. Черновик готов к публикации.
        </p>
      )}
    </div>
  );
};

export default ValidationResultPanel;


