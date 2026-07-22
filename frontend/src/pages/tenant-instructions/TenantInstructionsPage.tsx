// src/pages/tenant-instructions/TenantInstructionsPage.tsx

import React from "react";
import { useNavigate } from "react-router-dom";
import { GitBranch } from "lucide-react";
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

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
      </div>
    </div>
  );
};

export default TenantInstructionsPage;


