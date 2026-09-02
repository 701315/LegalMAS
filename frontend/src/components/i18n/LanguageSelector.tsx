import React from "react";
import { useTranslation } from "react-i18next";
import { getEnabledUiLocales, type UiLocale } from "../../i18n/localeRegistry";

interface LanguageSelectorProps {
  /**
   * Опциональный коллбек, вызываемый при смене языка.
   * Полезен для отправки PATCH запроса на бэкенд, если пользователь авторизован.
   */
  onLocaleChange?: (newLocale: string) => void | Promise<void>;
  /**
   * Стили оформления: 'minimal' (просто текст) или 'outline' (с рамкой, для страницы входа)
   */
  variant?: "minimal" | "outline";
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  onLocaleChange,
  variant = "minimal",
}) => {
  const { i18n } = useTranslation();
  const enabledLocales = getEnabledUiLocales();

  const handleLanguageChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newLocale = e.target.value;
    
    // 1. Меняем язык локально в i18next
    await i18n.changeLanguage(newLocale);
    
    // 2. Если передан обработчик (например, для сохранения в БД), вызываем его
    if (onLocaleChange) {
      try {
        await onLocaleChange(newLocale);
      } catch (err) {
        console.error("Failed to save language preference to backend:", err);
      }
    }
  };

  const selectClasses =
    variant === "outline"
      ? "block w-full rounded-md border border-gray-300 bg-white py-1.5 px-3 text-sm text-gray-700 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
      : "bg-transparent text-sm text-gray-600 hover:text-gray-900 focus:outline-none cursor-pointer font-medium";

  return (
    <div className="inline-block relative">
      <select
        value={i18n.resolvedLanguage || i18n.language}
        onChange={handleLanguageChange}
        className={selectClasses}
        aria-label="Select Interface Language"
      >
        {enabledLocales.map((loc: UiLocale) => (
          <option key={loc.code} value={loc.code} className="text-gray-900 bg-white">
            {loc.nativeName} ({loc.code.toUpperCase()})
          </option>
        ))}
      </select>
    </div>
  );
};


