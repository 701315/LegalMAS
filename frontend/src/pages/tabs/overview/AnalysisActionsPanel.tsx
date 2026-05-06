// =============================================================
// src/pages/tabs/overview/AnalysisActionsPanel.tsx
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import Button from "../../../components/ui/Button";
import { StatusRow } from "./shared";

interface AnalysisActionsPanelProps {
  deal: Deal;
  latestRunExists: boolean;
  canStartRun: boolean;
  onOpenRunPanel: () => void;
  showReclassBanner: boolean;
}

const AnalysisActionsPanel: React.FC<AnalysisActionsPanelProps> = ({
  deal,
  latestRunExists,
  canStartRun,
  onOpenRunPanel,
  showReclassBanner,
}) => {
  const hasPlaybook = !!deal.playbook_version_id;
  const documentLanguages = deal.languages ?? [];
  const hasMultipleDocumentLanguages = documentLanguages.length > 1;
  const primaryLanguageSelected = !!deal.primary_language;

  return (
    <aside className="self-start rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm xl:sticky xl:top-0">
      <div className="flex h-full flex-col px-5 py-5">
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Действия
          </p>
          <h3 className="text-base font-semibold text-[var(--text-primary)]">
            Анализ документов
          </h3>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            {!latestRunExists
              ? "Настройте параметры и запустите первый анализ документов по проекту."
              : "Вы можете запустить повторный анализ, чтобы обновить результаты."}
          </p>
        </div>

        {showReclassBanner && (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
            <p className="text-xs font-semibold text-amber-900">
              Требуется обновление результатов
            </p>
            <p className="mt-1 text-xs leading-5 text-amber-800">
              После ручной переклассификации рекомендуется повторно запустить
              анализ.
            </p>
          </div>
        )}

        <div className="mt-5 rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Текущая готовность
          </p>

          <div className="mt-3 space-y-2">
            <StatusRow
              label="Playbook проекта"
              value={hasPlaybook ? "Выбран" : "Не выбран"}
              tone={hasPlaybook ? "ok" : "warn"}
            />
            <StatusRow
              label="Языки документов"
              value={
                documentLanguages.length > 0
                  ? documentLanguages.join(", ")
                  : "Ещё не определены"
              }
              tone={documentLanguages.length > 0 ? "ok" : "neutral"}
            />
            <StatusRow
              label="Основной язык анализа"
              value={
                deal.primary_language
                  ? deal.primary_language
                  : hasMultipleDocumentLanguages
                    ? "Нужно выбрать перед запуском"
                    : "Будет определён автоматически"
              }
              tone={
                primaryLanguageSelected
                  ? "ok"
                  : hasMultipleDocumentLanguages
                    ? "warn"
                    : "neutral"
              }
            />
            <StatusRow
              label="Профиль модели"
              value={deal.model_config_name || "Профиль проекта / playbook"}
              tone={deal.model_config_name ? "ok" : "neutral"}
            />
          </div>
        </div>

        <div className="mt-5">
          <Button
            variant="secondary"
            size="sm"
            onClick={onOpenRunPanel}
            disabled={!canStartRun}
          >
            Запустить анализ документов
          </Button>
        </div>
      </div>
    </aside>
  );
};

export default AnalysisActionsPanel;





