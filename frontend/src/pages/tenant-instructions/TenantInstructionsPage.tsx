// src/pages/tenant-instructions/TenantInstructionsPage.tsx

import React from "react";
import { useNavigate } from "react-router-dom";
import { BookOpen, GitBranch, Shield } from "lucide-react";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";

const TenantInstructionsPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-full bg-[var(--bg-base)] px-4 py-6">
      <div className="mx-auto max-w-4xl space-y-4">
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Tenant Admin", to: "/tenant-admin" },
            { label: "Инструкции" },
          ]}
          title="Инструкции клиента"
          subtitle="Управление override-инструкциями для вашего tenant."
        />

        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-xs text-[var(--text-secondary)]">
          Рекомендуемый workflow: откройте{" "}
          <span className="font-semibold text-[var(--text-primary)]">Playbook Studio</span>,
          изучите базовые global checks и доступные templates, затем откройте
          редактор версий и после этого примените нужную версию в проекте через
          вкладку <span className="font-semibold text-[var(--text-primary)]">Playbook</span>.
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <button
            type="button"
            onClick={() => navigate("/tenant-admin/instructions/base-global-checks")}
            className="block rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 text-left transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
                <Shield
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              </div>
              <div>
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  Base Global Checks
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Read-only каталог базовых глобальных проверок платформы.
                </div>
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={() => navigate("/tenant-admin/instructions/playbook-studio")}
            className="block rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 text-left transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
                <BookOpen
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              </div>
              <div>
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  Playbook Studio
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Единая встроенная среда: templates, version builder, compiled preview и подготовка версий для проектов tenant.
                </div>
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={() => navigate("/tenant-admin/instructions/overrides")}
            className="block rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 text-left transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
                <GitBranch
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              </div>
              <div>
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  Tenant Overrides
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Переопределения базовых инструкций для вашего tenant.
                </div>
              </div>
            </div>
          </button>
        </div>

        <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-card)] px-4 py-4">
          <div className="text-sm font-semibold text-[var(--text-primary)]">
            Doc-Type Base Instructions
          </div>
          <div className="mt-1 text-xs text-[var(--text-secondary)]">
            Каталог базовых doc-type instructions пока централизован и не вынесен
            в отдельный tenant-safe read facade. Мы не показываем tenant_admin
            superadmin-only данные через обходные маршруты.
          </div>

          <button
            type="button"
            onClick={() => navigate("/tenant-admin/instructions/playbook-versions")}
            className="block rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 text-left transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
                <BookOpen
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              </div>
              <div>
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  Playbook Versions
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Сборка и управление версиями playbooks для использования в проектах.
                </div>
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={() => navigate("/dashboard")}
            className="block rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 text-left transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
                <BookOpen
                  className="h-4 w-4 text-[var(--accent-primary)]"
                  aria-hidden="true"
                />
              </div>
              <div>
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  Playbook проекта
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Для выбора и применения playbook откройте нужный проект и перейдите во вкладку Playbook.
                </div>
              </div>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
};

export default TenantInstructionsPage;


