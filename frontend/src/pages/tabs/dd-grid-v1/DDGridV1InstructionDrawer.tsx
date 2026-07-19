// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1InstructionDrawer.tsx
// Side-panel drawer со списком проверок doc_type, зафиксированных
// в снапшоте Run. Без собственного fetch: данные приходят как пропсы
// из уже загруженной DDGridV1DerivedModel.
// =============================================================

import React from "react";
import { X } from "lucide-react";
import type {
  DDGridV1InstructionSnapshotDTO,
  DDGridV1CheckSummaryDTO,
} from "../../../types/dealReview";

interface CheckGroupSectionProps {
  title: string;
  hint?: string;
  accentClassName: string;
  checks: DDGridV1CheckSummaryDTO[];
  defaultOpen?: boolean;
}

const CheckGroupSection: React.FC<CheckGroupSectionProps> = ({
  title,
  hint,
  accentClassName,
  checks,
  defaultOpen = true,
}) => {
  const [open, setOpen] = React.useState(defaultOpen);

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[var(--border)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left hover:bg-[var(--bg-hover)]"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border border-[var(--border)] text-[11px] font-bold leading-none text-[var(--text-secondary)]">
            {open ? "−" : "+"}
          </span>
          <h4 className="text-xs font-bold uppercase tracking-wide text-[var(--text-secondary)]">
            {title}
          </h4>
          <span className="rounded-full bg-[var(--bg-muted)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--text-faint)]">
            {checks.length}
          </span>
        </div>
        {hint ? (
          <span className="truncate text-[11px] text-[var(--text-faint)]">
            {hint}
          </span>
        ) : null}
      </button>

      {open ? (
        <ul className="flex flex-col gap-2 px-3 pb-3">
          {checks.map((check) => (
            <li
              key={check.id || check.name}
              className={`rounded-lg border border-[var(--border)] bg-[var(--bg-muted)] p-3 border-l-[3px] ${accentClassName}`}
            >
              <div className="text-sm font-semibold text-[var(--text-primary)]">
                {check.name}
              </div>
              {check.description ? (
                <div className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                  {check.description}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};

export interface DDGridV1InstructionDrawerProps {
  open: boolean;
  onClose: () => void;
  documentName: string | null;
  snapshot: DDGridV1InstructionSnapshotDTO | null;
}

export const DDGridV1InstructionDrawer: React.FC<
  DDGridV1InstructionDrawerProps
> = ({ open, onClose, documentName, snapshot }) => {
  React.useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    // СТАЛО
    <aside className="flex h-full w-full flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-[var(--border)] px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Инструкция проверки
          </h3>
          <div className="mt-0.5 text-xs text-[var(--text-muted)]">
            {documentName ?? "—"}
            {snapshot?.doc_type ? ` · ${snapshot.doc_type}` : ""}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
          aria-label="Закрыть"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
        {!snapshot ? (
          <div className="text-sm text-[var(--text-faint)]">
            Тип документа не классифицирован — инструкция не применялась.
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2">
              {snapshot.is_persisted_snapshot ? (
                <span className="inline-flex items-center rounded-full border border-emerald-500/40 bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-900 dark:border-emerald-700/60 dark:bg-emerald-900/40 dark:text-emerald-100">
                  Зафиксирована в момент запуска Run
                </span>
              ) : (
                <span className="inline-flex items-center rounded-full border border-amber-500/40 bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-900 dark:border-amber-700/60 dark:bg-amber-900/40 dark:text-amber-100">
                  Legacy Run — версия не зафиксирована
                </span>
              )}
              {snapshot.version_id ? (
                <span className="font-mono text-[11px] text-[var(--text-faint)]">
                  {snapshot.version_id}
                </span>
              ) : null}
            </div>

            {snapshot.global_checks.length === 0 &&
            snapshot.doc_type_checks.length === 0 ? (
              <div className="text-sm text-[var(--text-faint)]">
                Список проверок недоступен для этого doc_type.
              </div>
            ) : (
              <>
                {snapshot.global_checks.length > 0 && (
                  <CheckGroupSection
                    title="Глобальные проверки"
                    hint="Применяются ко всем документам сделки"
                    accentClassName="border-l-sky-500"
                    checks={snapshot.global_checks}
                    defaultOpen
                  />
                )}
                {snapshot.doc_type_checks.length > 0 && (
                  <CheckGroupSection
                    title="Проверки типа документа"
                    hint={snapshot.doc_type}
                    accentClassName="border-l-violet-500"
                    checks={snapshot.doc_type_checks}
                    defaultOpen
                  />
                )}
              </>
            )}
          </>
        )}
      </div>
    </aside>
  );
};

export default DDGridV1InstructionDrawer;


