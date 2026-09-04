// =============================================================
// src/components/new-project/Block6Launch.tsx
//
// Блок 6 — Режим проверки + кнопка «Запустить проект».
//
// Содержит:
//   - описание двух видов проверок
//   - radio-выбор режима проверки (3 варианта)
//   - checkbox force reclassify (если применимо)
//   - кнопка «Запустить проект»
//
// Не содержит API-логики — все callbacks передаются сверху.
// =============================================================

import React from "react";
import { Rocket } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { RunChecksMode } from "../../types";

import Button from "../ui/Button";
import InlineAlert from "../InlineAlert";

interface Block6LaunchProps {
  checksMode: RunChecksMode;
  onChecksModeChange: (value: RunChecksMode) => void;
  forceReclassify: boolean;
  onForceReclassifyChange: (value: boolean) => void;
  /** Показывать ли опцию force reclassify */
  showForceReclassify: boolean;
  /** Все обязательные условия для запуска выполнены */
  canLaunch: boolean;
  isSubmitting: boolean;
  errorText?: string | null;
  onLaunch: () => void;
}

const CHECKS_MODE_KEYS: Array<{
  value: RunChecksMode;
  titleKey: string;
  hintKey: string;
  badgeKey?: string;
}> = [
  {
    value: "global_and_doc_type",
    titleKey: "newProject.block6.modes.global_and_doc_type.title",
    hintKey: "newProject.block6.modes.global_and_doc_type.hint",
    badgeKey: "newProject.block6.modes.global_and_doc_type.badge",
  },
  {
    value: "global_only",
    titleKey: "newProject.block6.modes.global_only.title",
    hintKey: "newProject.block6.modes.global_only.hint",
  },
  {
    value: "doc_type_only",
    titleKey: "newProject.block6.modes.doc_type_only.title",
    hintKey: "newProject.block6.modes.doc_type_only.hint",
  },
];

const Block6Launch: React.FC<Block6LaunchProps> = ({
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  showForceReclassify,
  canLaunch,
  isSubmitting,
  errorText = null,
  onLaunch,
}) => {
  const { t } = useTranslation("projects");

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();

    if (!canLaunch || isSubmitting) {
      return;
    }

    onLaunch();
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {errorText ? <InlineAlert tone="error" message={errorText} /> : null}

      {/* ── Режим проверки ─────────────────────────────────── */}
      <div>
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          {t("newProject.block6.checksModeLabel")}
        </p>

        <div className="mb-4 subtle-panel px-4 py-3">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {t("newProject.block6.infoTitle")}
          </p>
          <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
            {t("newProject.block6.infoDesc1")}
          </p>
          <p className="mt-2 text-[11px] leading-5 text-[var(--text-secondary)]">
            {t("newProject.block6.infoDesc2")}
          </p>
        </div>

        <div className="space-y-2">
          {CHECKS_MODE_KEYS.map(({ value, titleKey, hintKey, badgeKey }) => {
            const isChecked = checksMode === value;
            const title = t(titleKey);
            const hint = t(hintKey);
            const badge = badgeKey ? t(badgeKey) : undefined;

            return (
              <label
                key={value}
                className={[
                  "flex items-start gap-3 rounded-xl border px-3 py-3 transition",
                  isChecked
                    ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]"
                    : "border-[var(--border-subtle)] bg-[var(--bg-card)]",
                  isSubmitting
                    ? "cursor-not-allowed opacity-70"
                    : "cursor-pointer hover:bg-[var(--bg-elevated-soft)]",
                ]
                  .filter(Boolean)
                  .join(" ")}
                aria-disabled={isSubmitting}
              >
                <input
                  type="radio"
                  name="new_project_checks_mode"
                  className="mt-[2px]"
                  value={value}
                  checked={isChecked}
                  onChange={() => onChecksModeChange(value)}
                  disabled={isSubmitting}
                />

                <span>
                  <span className="flex items-center gap-2">
                    <span className="text-[13px] font-medium text-[var(--text-primary)]">
                      {title}
                    </span>
                    {badge ? (
                      <span className="rounded-full border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--color-success-text)]">
                        {badge}
                      </span>
                    ) : null}
                  </span>
                  <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                    {hint}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      </div>

      {/* ── Force reclassify ───────────────────────────────── */}
      {showForceReclassify ? (
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {t("newProject.block6.extraParamsLabel")}
          </p>

          <label
            className={[
              "flex items-start gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-3 transition",
              isSubmitting
                ? "cursor-not-allowed opacity-70"
                : "cursor-pointer hover:bg-[var(--bg-elevated-soft)]",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-disabled={isSubmitting}
          >
            <input
              type="checkbox"
              className="mt-[2px]"
              checked={forceReclassify}
              onChange={(e) => onForceReclassifyChange(e.target.checked)}
              disabled={isSubmitting}
            />

            <span>
              <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                {t("newProject.block6.forceReclassifyLabel")}
              </span>
              <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                {t("newProject.block6.forceReclassifyHint")}
              </span>
            </span>
          </label>
        </div>
      ) : null}

      {/* ── Launch button ──────────────────────────────────── */}
      <div className="border-t border-[var(--border-subtle)] pt-4">
        <div className="subtle-panel px-4 py-3">
          <p className="text-[11px] leading-5 text-[var(--text-secondary)]">
            {t("newProject.block6.launchNotice")}
          </p>
        </div>

        <div className="mt-4 flex justify-end">
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={!canLaunch || isSubmitting}
            isLoading={isSubmitting}
            leftIcon={
              !isSubmitting ? (
                <Rocket className="h-3.5 w-3.5" />
              ) : undefined
            }
          >
            {isSubmitting
              ? t("newProject.block6.launching")
              : t("newProject.block6.launchBtn")}
          </Button>
        </div>
      </div>
    </form>
  );
};

export default Block6Launch;


