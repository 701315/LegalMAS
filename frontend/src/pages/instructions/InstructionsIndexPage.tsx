// src/pages/instructions/InstructionsIndexPage.tsx

import React from "react";
import { NavLink } from "react-router-dom";
import { BookOpen, FileText, Shield } from "lucide-react";

const InstructionsIndexPage: React.FC = () => {
  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        {/* Header */}
        <div className="space-y-1">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
            Admin · Instructions
          </p>
          <h1 className="text-base font-semibold tracking-tight text-[var(--text-primary)]">
            Управление инструкциями
          </h1>
          <p className="text-xs text-[var(--text-secondary)]">
            Глобальные playbooks, universal checks и инструкции по типам документов.
            Изменения публикуются через draft → validate → publish flow.
          </p>
        </div>

        {/* Navigation cards */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">

          {/* Global Playbooks — существующий раздел */}
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

          {/* Global Instructions — новый раздел */}
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
                  Универсальные проверки для любых документов: конфиденциальность,
                  применимое право, срок действия и др.
                </div>
              </div>
            </div>
          </NavLink>

          {/* Doc-Type Instructions — существующий раздел */}
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


