const STORAGE_KEY = "steloom_ui_locale";

export const getPersistedLocale = (): string | null => {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch (e) {
    console.warn("localStorage is not available:", e);
    return null;
  }
};

export const setPersistedLocale = (locale: string): void => {
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch (e) {
    console.warn("Failed to save locale to localStorage:", e);
  }
};
