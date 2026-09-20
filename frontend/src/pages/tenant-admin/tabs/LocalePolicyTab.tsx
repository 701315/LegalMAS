import React from "react";
import { useTranslation } from "react-i18next";
import { Check, Globe, Info, Save, ShieldAlert } from "lucide-react";

import { useTenantLocalePolicy, useUpdateTenantLocalePolicy } from "../../../api/tenantAdmin";
import Button from "../../../components/ui/Button";

interface LocaleOption {
  code: string;
  name: string;
}

const SUPPORTED_LOCALES: LocaleOption[] = [
  { code: "en", name: "English (US/UK)" },
  { code: "ru", name: "Russian (Русский)" },
  { code: "de", name: "German (Deutsch)" },
  { code: "fr", name: "French (Français)" },
  { code: "es", name: "Spanish (Español)" },
  { code: "zh", name: "Chinese (中文)" }
];

export const LocalePolicyTab: React.FC = () => {
  const { t } = useTranslation("tenantAdmin");

  const { data: policy, isLoading, isError } = useTenantLocalePolicy();
  const updateMutation = useUpdateTenantLocalePolicy();

  const [allowedLocales, setAllowedLocales] = React.useState<string[]>([]);
  const [isTranslationEnabled, setIsTranslationEnabled] = React.useState(true);
  const [restrictToAllowed, setRestrictToAllowed] = React.useState(true);
  const [saveSuccess, setSaveSuccess] = React.useState(false);

  React.useEffect(() => {
    if (policy) {
      setAllowedLocales(policy.allowed_locales || []);
      setIsTranslationEnabled(policy.is_translation_enabled ?? true);
      setRestrictToAllowed(policy.restrict_to_allowed ?? true);
    }
  }, [policy]);

  if (isLoading) {
    return (
      <div className="flex h-48 items-center justify-center gap-2 text-sm text-[var(--text-muted)]" role="status">
        <Globe className="h-5 w-5 animate-spin" aria-hidden="true" />
        <span>{t("policy.loading", "Loading language policy settings...")}</span>
      </div>
    );
  }

  if (isError || !policy) {
    return (
      <div className="rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] p-4 text-sm text-[var(--color-error-text)]" role="alert">
        <ShieldAlert className="h-5 w-5 inline mr-2" aria-hidden="true" />
        <span>{t("policy.loadError", "Failed to load tenant translation policy settings from the database.")}</span>
      </div>
    );
  }

  const handleToggleLocale = (code: string) => {
    setAllowedLocales((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    try {
      await updateMutation.mutateAsync({
        allowed_locales: allowedLocales,
        is_translation_enabled: isTranslationEnabled,
        restrict_to_allowed: restrictToAllowed,
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      console.error("Failed to save translation policy:", err);
    }
  };

  const isDirty =
    JSON.stringify([...allowedLocales].sort()) !== JSON.stringify([...(policy.allowed_locales || [])].sort()) ||
    isTranslationEnabled !== (policy.is_translation_enabled ?? true) ||
    restrictToAllowed !== (policy.restrict_to_allowed ?? true);

  return (
    <div className="min-h-0 flex-1 overflow-auto px-5 pb-5 pt-4">
      <div className="max-w-2xl space-y-6">
        {/* Intro */}
        <div className="flex gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-4">
          <Info className="h-5 w-5 shrink-0 text-[var(--accent-primary)]" aria-hidden="true" />
          <div className="text-xs leading-5 text-[var(--text-secondary)]">
            <h4 className="font-semibold text-[var(--text-primary)] mb-1">
              {t("policy.introTitle", "About Language Policy Settings")}
            </h4>
            <p>
              {t(
                "policy.introDesc",
                "These policies dictate the localization rules for all projects in your organization. You can lock report generation, disable translation pipelines entirely, or restrict users only to specific verified BCP-47 output languages."
              )}
            </p>
          </div>
        </div>

        {/* Enable Translation Pipelines Switch */}
        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <label className="text-sm font-semibold text-[var(--text-primary)]">
                {t("policy.enableTranslation", "Enable Translation Pipelines")}
              </label>
              <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                {t(
                  "policy.enableTranslationDesc",
                  "When disabled, LLM-based translations are blocked entirely. Users can only view analysis results in the original Project Primary Language."
                )}
              </p>
            </div>
            <input
              type="checkbox"
              checked={isTranslationEnabled}
              onChange={(e) => {
                setIsTranslationEnabled(e.target.checked);
                setSaveSuccess(false);
              }}
              className="h-4 w-4 rounded border-[var(--border)] text-[var(--accent-primary)] focus:ring-[var(--accent-primary)]"
            />
          </div>
        </div>

        {/* Allowed target languages configuration */}
        {isTranslationEnabled && (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm space-y-4">
            <div className="space-y-1">
              <label className="text-sm font-semibold text-[var(--text-primary)]">
                {t("policy.allowedLanguages", "Allowed Translation Target Languages")}
              </label>
              <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                {t(
                  "policy.allowedLanguagesDesc",
                  "Select which languages are available for report exports and grid viewing. If no languages are selected, all globally supported languages are allowed."
                )}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2 pt-2">
              {SUPPORTED_LOCALES.map((loc) => {
                const isSelected = allowedLocales.includes(loc.code);
                const btnClass = isSelected
                  ? "flex items-center justify-between rounded-lg border p-3 text-left transition-all border-[var(--accent-primary)] bg-[var(--accent-primary)]/5 text-[var(--text-primary)] font-semibold"
                  : "flex items-center justify-between rounded-lg border p-3 text-left transition-all border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:border-[var(--border)]";

                return (
                  <button
                    key={loc.code}
                    type="button"
                    onClick={() => handleToggleLocale(loc.code)}
                    className={btnClass}
                  >
                    <div className="min-w-0">
                      <div className="text-xs text-[var(--text-muted)] uppercase font-semibold">{loc.code}</div>
                      <div className="text-sm truncate mt-0.5">{loc.name}</div>
                    </div>
                    {isSelected && <Check className="h-4 w-4 text-[var(--accent-primary)]" />}
                  </button>
                );
              })}
            </div>

            {/* Strict validation restrict control */}
            {allowedLocales.length > 0 && (
              <div className="flex items-start justify-between gap-4 border-t border-[var(--border-subtle)] pt-4 mt-2">
                <div className="space-y-1">
                  <label className="text-sm font-semibold text-[var(--text-primary)]">
                    {t("policy.enforceStrictly", "Enforce Restrictions Strictly")}
                  </label>
                  <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                    {t(
                      "policy.enforceStrictlyDesc",
                      "Block API calls and hide options for languages outside of the selected list. If unchecked, unselected languages remain accessible via explicit API requests but are hidden in UI settings."
                    )}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={restrictToAllowed}
                  onChange={(e) => {
                    setRestrictToAllowed(e.target.checked);
                    setSaveSuccess(false);
                  }}
                  className="h-4 w-4 rounded border-[var(--border)] text-[var(--accent-primary)] focus:ring-[var(--accent-primary)]"
                />
              </div>
            )}
          </div>
        )}

        {/* Action bar and Save button */}
        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="primary"
            onClick={handleSave}
            disabled={!isDirty || updateMutation.isPending}
            isLoading={updateMutation.isPending}
            leftIcon={<Save className="h-4 w-4" />}
          >
            {t("policy.saveButton", "Save translation policy")}
          </Button>

          {saveSuccess && (
            <span className="text-xs font-semibold text-[var(--color-success-text)] flex items-center gap-1" role="status">
              <Check className="h-4 w-4" aria-hidden="true" /> {t("policy.saveSuccess", "Translation policy updated successfully!")}
            </span>
          )}

          {updateMutation.isError && (
            <span className="text-xs font-semibold text-[var(--color-error-text)]" role="alert">
              {t("policy.saveError", "Error saving translation policy.")}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default LocalePolicyTab;


