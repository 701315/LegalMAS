// =============================================================
// src/pages/tabs/overview/AnalysisActionsPanel.tsx
// Header приведён к стандарту Overview:
// - "Действия" — основной заголовок
// - "Анализ документов" — подзаголовок
// - divider inset, не примыкает к краям карточки
// - внешний блок акцентирован синим обрамлением по всей границе,
//   при этом сохранена стандартная системная тень карточки
//
// Актуальный контракт:
// - hasCurrentRun отражает наличие current run,
//   определяемого через deal.last_run_id / currentRunId наверху.
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import Button from "../../../components/ui/Button";
import { StatusRow } from "./shared";
import {
  formatLangLabel,
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

  const documentLanguagesValue =
    documentLanguages.length > 0
      ? documentLanguages.map(formatLangLabel).join(", ")
      : discoveryStatus === "processing"
        ? "Определяются…"
        : discoveryStatus === "failed"
          ? "Не удалось определить"
          : discoveryStatus === "partial"
            ? "Определены частично"
            : "Ещё не определены";

  const documentLanguagesTone =
    documentLanguages.length > 0
      ? "ok"
      : discoveryStatus === "failed"
        ? "warn"
        : "neutral";

  const primaryLanguageValue = primaryLanguageSelected
    ? formatLangLabel(primaryLanguage)
    : "Не выбран";

  const primaryLanguageTone = primaryLanguageSelected ? "ok" : "warn";

  const readinessText = canStartRun
    ? "Проект готов к запуску анализа."
    : !hasPlaybook
      ? "Сначала выберите playbook проекта."
      : !primaryLanguageSelected
        ? "Перед запуском нужно выбрать основной язык анализа."
        : documentLanguages.length === 0 && discoveryStatus === "processing"
          ? "Языки документов ещё определяются."
          : "Перед запуском проверьте параметры анализа в панели запуска.";

  return (
    <aside
      className="self-start rounded-2xl bg-[var(--bg-card)] xl:sticky xl:top-0"
      style={{
        border: "1px solid var(--border)",
        boxShadow: "inset 0 0 0 1px var(--accent-primary), var(--shadow-sm)",
      }}
    >
      <div className="flex h-full flex-col">
        <div className="px-5">
          <div className="py-4">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              Действия
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Анализ документов
            </p>
            <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
              {!hasCurrentRun
                ? "Настройте параметры и запустите первый анализ документов по проекту."
                : "Вы можете запустить повторный анализ, чтобы обновить результаты."}
            </p>
          </div>

          <div className="border-t border-[var(--border-subtle)]" />
        </div>

        <div className="px-5 py-5">
          {showReclassBanner && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
              <p className="text-xs font-semibold text-amber-900">
                Требуется обновление результатов
              </p>
              <p className="mt-1 text-xs leading-5 text-amber-800">
                После ручной переклассификации рекомендуется повторно запустить
                анализ.
              </p>
            </div>
          )}

          <div
            className={`rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-4 ${
              showReclassBanner ? "mt-4" : ""
            }`}
          >
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
                value={documentLanguagesValue}
                tone={documentLanguagesTone}
              />

              <StatusRow
                label="Основной язык анализа"
                value={primaryLanguageValue}
                tone={primaryLanguageTone}
              />

              <StatusRow
                label="Профиль модели"
                value={deal.model_config_name || "Профиль проекта / playbook"}
                tone={deal.model_config_name ? "ok" : "neutral"}
              />
            </div>
          </div>

          <div className="mt-4 rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Статус запуска
            </p>
            <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
              {readinessText}
            </p>
          </div>

          <div className="mt-5">
            <Button
              variant="secondary"
              size="sm"
              onClick={onOpenRunPanel}
              disabled={!canStartRun}
            >
              Выбрать настройки для анализа документов
            </Button>
          </div>
        </div>
      </div>
    </aside>
  );
};

export default AnalysisActionsPanel;




