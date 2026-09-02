import { DEFAULT_UI_LOCALE, getEnabledUiLocaleCodes } from "./localeRegistry";
import { getPersistedLocale } from "./localePersistence";

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


