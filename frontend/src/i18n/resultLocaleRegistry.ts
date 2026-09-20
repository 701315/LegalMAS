// frontend/src/i18n/resultLocaleRegistry.ts

/**
 * Result output locale registry.
 *
 * Reads shared/config/result_locales.json and exposes helpers for the
 * result-presentation language selector and API calls.
 *
 * IMPORTANT (Invariant #5): This is for OUTPUT locales of translated
 * check-result presentations — a SEPARATE axis from UI locales.
 */

import resultLocalesRaw from "../../../shared/config/result_locales.json";

export interface ResultLocaleTranslation {
  supportedSourceLocales: string[];
  promptVersion: string;
  qualityGate: string;
}

export interface ResultLocale {
  code: string;
  nativeName: string;
  englishName: string;
  status: "supported" | "beta" | "disabled";
  isDefault: boolean;
  direction: "ltr" | "rtl";
  translation: ResultLocaleTranslation;
}

interface ResultLocalesConfig {
  schema_version: number;
  default_output_locale: string;
  default_output_policy: string;
  locales: Array<{
    code: string;
    native_name: string;
    english_name: string;
    status: string;
    is_default: boolean;
    direction: string;
    translation: {
      supported_source_locales: string[];
      prompt_version: string;
      quality_gate: string;
    };
  }>;
}

const config = resultLocalesRaw as unknown as ResultLocalesConfig;

export const DEFAULT_OUTPUT_LOCALE =
  config.default_output_locale || "en";

export const DEFAULT_OUTPUT_POLICY =
  config.default_output_policy || "match_analysis_language";

export const getEnabledResultLocales = (): ResultLocale[] => {
  return config.locales
    .filter((loc) => loc.status === "supported" || loc.status === "beta")
    .map((loc) => ({
      code: loc.code,
      nativeName: loc.native_name,
      englishName: loc.english_name,
      status: loc.status as ResultLocale["status"],
      isDefault: loc.is_default,
      direction: loc.direction as ResultLocale["direction"],
      translation: {
        supportedSourceLocales:
          loc.translation?.supported_source_locales ?? [],
        promptVersion: loc.translation?.prompt_version ?? "v1",
        qualityGate: loc.translation?.quality_gate ?? "basic",
      },
    }));
};

export const getEnabledResultLocaleCodes = (): string[] => {
  return getEnabledResultLocales().map((loc) => loc.code);
};

export const isValidResultLocale = (code: string | null | undefined): boolean => {
  if (!code) return true;
  return getEnabledResultLocaleCodes().includes(code.trim().toLowerCase());
};

export const isTranslationPairSupported = (
  sourceLocale: string,
  targetLocale: string,
): boolean => {
  const target = getEnabledResultLocales().find(
    (loc) => loc.code === targetLocale.trim().toLowerCase(),
  );
  if (!target) return false;
  return target.translation.supportedSourceLocales.includes(
    sourceLocale.trim().toLowerCase(),
  );
};

