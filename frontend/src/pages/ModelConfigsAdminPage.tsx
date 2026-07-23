// =============================================================
// src/pages/ModelConfigsAdminPage.tsx
// Админ-страница для управления профилями моделей (ModelConfig).
// =============================================================

import React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import ModelConfigManagerPanel from "../components/model-config/ModelConfigManagerPanel";

const ModelConfigsAdminPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const dealIdFromQuery = searchParams.get("dealId");

  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-6">
        {/* ── Back-link ────────────────────────────────────── */}
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="flex shrink-0 items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Назад
        </button>

        {/* ── Header ───────────────────────────────────────── */}
        <header>
          <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
            Конфигурации моделей
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Управление профилями моделей для playbook-версий и проектов.
          </p>
        </header>

        {/* ── Panel ────────────────────────────────────────── */}
        <ModelConfigManagerPanel
          mode="page"
          dealId={dealIdFromQuery}
          onFinished={() => {
            if (dealIdFromQuery) {
              navigate(-1);
            }
          }}
        />
      </div>
    </div>
  );
};

export default ModelConfigsAdminPage;