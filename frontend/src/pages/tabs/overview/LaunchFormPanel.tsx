// =============================================================
// src/pages/tabs/overview/LaunchFormPanel.tsx
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import type { ChecksMode } from "../OverviewTab";
import Button from "../../../components/ui/Button";

const SECONDARY_ACTION_BUTTON_CLASS = "w-[220px] shrink-0 justify-center";

interface LaunchFormPanelProps {
  deal: Deal;
  latestRunId?: string | null;
  documentsCount?: number;
  checksMode: ChecksMode;
  onChecksModeChange: (value: ChecksMode) => void;
  forceReclassify: boolean;
  onForceReclassifyChange: (value: boolean) => void;
  canStartRun: boolean;
  canUploadDocuments: boolean;
  isSubmitting: boolean;
  onOpenPlaybook: () => void;
  onOpenModelConfig?: () => void;
  onOpenUpload: () => void;
  onPrimaryLanguageChange: (value: string) => void;
}

const LANGUAGE_LABELS: Record<string, string> = {
  ru: "Русский",
  rus: "Русский",
  en: "English",
  eng: "English",
  de: "Deutsch",
  deu: "Deutsch",
  ger: "Deutsch",
  fr: "Français",
  fra: "Français",
  fre: "Français",
  es: "Español",
  spa: "Español",
  it: "Italiano",
  ita: "Italiano",
  tr: "Türkçe",
  tur: "Türkçe",
  ar: "العربية",
  ara: "العربية",
  chi: "中文",
  ja: "日本語",
  jpn: "日本語",
};

function formatLanguageCode(language: string): string {
  return String(language).trim().toUpperCase();
}

function formatLanguageName(language: string): string {
  const normalized = String(language).trim().toLowerCase();
  return LANGUAGE_LABELS[normalized] ?? formatLanguageCode(language);
}

const CHECKS_MODE_OPTIONS: Array<{
  value: ChecksMode;
  title: string;
  hint: string;
}> = [
  {
    value: "global_and_doc_type",
    title: "Playbook и типы документов",
    hint: "Рекомендуемый режим.",
  },
  {
    value: "global_only",
    title: "Только Playbook",
    hint: "Только правила playbook.",
  },
  {
    value: "doc_type_only",
    title: "Только типы документов",
    hint: "Только проверки по типам документов.",
  },
];

const LaunchFormPanel: React.FC<LaunchFormPanelProps> = ({
  deal,
  documentsCount,
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  canStartRun,
  canUploadDocuments,
  isSubmitting,
  onOpenPlaybook,
  onOpenModelConfig,
  onOpenUpload,
  onPrimaryLanguageChange,
}) => {
  const documentLanguages = deal.languages ?? [];
  const selectedPrimaryLanguage = deal.primary_language ?? "";
  const hasPlaybook = !!deal.playbook_version_id;

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--bg-card)]">
      <div className="border-b border-[var(--border-subtle)] px-5 py-4">
        <h3 className="text-base font-semibold text-[var(--text-primary)]">
          Запуск анализа
        </h3>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Проверьте параметры анализа для этой сделки.
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <div className="space-y-3">
          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  Документы
                </h4>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  {typeof documentsCount === "number"
                    ? `В проект загружено ${documentsCount} документ(ов).`
                    : "Загружаем информацию о документах…"}
                </p>
              </div>

              <Button
                variant="secondary"
                size="sm"
                onClick={onOpenUpload}
                disabled={!canUploadDocuments}
                className={SECONDARY_ACTION_BUTTON_CLASS}
              >
                Загрузить новые документы
              </Button>
            </div>
          </section>

          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">
              Режим проверки
            </h4>

            <div className="mt-3 space-y-2">
              {CHECKS_MODE_OPTIONS.map(({ value, title, hint }) => (
                <label
                  key={value}
                  className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-3 transition ${
                    checksMode === value
                      ? "border-[var(--accent-primary)] bg-[var(--bg-elevated-soft)]"
                      : "border-[var(--border-subtle)] bg-[var(--bg-card)] hover:bg-[var(--bg-elevated-soft)]"
                  }`}
                >
                  <input
                    type="radio"
                    className="mt-[2px]"
                    value={value}
                    checked={checksMode === value}
                    onChange={() => onChecksModeChange(value)}
                    disabled={isSubmitting || !canStartRun}
                  />

                  <span>
                    <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                      {title}
                    </span>
                    <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                      {hint}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  Playbook проекта
                </h4>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  Используется для формирования проверок и DD Grid.
                </p>
              </div>

              <Button
                variant="secondary"
                size="sm"
                onClick={onOpenPlaybook}
                className={SECONDARY_ACTION_BUTTON_CLASS}
              >
                Выбрать Playbook
              </Button>
            </div>

            <p className="mt-3 text-xs leading-5">
              {hasPlaybook ? (
                <span className="text-[var(--text-secondary)]">
                  Playbook выбран.
                </span>
              ) : (
                <span className="text-[var(--color-error)]">
                  Playbook не выбран. Нельзя запустить анализ без playbook.
                </span>
              )}
            </p>
          </section>

          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  Профиль модели
                </h4>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  Настройка профиля модели.
                </p>
              </div>

              {onOpenModelConfig ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={onOpenModelConfig}
                  className={SECONDARY_ACTION_BUTTON_CLASS}
                >
                  Настроить профиль модели
                </Button>
              ) : null}
            </div>

            <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
              {deal.model_config_name
                ? `Текущий профиль (используется в проекте по умолчанию): ${deal.model_config_name}.`
                : "Будет использован профиль проекта или playbook."}
            </p>
          </section>

          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">
              Основной язык анализа
            </h4>

            {documentLanguages.length === 0 ? (
              <p className="mt-2 text-xs text-[var(--text-secondary)]">
                Языки документов ещё не определены. После загрузки и анализа
                документов основной язык будет выбран автоматически.
              </p>
            ) : null}

            {documentLanguages.length === 1 ? (
              <p className="mt-2 text-xs text-[var(--text-secondary)]">
                Обнаружен единственный язык документов:{" "}
                <span className="font-medium text-[var(--text-primary)]">
                  {formatLanguageName(documentLanguages[0])}
                </span>{" "}
                <span className="text-[var(--text-muted)]">
                  ({formatLanguageCode(documentLanguages[0])})
                </span>
                . Основной язык будет определён автоматически.
              </p>
            ) : null}

            {documentLanguages.length > 1 ? (
              <>
                <p className="mt-2 text-xs text-[var(--text-secondary)]">
                  В документах проекта обнаружено несколько языков. Выберите, на
                  каком языке считать анализ основным.
                </p>

                <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {documentLanguages.map((lang) => {
                    const checked = selectedPrimaryLanguage === lang;

                    return (
                      <label
                        key={lang}
                        className={[
                          "flex cursor-pointer items-center gap-3 rounded-2xl border px-3 py-2 text-xs transition",
                          checked
                            ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
                            : "border-[var(--border)] bg-[var(--bg-card)] hover:bg-[var(--bg-elevated-soft)]",
                        ].join(" ")}
                      >
                        <input
                          type="radio"
                          name="primary_language"
                          value={lang}
                          checked={checked}
                          onChange={() => onPrimaryLanguageChange(lang)}
                          disabled={isSubmitting}
                          className="h-4 w-4 shrink-0 accent-[var(--accent-primary)]"
                        />

                        <div className="min-w-0">
                          <div className="text-[11px] font-semibold text-[var(--text-primary)]">
                            {formatLanguageCode(lang)}
                          </div>
                          <div className="text-[11px] text-[var(--text-muted)]">
                            {formatLanguageName(lang)}
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>

                {!selectedPrimaryLanguage ? (
                  <p className="mt-3 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-subtle)] px-3 py-2 text-[11px] leading-5 text-[var(--color-warning)]">
                    В сделке есть документы на нескольких языках. Перед запуском
                    анализа выберите основной язык.
                  </p>
                ) : null}
              </>
            ) : null}

            {documentLanguages.length > 0 ? (
              <p className="mt-2 text-xs text-[var(--text-secondary)]">
                Языки документов:{" "}
                {documentLanguages
                  .map(
                    (lang) =>
                      `${formatLanguageName(lang)} (${formatLanguageCode(lang)})`,
                  )
                  .join(", ")}
              </p>
            ) : null}
          </section>

          {deal.has_pending_manual_reclassifications ? (
            <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                Дополнительные параметры
              </h4>

              <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-3 text-xs text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  className="mt-[2px]"
                  checked={forceReclassify}
                  onChange={(e) => onForceReclassifyChange(e.target.checked)}
                  disabled={isSubmitting}
                />

                <span>
                  <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                    Принудительно переклассифицировать документы
                  </span>
                  <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                    Используйте после ручной переклассификации.
                  </span>
                </span>
              </label>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default LaunchFormPanel;


