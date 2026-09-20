const UI_LOCALE_KEY = "steloom_ui_locale";
const OUTPUT_LOCALE_KEY = "steloom_output_locale";

// --- UI Locale (interface language: buttons, menus, labels) ---

export const getPersistedLocale = (): string | null => {
  try {
    return localStorage.getItem(UI_LOCALE_KEY);
  } catch (e) {
    console.warn("localStorage is not available:", e);
    return null;
  }
};

export const setPersistedLocale = (locale: string): void => {
  try {
    localStorage.setItem(UI_LOCALE_KEY, locale);
  } catch (e) {
    console.warn("Failed to save UI locale to localStorage:", e);
  }
};

// --- Output Locale (result presentation language: check names, evidence, DD Grid) ---
// Independent axis from UI locale. A lawyer with RU interface can view EN results.

export const getPersistedOutputLocale = (): string | null => {
  try {
    return localStorage.getItem(OUTPUT_LOCALE_KEY);
  } catch (e) {
    console.warn("localStorage is not available:", e);
    return null;
  }
};

export const setPersistedOutputLocale = (locale: string): void => {
  try {
    localStorage.setItem(OUTPUT_LOCALE_KEY, locale);
  } catch (e) {
    console.warn("Failed to save output locale to localStorage:", e);
  }
};

export const clearPersistedOutputLocale = (): void => {
  try {
    localStorage.removeItem(OUTPUT_LOCALE_KEY);
  } catch (e) {
    console.warn("Failed to clear output locale from localStorage:", e);
  }
};


