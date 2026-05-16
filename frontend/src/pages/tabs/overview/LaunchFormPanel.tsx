// =============================================================
// src/pages/tabs/overview/LaunchFormPanel.tsx
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import type { ChecksMode } from "../OverviewTab";
import Button from "../../../components/ui/Button";
import {
  formatLangLabel,
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../../../utils/languageDiscovery";

const SECONDARY_ACTION_BUTTON_CLASS = "w-[220px] shrink-0 justify-center";

interface LaunchFormPanelProps {
  deal: Deal;
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

type BannerTone = "info" | "warning" | "error" | "success";

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
  tone: BannerTone;
  text: string;
} | null {
  if (status === "pending") {
    return {
      tone: "info",
      text: "Система подготавливает анализ всех загруженных документов для определения языков. До завершения этого этапа выбор основного языка сделки и режима проверки недоступен.",
    };
  }

  if (status === "processing") {
    return {
      tone: "info",
      text: "Система анализирует все загруженные документы и определяет языки, которые в них используются. Пока этот этап не завершён по всем файлам, выбор основного языка сделки и режима проверки недоступен.",
    };
  }

  if (status === "failed") {
    return {
      tone: "error",
      text: "Автоопределение языков завершилось ошибкой. Проверьте документы или повторите подготовку перед запуском анализа.",
    };
  }

  if (status === "partial") {
    return {
      tone: "warning",
      text: "Определение языков завершено частично: часть документов не прошла language discovery. Вы можете продолжить настройку, но рекомендуется проверить проблемные файлы.",
    };
  }

  if (status === "completed" && hasLanguages) {
    return {
      tone: "success",
      text: "Определение языков завершено. Теперь выберите основной язык сделки, после этого станет доступен режим проверки.",
    };
  }

  return null;
}

function getBannerClassName(tone: BannerTone): string {
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

function getPrimaryLanguageHelperText(params: {
  isDiscoveryInProgress: boolean;
  discoveryStatus: string | null;
  hasLanguages: boolean;
  primaryLanguageSelected: boolean;
}): string {
  const {
    isDiscoveryInProgress,
    discoveryStatus,
    hasLanguages,
    primaryLanguageSelected,
  } = params;

  if (isDiscoveryInProgress) {
    return "Основной язык сделки можно будет выбрать только после завершения анализа всех загруженных файлов.";
  }

  if (!hasLanguages && discoveryStatus === "failed") {
    return "Список языков недоступен, потому что автоопределение завершилось ошибкой.";
  }

  if (!hasLanguages && discoveryStatus === "partial") {
    return "Языки определены не по всем документам. Проверьте проблемные файлы или повторите подготовку.";
  }

  if (!hasLanguages) {
    return "Языки документов ещё недоступны. После завершения подготовки вы сможете выбрать основной язык сделки.";
  }

  if (!primaryLanguageSelected) {
    return "Выберите основной язык сделки. После этого станет доступен режим проверки.";
  }

  return "Основной язык выбран. Теперь можно выбрать режим проверки.";
}

function getChecksModeHelperText(params: {
  documentsCountLoaded: boolean;
  hasDocuments: boolean;
  hasPlaybook: boolean;
  isDiscoveryInProgress: boolean;
  primaryLanguageSelected: boolean;
}): string {
  const {
    documentsCountLoaded,
    hasDocuments,
    hasPlaybook,
    isDiscoveryInProgress,
    primaryLanguageSelected,
  } = params;

  if (!documentsCountLoaded) {
    return "Дождитесь загрузки информации о документах проекта.";
  }

  if (!hasDocuments) {
    return "Сначала загрузите документы в проект.";
  }

  if (!hasPlaybook) {
    return "Сначала выберите playbook проекта.";
  }

  if (isDiscoveryInProgress) {
    return "Система анализирует все загруженные документы и определяет языки, которые в них используются. Режим проверки станет доступен после завершения этого этапа по всем файлам.";
  }

  if (!primaryLanguageSelected) {
    return "Сначала выберите основной язык сделки, затем станет доступен режим проверки.";
  }

  return "Выберите набор проверок для запуска анализа.";
}

const LaunchFormPanel: React.FC<LaunchFormPanelProps> = ({
  deal,
  documentsCount,
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  canUploadDocuments,
  isSubmitting,
  onOpenPlaybook,
  onOpenModelConfig,
  onOpenUpload,
  onPrimaryLanguageChange,
}) => {
  const normalizedDocumentLanguages = React.useMemo(
    () =>
      Array.from(
        new Set(
          (deal.languages ?? [])
            .map((lang) => normalizeLang(lang))
            .filter(Boolean),
        ),
      ),
    [deal.languages],
  );

  const selectedPrimaryLanguage = normalizeLang(deal.primary_language);
  const discoveryStatus = normalizeDiscoveryStatus(
    deal.language_discovery_status,
  );

  const documentsCountLoaded = typeof documentsCount === "number";
  const hasDocuments = documentsCountLoaded ? documentsCount > 0 : false;
  const hasPlaybook = !!deal.playbook_version_id;
  const hasLanguages = normalizedDocumentLanguages.length > 0;
  const primaryLanguageSelected = !!selectedPrimaryLanguage;
  const isDiscoveryInProgress =
    discoveryStatus === "pending" || discoveryStatus === "processing";

  const canSelectPrimaryLanguage =
    hasLanguages &&
    !isSubmitting &&
    !isDiscoveryInProgress;

  const canSelectChecksMode =
    documentsCountLoaded &&
    hasDocuments &&
    hasPlaybook &&
    !isSubmitting &&
    !isDiscoveryInProgress &&
    primaryLanguageSelected;

  const discoveryBanner = React.useMemo(
    () => getDiscoveryBanner(discoveryStatus, hasLanguages),
    [discoveryStatus, hasLanguages],
  );

  const autoDetectedLanguagesText = React.useMemo(
    () =>
      normalizedDocumentLanguages
        .map((lang) => formatLangLabel(lang))
        .join(", "),
    [normalizedDocumentLanguages],
  );

  const primaryLanguageHelperText = React.useMemo(
    () =>
      getPrimaryLanguageHelperText({
        isDiscoveryInProgress,
        discoveryStatus,
        hasLanguages,
        primaryLanguageSelected,
      }),
    [
      isDiscoveryInProgress,
      discoveryStatus,
      hasLanguages,
      primaryLanguageSelected,
    ],
  );

  const checksModeHelperText = React.useMemo(
    () =>
      getChecksModeHelperText({
        documentsCountLoaded,
        hasDocuments,
        hasPlaybook,
        isDiscoveryInProgress,
        primaryLanguageSelected,
      }),
    [
      documentsCountLoaded,
      hasDocuments,
      hasPlaybook,
      isDiscoveryInProgress,
      primaryLanguageSelected,
    ],
  );

  const handleLanguageSelect = React.useCallback(
    (lang: string) => {
      const normalized = normalizeLang(lang);

      if (!normalized || isSubmitting || !canSelectPrimaryLanguage) {
        return;
      }

      if (selectedPrimaryLanguage === normalized) {
        return;
      }

      onPrimaryLanguageChange(normalized);
    },
    [
      canSelectPrimaryLanguage,
      isSubmitting,
      onPrimaryLanguageChange,
      selectedPrimaryLanguage,
    ],
  );

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
                  {documentsCountLoaded
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

            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              Сначала система должна определить языки во всех загруженных
              документах. Только после этого можно выбрать основной язык сделки.
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

            <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
              {primaryLanguageHelperText}
            </p>

            {hasLanguages ? (
              <>
                <div className="mt-3 space-y-2">
                  {normalizedDocumentLanguages.map((lang) => {
                    const checked = selectedPrimaryLanguage === lang;
                    const disabled = !canSelectPrimaryLanguage;

                    return (
                      <label
                        key={lang}
                        className={`flex items-start gap-3 rounded-xl border px-3 py-3 transition ${
                          checked
                            ? "border-[var(--accent-primary)] bg-[var(--bg-elevated-soft)]"
                            : "border-[var(--border-subtle)] bg-[var(--bg-card)]"
                        } ${
                          disabled
                            ? "cursor-not-allowed opacity-70"
                            : "cursor-pointer hover:bg-[var(--bg-elevated-soft)]"
                        }`}
                        aria-disabled={disabled}
                      >
                        <input
                          type="radio"
                          name="primary_language"
                          className="mt-[2px]"
                          value={lang}
                          checked={checked}
                          onChange={() => handleLanguageSelect(lang)}
                          disabled={disabled}
                        />

                        <span>
                          <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                            {formatLangLabel(lang)}
                          </span>
                          <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                            {formatLangHint(lang)}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>

                {!primaryLanguageSelected && !isDiscoveryInProgress && (
                  <p className="mt-3 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-subtle)] px-3 py-2 text-[11px] leading-5 text-[var(--color-warning)]">
                    Перед запуском анализа выберите основной язык сделки.
                  </p>
                )}

                <p className="mt-2 text-xs text-[var(--text-secondary)]">
                  Автоопределённые языки документов: {autoDetectedLanguagesText}.
                </p>
              </>
            ) : (
              <p className="mt-3 text-xs text-[var(--text-secondary)]">
                {discoveryStatus === "failed"
                  ? "Список языков пока недоступен, потому что автоопределение завершилось ошибкой."
                  : "Языки документов ещё не определены автоматически. После завершения обработки всех файлов вы сможете выбрать основной язык сделки."}
              </p>
            )}
          </section>

          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-base)] p-4">
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">
              Режим проверки
            </h4>

            <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
              {checksModeHelperText}
            </p>

            <div className="mt-3 space-y-2">
              {CHECKS_MODE_OPTIONS.map(({ value, title, hint }) => {
                const checked = checksMode === value;
                const disabled = !canSelectChecksMode;

                return (
                  <label
                    key={value}
                    className={`flex items-start gap-3 rounded-xl border px-3 py-3 transition ${
                      checked
                        ? "border-[var(--accent-primary)] bg-[var(--bg-elevated-soft)]"
                        : "border-[var(--border-subtle)] bg-[var(--bg-card)]"
                    } ${
                      disabled
                        ? "cursor-not-allowed opacity-70"
                        : "cursor-pointer hover:bg-[var(--bg-elevated-soft)]"
                    }`}
                    aria-disabled={disabled}
                  >
                    <input
                      type="radio"
                      className="mt-[2px]"
                      value={value}
                      checked={checked}
                      onChange={() => onChecksModeChange(value)}
                      disabled={disabled}
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
                );
              })}
            </div>
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




