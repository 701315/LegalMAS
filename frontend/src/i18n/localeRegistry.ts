import uiLocalesRaw from "../../../shared/config/ui_locales.json";

export interface UiLocale {
  code: string;
  nativeName: string;
  englishName: string;
  status: "supported" | "beta" | "disabled";
  isDefault: boolean;
  direction: "ltr" | "rtl";
}

interface UiLocalesConfig {
  schema_version: number;
  default_locale: string;
  locales: Array<{
    code: string;
    native_name: string;
    english_name: string;
    status: string;
    is_default: boolean;
    direction: string;
  }>;
}

const config = uiLocalesRaw as unknown as UiLocalesConfig;

export const DEFAULT_UI_LOCALE = config.default_locale || "en";

export const getEnabledUiLocales = (): UiLocale[] => {
  return config.locales
    .filter(loc => loc.status === "supported" || loc.status === "beta")
    .map(loc => ({
      code: loc.code,
      nativeName: loc.native_name,
      englishName: loc.english_name,
      status: loc.status as UiLocale["status"],
      isDefault: loc.is_default,
      direction: loc.direction as UiLocale["direction"],
    }));
};

export const getEnabledUiLocaleCodes = (): string[] => {
  return getEnabledUiLocales().map(loc => loc.code);
};

export const getLocaleDirection = (code: string): "ltr" | "rtl" => {
  const locale = getEnabledUiLocales().find(loc => loc.code === code);
  return locale ? locale.direction : "ltr";
};


