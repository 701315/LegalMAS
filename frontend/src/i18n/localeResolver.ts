// frontend/src/i18n/localeResolver.ts

import { DEFAULT_UI_LOCALE, getEnabledUiLocaleCodes } from "./localeRegistry";
import { getPersistedLocale, getPersistedOutputLocale } from "./localePersistence";
import { getEnabledResultLocaleCodes, DEFAULT_OUTPUT_LOCALE } from "./resultLocaleRegistry";

/**
 * Разрешает язык интерфейса на основе приоритетов:
 * 1. Явно переданная локаль (например, из профиля пользователя)
 * 2. Локаль из localStorage
 * 3. Язык браузера (navigator.language)
 * 4. Дефолтный язык (en)
 */
export const resolveUiLocale = (userLocale?: string | null): string => {
  const enabledCodes = getEnabledUiLocaleCodes();

  // 1. Приоритет профиля пользователя (для авторизованных)
  if (userLocale && enabledCodes.includes(userLocale)) {
    return userLocale;
  }

  // 2. Приоритет localStorage (для анонимных, выбравших язык на форме входа)
  const persisted = getPersistedLocale();
  if (persisted && enabledCodes.includes(persisted)) {
    return persisted;
  }

  // 3. Строгий дефолт (English)
  return DEFAULT_UI_LOCALE;
};

/**
 * Разрешает язык выдачи результатов (ось результатов) на основе приоритетов:
 * 1. Явно переданная локаль
 * 2. steloom_output_locale из localStorage (независимая настройка пользователя)
 * 3. steloom_ui_locale из localStorage (fallback)
 * 4. Дефолтный язык результатов из реестра (обычно "en")
 */
export const resolveOutputLocale = (explicitLocale?: string | null): string => {
  const enabledResultCodes = getEnabledResultLocaleCodes();

  // 1. Explicitly passed parameter
  if (explicitLocale && enabledResultCodes.includes(explicitLocale)) {
    return explicitLocale;
  }

  // 2. Persisted output-specific locale
  const persistedOutput = getPersistedOutputLocale();
  if (persistedOutput && enabledResultCodes.includes(persistedOutput)) {
    return persistedOutput;
  }

  // 3. Persisted UI locale fallback
  const persistedUi = getPersistedLocale();
  if (persistedUi && enabledResultCodes.includes(persistedUi)) {
    return persistedUi;
  }

  // 4. Fallback to platform default result locale
  return DEFAULT_OUTPUT_LOCALE || "en";
};
