// =============================================================
// src/components/new-project/Block5Language.tsx
//
// Блок 5 — Выбор основного языка анализа.
//
// Показывает:
//   - статус language discovery (pending / processing / completed / failed / partial)
//   - список автоопределённых языков
//   - radio-выбор основного языка
//
// Использует утилиты из utils/languageDiscovery и
// хук useSetPrimaryLanguage для PATCH.
//
// Логика discovery/language переиспользована из LaunchFormPanel,
// но реализована как самостоятельный блок — LaunchFormPanel
// не трогаем.
// =============================================================

import React from "react";
import { Globe, Loader2 } from "lucide-react";

import { useSetPrimaryLanguage } from "../../api/deals";
import {
  formatLangLabel,
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../../utils/languageDiscovery";

import InlineAlert from "../InlineAlert";

import type { DealLanguageDiscoveryStatus } from "../../types";

interface Block5LanguageProps {
  dealId: string;
  /** Список автоопределённых языков из deal.languages */
  languages: string[];
  /** Текущий primary_language из deal */
  primaryLanguage: string | null;
  /** Статус language discovery из deal */
  discoveryStatus: DealLanguageDiscoveryStatus | string | null;
  /** Вызывается после успешного выбора языка (для summary) */
  onLanguageSet: (lang: string, label: string) => void;
}

// ── Banner types ────────────────────────────────────────────

type BannerTone = "info" | "warning" | "error" | "success";

interface DiscoveryBanner {
  tone: BannerTone;
  text: string;
}

function getDiscoveryBanner(
  status: string | null,
  hasLanguages: boolean,
): DiscoveryBanner | null {
  if (status === "pending") {
    return {
      tone: "info",
      text: "Система подготавливает анализ загруженных документов для определения языков. Выбор основного языка станет доступен после завершения этого этапа.",
    };
  }

  if (status === "processing") {
    return {
      tone: "info",
      text: "Система анализирует документы и определяет языки. Выбор основного языка станет доступен после завершения по всем файлам.",
    };
  }

  if (status === "failed") {
    return {
      tone: "error",
      text: "Автоопределение языков завершилось ошибкой. Проверьте документы или повторите загрузку.",
    };
  }

  if (status === "partial") {
    return {
      tone: "warning",
      text: "Определение языков завершено частично: часть документов не прошла обработку. Вы можете продолжить, но рекомендуется проверить проблемные файлы.",
    };
  }

  if (status === "completed" && hasLanguages) {
    return {
      tone: "success",
      text: "Определение языков завершено. Выберите основной язык анализа.",
    };
  }

  return null;
}

function getBannerClassName(tone: BannerTone): string {
  if (tone === "error") {
    return "border border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]";
  }

  if (tone === "warning") {
    return "border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]";
  }

  if (tone === "success") {
    return "border border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]";
  }

  return "border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]";
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

// ── Component ───────────────────────────────────────────────

const Block5Language: React.FC<Block5LanguageProps> = ({
  dealId,
  languages,
  primaryLanguage,
  discoveryStatus: rawDiscoveryStatus,
  onLanguageSet,
}) => {

  // === DEBUG: временный лог для отладки ===
  React.useEffect(() => {
    console.log("[Block5Language DEBUG]", {
      dealId,
      languages,
      primaryLanguage,
      discoveryStatus: rawDiscoveryStatus,
      languages_type: typeof languages,
      languages_isArray: Array.isArray(languages),
      languages_length: languages?.length,
    });
  }, [dealId, languages, primaryLanguage, rawDiscoveryStatus]);
  // === END DEBUG ===

  const setPrimaryLanguage = useSetPrimaryLanguage(dealId);

  const [optimisticLang, setOptimisticLang] = React.useState<string | null>(
    null,
  );
  const [errorText, setErrorText] = React.useState<string | null>(null);

  // ── Derived ───────────────────────────────────────────────
  const discoveryStatus = normalizeDiscoveryStatus(rawDiscoveryStatus);

  const normalizedLanguages = React.useMemo(
    () =>
      Array.from(
        new Set(
          languages
            .map((lang) => normalizeLang(lang))
            .filter(Boolean),
        ),
      ),
    [languages],
  );

  const normalizedPrimaryLanguage = normalizeLang(primaryLanguage);

  const selectedLang =
    optimisticLang ?? (normalizedPrimaryLanguage || null);

  const hasLanguages = normalizedLanguages.length > 0;

  const isDiscoveryInProgress =
    discoveryStatus === "pending" || discoveryStatus === "processing";

  const isSubmitting = setPrimaryLanguage.isPending;

  const canSelect =
    hasLanguages && !isSubmitting && !isDiscoveryInProgress;

  const discoveryBanner = React.useMemo(
    () => getDiscoveryBanner(discoveryStatus, hasLanguages),
    [discoveryStatus, hasLanguages],
  );

  const autoDetectedText = React.useMemo(
    () => normalizedLanguages.map((l) => formatLangLabel(l)).join(", "),
    [normalizedLanguages],
  );

  // ── Sync optimistic with real value ───────────────────────
  React.useEffect(() => {
    if (!setPrimaryLanguage.isPending) {
      setOptimisticLang(null);
    }
  }, [setPrimaryLanguage.isPending]);

  // ── Handler ───────────────────────────────────────────────
  const handleSelectLanguage = React.useCallback(
    (lang: string) => {
      const normalized = normalizeLang(lang);

      if (!normalized || !canSelect) return;
      if (selectedLang === normalized) return;

      setOptimisticLang(normalized);
      setErrorText(null);

      setPrimaryLanguage.mutate(
        { primary_language: normalized },
        {
          onSuccess: () => {
            const label = formatLangLabel(normalized);
            onLanguageSet(normalized, label);
          },
          onError: () => {
            setOptimisticLang(null);
            setErrorText(
              "Не удалось установить основной язык. Попробуйте ещё раз.",
            );
          },
        },
      );
    },
    [canSelect, onLanguageSet, selectedLang, setPrimaryLanguage],
  );

  // ── Discovery in progress — waiting state ─────────────────
  if (isDiscoveryInProgress && !hasLanguages) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-4">
          <Loader2
            className="h-4 w-4 animate-spin text-[var(--accent-primary)]"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-sm text-[var(--text-primary)]">
              Определяем языки документов…
            </p>
            <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
              Выбор основного языка станет доступен после завершения анализа
              всех файлов.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ── No languages at all ───────────────────────────────────
  if (!hasLanguages && !isDiscoveryInProgress) {
    return (
      <div className="space-y-4">
        {discoveryBanner ? (
          <p
            className={`rounded-xl px-3 py-2 text-[11px] leading-5 ${getBannerClassName(discoveryBanner.tone)}`}
          >
            {discoveryBanner.text}
          </p>
        ) : null}

        <div className="subtle-panel px-4 py-6 text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
            <Globe className="h-5 w-5 text-[var(--text-muted)]" />
          </div>
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Языки документов ещё не определены
          </p>
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
            {discoveryStatus === "failed"
              ? "Автоопределение завершилось ошибкой. Проверьте документы или загрузите новые."
              : "После завершения обработки всех файлов здесь появится список языков."}
          </p>
        </div>
      </div>
    );
  }

  // ── Main content — language selection ─────────────────────
  return (
    <div className="space-y-4">
      {errorText ? <InlineAlert tone="error" message={errorText} /> : null}

      {/* Discovery banner */}
      {discoveryBanner ? (
        <p
          className={`rounded-xl px-3 py-2 text-[11px] leading-5 ${getBannerClassName(discoveryBanner.tone)}`}
        >
          {discoveryBanner.text}
        </p>
      ) : null}

      {/* Language radios */}
      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          Основной язык анализа
        </p>

        <div className="space-y-2">
          {normalizedLanguages.map((lang) => {
            const isChecked = selectedLang === lang;
            const disabled = !canSelect;

            return (
              <label
                key={lang}
                className={[
                  "flex items-start gap-3 rounded-xl border px-3 py-3 transition",
                  isChecked
                    ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
                    : "border-[var(--border-subtle)] bg-[var(--bg-card)]",
                  disabled
                    ? "cursor-not-allowed opacity-70"
                    : "cursor-pointer hover:bg-[var(--bg-elevated-soft)]",
                ]
                  .filter(Boolean)
                  .join(" ")}
                aria-disabled={disabled}
              >
                <input
                  type="radio"
                  name="new_project_primary_language"
                  className="mt-[2px]"
                  value={lang}
                  checked={isChecked}
                  onChange={() => handleSelectLanguage(lang)}
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
      </div>

      {/* Auto-detected info */}
      <p className="text-[11px] text-[var(--text-muted)]">
        Автоопределённые языки документов: {autoDetectedText}.
      </p>

      {/* Warning if not selected */}
      {!selectedLang && !isDiscoveryInProgress ? (
        <p className="rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2 text-[11px] leading-5 text-[var(--color-warning-text)]">
          Перед запуском анализа необходимо выбрать основной язык.
        </p>
      ) : null}

      {/* Submitting indicator */}
      {isSubmitting ? (
        <div className="flex items-center gap-2">
          <Loader2
            className="h-3.5 w-3.5 animate-spin text-[var(--accent-primary)]"
            aria-hidden="true"
          />
          <span className="text-[11px] text-[var(--text-muted)]">
            Сохраняем выбор…
          </span>
        </div>
      ) : null}
    </div>
  );
};

export default Block5Language;


