// =============================================================
// src/pages/tabs/overview/LaunchFormPanel.tsx
// =============================================================

import React from "react";
import type { Deal, DealLanguageDiscoveryStatus } from "../../../types";
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

function normalizeLang(value: string | null | undefined): string {
  return String(value ?? "").trim().toUpperCase();
}

function normalizeDiscoveryStatus(
  value: string | null | undefined,
): DealLanguageDiscoveryStatus | string | null {
  const normalized = String(value ?? "").trim().toLowerCase();
  return normalized || null;
}

function formatLangCode(value: string | null | undefined): string {
  const v = String(value ?? "").trim().toUpperCase();
  return v || "";
}

function formatLangTitle(value: string): string {
  const normalized = normalizeLang(value);
  if (normalized === "RU") return "Русский";
  if (normalized === "EN") return "English";
  return formatLangCode(normalized);
}

function formatLangHint(value: string): string {
  const normalized = normalizeLang(value);
  if (normalized === "RU") {
    return "Primary source и проверки будут ориентированы на русский язык.";
  }
  if (normalized === "EN") {
    return "Primary source и проверки будут ориентированы на английский язык.";
  }
  return "Выберите этот язык как основной для анализа.";
}

function getDiscoveryBanner(
  status: string | null,
  hasLanguages: boolean,
): {
  tone: "info" | "warning" | "error" | "success";
  text: string;
} | null {
  if (status === "processing") {
    return {
      tone: "info",
      text: "Языки документов ещё определяются автоматически. Список языков может обновиться.",
    };
  }

  if (status === "failed") {
    return {
      tone: "error",
      text: "Автоопределение языков завершилось ошибкой. Проверьте документы или повторите подготовку.",
    };
  }

  if (status === "partial") {
    return {
      tone: "warning",
      text: "Языки определены частично: часть документов могла не пройти language discovery.",
    };
  }

  if (status === "completed" && hasLanguages) {
    return {
      tone: "success",
      text: "Языки документов определены. Выберите основной язык анализа.",
    };
  }

  return null;
}

function getBannerClassName(tone: "info" | "warning" | "error" | "success"): string {
  if (tone === "error") {
    return "border border-[var(--color-error-border)] bg-[var(--color-error-subtle)] text-[var(--color-error)]";
  }
  if (tone === "warning") {
    return "border border-[var(--color-warning-border)] bg-[var(--color-warning-subtle)] text-[var(--color-warning)]";
  }
  if (tone === "success") {
    return "border border-[var(--color-success-border)] bg-[var(--color-success-subtle)] text-[var(--color-success)]";
  }
  return "border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]";
}

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
  const rawDocumentLanguages = deal.languages ?? [];
  const normalizedDocumentLanguages = Array.from(
    new Set(rawDocumentLanguages.map((l) => normalizeLang(l)).filter(Boolean)),
  );

  const selectedPrimaryLanguage = normalizeLang(deal.primary_language ?? "");
  const discoveryStatus = normalizeDiscoveryStatus(deal.language_discovery_status);
  const discoveryBanner = getDiscoveryBanner(
    typeof discoveryStatus === "string" ? discoveryStatus : null,
    normalizedDocumentLanguages.length > 0,
  );

  const hasPlaybook = !!deal.playbook_version_id;
  const hasLanguages = normalizedDocumentLanguages.length > 0;
  const canSelectPrimaryLanguage = hasLanguages && !isSubmitting;

  const handleLanguageSelect = (lang: string) => {
    const normalized = normalizeLang(lang);
    if (!normalized || isSubmitting) return;
    if (selectedPrimaryLanguage === normalized) return;
    onPrimaryLanguageChange(normalized);
  };

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
                <span className="text-[var(--text-secondary)]">Playbook выбран.</span>
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

            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              Выберите основной язык, на котором будет строиться primary source и
              выполняться анализ.
            </p>

            {discoveryBanner ? (
              <p
                className={`mt-3 rounded-xl px-3 py-2 text-[11px] leading-5 ${getBannerClassName(
                  discoveryBanner.tone,
                )}`}
              >
                {discoveryBanner.text}
              </p>
            ) : null}

            {hasLanguages ? (
              <>
                <div className="mt-3 space-y-2">
                  {normalizedDocumentLanguages.map((lang) => {
                    const checked = selectedPrimaryLanguage === lang;

                    return (
                      <label
                        key={lang}
                        className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-3 transition ${
                          checked
                            ? "border-[var(--accent-primary)] bg-[var(--bg-elevated-soft)]"
                            : "border-[var(--border-subtle)] bg-[var(--bg-card)] hover:bg-[var(--bg-elevated-soft)]"
                        } ${!canSelectPrimaryLanguage ? "opacity-70" : ""}`}
                      >
                        <input
                          type="radio"
                          name="primary_language"
                          className="mt-[2px]"
                          value={lang}
                          checked={checked}
                          onChange={() => handleLanguageSelect(lang)}
                          disabled={!canSelectPrimaryLanguage}
                        />

                        <span>
                          <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                            {formatLangTitle(lang)} ({formatLangCode(lang)})
                          </span>
                          <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                            {formatLangHint(lang)}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>

                {!selectedPrimaryLanguage && (
                  <p className="mt-3 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-subtle)] px-3 py-2 text-[11px] leading-5 text-[var(--color-warning)]">
                    Перед запуском анализа выберите основной язык анализа.
                  </p>
                )}

                <p className="mt-2 text-xs text-[var(--text-secondary)]">
                  Автоопределённые языки документов:{" "}
                  {normalizedDocumentLanguages
                    .map((l) => `${formatLangTitle(l)} (${formatLangCode(l)})`)
                    .join(", ")}
                  .
                </p>
              </>
            ) : (
              <>
                <p className="mt-3 text-xs text-[var(--text-secondary)]">
                  {discoveryStatus === "failed"
                    ? "Список языков пока недоступен, потому что автоопределение завершилось ошибкой."
                    : "Языки документов ещё не определены автоматически. После завершения подготовки языков вы сможете выбрать основной язык."}
                </p>

                {!selectedPrimaryLanguage && (
                  <p className="mt-2 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-subtle)] px-3 py-2 text-[11px] leading-5 text-[var(--color-warning)]">
                    Основной язык ещё не выбран. Выберите его, когда языки документов будут готовы.
                  </p>
                )}
              </>
            )}
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




