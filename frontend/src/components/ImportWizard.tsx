// =============================================================
// src/components/ImportWizard.tsx
// Мастер импорта документов для сделки + опция force_reclassify.
// Приведено к единому product-дизайну workspace.
// =============================================================

import React, { useState } from "react";
import type { Deal } from "../types";
import Button from "./ui/Button";
import InlineAlert from "./InlineAlert";

interface ImportWizardProps {
  deal: Deal;
}

const fileInputClassName =
  "block w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-base)] px-3 py-3 text-sm text-[var(--text-primary)] file:mr-3 file:rounded-xl file:border-0 file:bg-[var(--accent-muted)] file:px-3 file:py-2 file:text-sm file:font-medium file:text-[var(--accent-primary)]";

const stepBaseClassName =
  "flex h-9 w-9 items-center justify-center rounded-full border text-sm font-semibold transition-colors";

const ImportWizard: React.FC<ImportWizardProps> = ({ deal }) => {
  const [step, setStep] = useState<1 | 2>(1);
  const [forceReclassify, setForceReclassify] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [infoText, setInfoText] = useState<string | null>(null);

  const handleNext = () => {
    if (step === 1) {
      setStep(2);
      setInfoText(null);
    }
  };

  const handleBack = () => {
    if (step === 2) {
      setStep(1);
      setInfoText(null);
    }
  };

  const handleSubmit = () => {
    if (forceReclassify) {
      localStorage.setItem(`mas_dd_force_reclassify_${deal.id}`, "1");
    } else {
      localStorage.removeItem(`mas_dd_force_reclassify_${deal.id}`);
    }

    setInfoText(
      "Импорт запущен (заглушка). Настройка force_reclassify сохранена.",
    );
  };

  const renderStep = () => {
    if (step === 1) {
      return (
        <div className="space-y-4">
          <div>
            <h3 className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">
              Шаг 1. Выбор файлов
            </h3>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              Выберите документы или архив Data Room для импорта. Пока это
              заглушка интерфейса, но визуально она уже соответствует рабочему мастеру.
            </p>
          </div>

          <div className="rounded-[22px] border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
            <input
              type="file"
              multiple
              onChange={(e) => setSelectedFiles(e.target.files)}
              className={fileInputClassName}
            />

            {selectedFiles && selectedFiles.length > 0 ? (
              <div className="mt-3 rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-card)] px-3 py-2 text-xs text-[var(--text-secondary)]">
                Выбрано файлов:{" "}
                <span className="font-semibold text-[var(--text-primary)]">
                  {selectedFiles.length}
                </span>
              </div>
            ) : (
              <p className="mt-3 text-xs text-[var(--text-muted)]">
                Пока файлы не выбраны.
              </p>
            )}
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">
            Шаг 2. Параметры анализа
          </h3>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            Уточните параметры перед запуском импорта и предварительной обработки документов.
          </p>
        </div>

        <div className="rounded-[22px] border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={forceReclassify}
              onChange={(e) => setForceReclassify(e.target.checked)}
              className="mt-1 h-4 w-4 rounded border-[var(--border)]"
            />

            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Принудительная переклассификация
              </p>
              <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                Перезапустить HybridClassifier для всех документов перед анализом.
                Это полезно, если документы были переименованы или структура Data Room изменилась.
              </p>
            </div>
          </label>
        </div>
      </div>
    );
  };

  return (
    <div className="w-full max-w-2xl rounded-[28px] border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm">
      <div className="border-b border-[var(--border-soft)] pb-4">
        <div className="inline-flex items-center rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
          Import wizard
        </div>

        <h2 className="mt-3 text-[24px] font-semibold tracking-tight text-[var(--text-primary)]">
          Импорт документов
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {deal.name}
        </p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          Сделка: {deal.id}
        </p>
      </div>

      <div className="mt-5 flex items-center gap-3">
        <div className="flex items-center gap-3">
          <div
            className={[
              stepBaseClassName,
              step === 1
                ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--accent-primary)]"
                : "border-[var(--border-soft)] bg-[var(--bg-base)] text-[var(--text-muted)]",
            ].join(" ")}
          >
            1
          </div>
          <div className="text-sm font-medium text-[var(--text-primary)]">
            Файлы
          </div>
        </div>

        <div className="h-px flex-1 bg-[var(--border-soft)]" />

        <div className="flex items-center gap-3">
          <div
            className={[
              stepBaseClassName,
              step === 2
                ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--accent-primary)]"
                : "border-[var(--border-soft)] bg-[var(--bg-base)] text-[var(--text-muted)]",
            ].join(" ")}
          >
            2
          </div>
          <div className="text-sm font-medium text-[var(--text-primary)]">
            Параметры
          </div>
        </div>
      </div>

      <div className="mt-5">{renderStep()}</div>

      <div className="mt-4">
        <InlineAlert tone="info" message={infoText} />
      </div>

      <div className="mt-6 flex items-center justify-between border-t border-[var(--border-soft)] pt-4">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={handleBack}
          disabled={step === 1}
        >
          Назад
        </Button>

        <div className="flex gap-2">
          {step === 1 && (
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={handleNext}
              disabled={!selectedFiles || selectedFiles.length === 0}
            >
              Далее
            </Button>
          )}

          {step === 2 && (
            <Button
              type="button"
              variant="primary"
              size="md"
              onClick={handleSubmit}
            >
              Запустить импорт
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ImportWizard;


