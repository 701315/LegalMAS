// =============================================================
// src/components/requests/shared/RequestStructuredValuesList.tsx
// Shared UI компонент для отображения извлечённых значений (structured values).
// Используется в:
// - RequestSidePanel (legacy)
// - ReviewRequestSidePanel (review)
//
// Для непрофессионального программиста:
// Это таблица "ключ → значение" для данных, которые AI извлёк из документа.
// Например: "Цена → 5 000 000 руб.", "Дата → 15.03.2024"
// =============================================================

import React from "react";
import type { StructuredValueView } from "../../../viewAdapters/requestPresentation";

interface RequestStructuredValuesListProps {
  values: StructuredValueView[];
  /**
   * Максимальная высота списка в пикселях (для overflow-y-auto).
   */
  maxHeight?: string;
}

/**
 * Отображает список извлечённых значений в виде таблицы ключ-значение.
 * Поддерживает форматы: money, date, entity_name, text.
 */
export const RequestStructuredValuesList: React.FC<
  RequestStructuredValuesListProps
> = ({ values, maxHeight = "10rem" }) => {
  if (values.length === 0) {
    return (
      <div className="text-xs text-gray-400 py-2 text-center">
        Извлечённые данные отсутствуют
      </div>
    );
  }

  return (
    <div
      className="space-y-1 bg-gray-50 rounded p-2 overflow-y-auto"
      style={{ maxHeight }}
    >
      {values.map((sv, index) => (
        <div
          key={index}
          className="flex justify-between gap-2 text-xs py-0.5 border-b border-gray-100 last:border-0"
        >
          {/* Ключ (название поля) */}
          <span className="text-gray-400 capitalize shrink-0">
            {sv.key.replace(/_/g, " ")}
            {sv.format && (
              <span className="ml-1 text-gray-300 normal-case">
                ({sv.format})
              </span>
            )}
          </span>

          {/* Значение */}
          <span className="text-gray-700 font-medium text-right break-words">
            {sv.value}
          </span>
        </div>
      ))}
    </div>
  );
};

export default RequestStructuredValuesList;


