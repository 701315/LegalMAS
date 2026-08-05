// =============================================================
// src/pages/tabs/overview/AnalysisActionsPanel.tsx
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import Button from "../../../components/ui/Button";
import {
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../../../utils/languageDiscovery";

interface AnalysisActionsPanelProps {
  deal: Deal;
  hasCurrentRun: boolean;
  canStartRun: boolean;
  onOpenRunPanel: () => void;
  showReclassBanner: boolean;
}

const AnalysisActionsPanel: React.FC<AnalysisActionsPanelProps> = ({
  deal,
  hasCurrentRun,
  canStartRun,
  onOpenRunPanel,
  showReclassBanner,
}) => {
  const hasPlaybook = !!deal.playbook_version_id;
  const documentLanguages = Array.from(
    new Set(
      (deal.languages ?? [])
        .map((lang) => normalizeLang(lang))
        .filter(Boolean),
    ),
  );

  const discoveryStatus = normalizeDiscoveryStatus(
    deal.language_discovery_status,
  );
  const primaryLanguage = normalizeLang(deal.primary_language);
  const primaryLanguageSelected = !!primaryLanguage;

  const readinessText = canStartRun
    ? hasCurrentRun
      ? "Можно перезапустить анализ с текущими настройками или сначала изменить их."
      : "Проект готов к первому запуску."
    : !hasPlaybook
      ? "Сначала выберите playbook проекта."
      : !primaryLanguageSelected
        ? "Нужно выбрать основной язык анализа."
        : documentLanguages.length === 0 && discoveryStatus === "processing"
          ? "Языки документов ещё определяются."
          : hasCurrentRun
            ? "Проверьте настройки перед перезапуском."
            : "Проверьте настройки перед запуском.";

  const panelTitle = hasCurrentRun ? "Перезапуск анализа" : "Запуск анализа";
  const panelDescription = hasCurrentRun
    ? "Запустите анализ заново, чтобы обновить результаты проекта."
    : "Настройте параметры и запустите первый анализ документов по проекту.";

  const buttonLabel = hasCurrentRun
    ? "Настроить перезапуск"
    : "Настроить запуск";

  return (
    <aside
      className="self-start rounded-2xl bg-[var(--bg-card)] xl:sticky xl:top-0"
      style={{
        border: "1px solid var(--border)",
        boxShadow:
          "inset 0 0 0 1px var(--accent-primary), var(--shadow-sm)",
      }}
    >
      <div className="flex flex-col gap-4 p-5">
        {/* Заголовок */}
        <div>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            Действия
          </h2>
          <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
            {panelTitle}
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--text-muted)]">
            {panelDescription}
          </p>
        </div>

        {/* Блок "Когда нужен перезапуск" */}
        {hasCurrentRun && (
          <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-3">
            <p className="text-xs font-semibold text-[var(--text-secondary)]">
              Когда нужен перезапуск
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-[var(--text-muted)]">
              <li>Если вы хотите загрузить и проверить новые документы</li>
              <li>Если вы хотите проверить документы по новому playbook или профилю модели</li>
              <li>После ручной переклассификации документов</li>
            </ul>
          </div>
        )}

        {/* Баннер про ручную переклассификацию */}
        {showReclassBanner && (
          <div className="rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-3">
            <p className="text-xs font-semibold text-[var(--color-warning-text)]">
              Обновите результаты
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--color-warning-text)]">
              Вы изменили типы документов вручную. Рекомендуем перезапустить
              анализ, чтобы обновить результаты проекта.
            </p>
          </div>
        )}

        {/* Блок "Готовность к перезапуску" */}
        <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {hasCurrentRun ? "Готовность к перезапуску" : "Готовность к запуску"}
          </p>
          <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
            {readinessText}
          </p>
        </div>

        {/* Кнопка */}
        <div>
          <Button
            variant="secondary"
            size="sm"
            onClick={onOpenRunPanel}
          >
            {buttonLabel}
          </Button>
        </div>
      </div>
    </aside>
  );
};

export default AnalysisActionsPanel;


