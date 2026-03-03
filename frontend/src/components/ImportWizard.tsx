// =============================================================
// src/components/ImportWizard.tsx
// Мастер импорта документов для сделки + опция force_reclassify.
// =============================================================

import React, { useState } from "react";
import type { Deal } from "../types";

/**
 * Пропсы ImportWizard:
 * - deal: текущая сделка, для которой импортируем документы
 *
 * Позже сюда добавим колбэки onCompleted и вызов API импорта.
 */
interface ImportWizardProps {
  deal: Deal;
}

/**
 * Простейший скелет мастера импорта:
 * Шаг 1 — выбор файлов (пока заглушка).
 * Шаг 2 — параметры анализа (здесь переключатель force_reclassify).
 */
const ImportWizard: React.FC<ImportWizardProps> = ({ deal }) => {
  const [step, setStep] = useState<1 | 2>(1);

  // Локальный флаг принудительной переклассификации
  const [forceReclassify, setForceReclassify] = useState(false);

  // Заглушка для списка файлов
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);

  const handleNext = () => {
    if (step === 1) {
      setStep(2);
    }
  };

  const handleBack = () => {
    if (step === 2) {
      setStep(1);
    }
  };

  /**
   * "Завершить" импорт.
   * Здесь в реальном проекте:
   * - отправляется multipart-запрос на бэкенд
   * - создаётся ImportJob
   * - после завершения можно стартовать Run
   *
   * Сейчас мы только сохраняем флаг force_reclassify в localStorage.
   */
  const handleSubmit = () => {
    if (forceReclassify) {
      // Ключ включает ID сделки, чтобы не мешать разные сделки.
      localStorage.setItem(`mas_dd_force_reclassify_${deal.id}`, "1");
    } else {
      localStorage.removeItem(`mas_dd_force_reclassify_${deal.id}`);
    }

    // TODO: здесь будет реальный вызов API импорта
    // и закрытие мастера / переход на DealPage.

    alert("Импорт запущен (заглушка). Настройка force_reclassify сохранена.");
  };

  // Рендер разных шагов мастера
  const renderStep = () => {
    if (step === 1) {
      return (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-gray-900">
            Шаг 1. Выбор файлов
          </h3>
          <p className="text-sm text-gray-500">
            Здесь пользователь выбирает файлы или загружает архив Data Room.
            В текущей версии компонент работает как заглушка.
          </p>

          <input
            type="file"
            multiple
            onChange={(e) => setSelectedFiles(e.target.files)}
            className="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50"
          />

          {selectedFiles && selectedFiles.length > 0 && (
            <p className="text-xs text-gray-500 mt-1">
              Выбрано файлов: {selectedFiles.length}
            </p>
          )}
        </div>
      );
    }

    // Шаг 2: параметры анализа
    return (
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-gray-900">
          Шаг 2. Параметры анализа
        </h3>
        <p className="text-sm text-gray-500">
          Выберите параметры перед запуском анализа документов.
        </p>

        {/* Опция force_reclassify */}
        <div className="mt-4 p-4 bg-gray-50 rounded-lg border">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={forceReclassify}
              onChange={(e) => setForceReclassify(e.target.checked)}
              className="mt-0.5 rounded border-gray-300"
            />
            <div>
              <p className="text-sm font-medium text-gray-800">
                Принудительная переклассификация
              </p>
              <p className="text-xs text-gray-500 mt-0.5">
                Перезапустить HybridClassifier для всех документов перед
                анализом. Рекомендуется, если документы были переименованы
                или структура Data Room изменилась.
              </p>
            </div>
          </label>
        </div>
      </div>
    );
  };

  return (
    <div className="bg-white rounded-lg shadow border p-6 max-w-2xl">
      <h2 className="text-xl font-bold text-gray-900 mb-2">
        Импорт документов — {deal.name}
      </h2>
      <p className="text-xs text-gray-500 mb-4">Сделка: {deal.id}</p>

      {/* Тело текущего шага */}
      {renderStep()}

      {/* Кнопки навигации по шагам */}
      <div className="mt-6 flex justify-between">
        <button
          type="button"
          onClick={handleBack}
          disabled={step === 1}
          className="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700 disabled:opacity-50"
        >
          Назад
        </button>

        <div className="flex gap-2">
          {step === 1 && (
            <button
              type="button"
              onClick={handleNext}
              disabled={!selectedFiles || selectedFiles.length === 0}
              className="px-4 py-2 text-sm rounded bg-blue-600 text-white disabled:opacity-50"
            >
              Далее
            </button>
          )}

          {step === 2 && (
            <button
              type="button"
              onClick={handleSubmit}
              className="px-4 py-2 text-sm rounded bg-green-600 text-white"
            >
              Запустить импорт
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ImportWizard;
