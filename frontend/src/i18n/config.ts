import i18n from "i18next";
import HttpBackend from "i18next-http-backend";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";
import { DEFAULT_UI_LOCALE, getEnabledUiLocaleCodes, getLocaleDirection } from "./localeRegistry";
import { resolveUiLocale } from "./localeResolver";
import { setPersistedLocale } from "./localePersistence";

const initialLocale = resolveUiLocale();

i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    lng: initialLocale,
    supportedLngs: getEnabledUiLocaleCodes(),
    fallbackLng: DEFAULT_UI_LOCALE,
    defaultNS: "common",
    ns: [
      "common", "navigation", "auth", "projects", "documents",
      "analysis", "pipeline", "findings", "requests", "playbooks",
      "instructions", "admin", "tenantAdmin", "counterparties",
      "realEstate", "ddGrid", "errors", "exports", "marketing", "security" // <-- ДОБАВЛЕНО
    ],
    backend: {
      loadPath: "/locales/{{lng}}/{{ns}}.json",
    },
    interpolation: {
      escapeValue: false,
    },
    returnNull: false,
    returnEmptyString: false,
  });

i18n.on("languageChanged", (lng) => {
  setPersistedLocale(lng);
  if (typeof document !== "undefined") {
    const html = document.documentElement;
    html.setAttribute("lang", lng);
    html.setAttribute("dir", getLocaleDirection(lng));
  }
});

export default i18n;
