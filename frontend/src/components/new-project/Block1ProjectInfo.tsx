// =============================================================
// src/components/new-project/Block1ProjectInfo.tsx
//
// Шаг 1 нового flow:
// - ввод названия проекта
// - создание deal
//
// После успешного создания блок становится read-only.
// =============================================================

import React from "react";
import { CheckCircle2 } from "lucide-react";

import Button from "../ui/Button";
import Field from "../ui/Field";
import InlineAlert from "../InlineAlert";

interface Block1ProjectInfoProps {
  projectName: string;
  onProjectNameChange: (value: string) => void;
  onCreateProject: () => void;
  onCancel?: () => void;
  isSubmitting: boolean;
  isCreated: boolean;
  errorText?: string | null;
}

const Block1ProjectInfo: React.FC<Block1ProjectInfoProps> = ({
  projectName,
  onProjectNameChange,
  onCreateProject,
  onCancel,
  isSubmitting,
  isCreated,
  errorText = null,
}) => {
  const canSubmit =
    !isCreated && !isSubmitting && projectName.trim().length > 0;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();

    if (!canSubmit) {
      return;
    }

    onCreateProject();
  };

  return (
    <div className="space-y-4">
      {errorText ? <InlineAlert tone="error" message={errorText} /> : null}

      <form onSubmit={handleSubmit} className="space-y-5">
        <Field
          label="Название проекта"
          required
          hint={
            isCreated
              ? "Проект уже создан. Название можно будет изменить позже в карточке проекта, если это потребуется."
              : "Лучше использовать короткое рабочее название, которое команда быстро узнает в dashboard и списке проектов."
          }
        >
          <input
            type="text"
            value={projectName}
            onChange={(event) => onProjectNameChange(event.target.value)}
            className="input-base"
            placeholder='Например: DD по покупке ООО «Ромашка»'
            autoComplete="off"
            disabled={isCreated || isSubmitting}
          />
        </Field>

        {isCreated ? (
          <div className="subtle-panel px-4 py-3">
            <div className="flex items-start gap-3">
              <div
                className="mt-0.5 shrink-0 text-[var(--color-success-text)]"
                aria-hidden="true"
              >
                <CheckCircle2 className="h-4 w-4" />
              </div>

              <div className="min-w-0">
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  Проект создан
                </p>
                <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                  Теперь можно перейти к следующему шагу настройки проекта.
                </p>
              </div>
            </div>
          </div>
        ) : null}

        {!isCreated ? (
          <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] pt-4">
            {onCancel ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={onCancel}
                disabled={isSubmitting}
              >
                Отмена
              </Button>
            ) : null}

            <Button
              type="submit"
              variant="primary"
              size="sm"
              isLoading={isSubmitting}
              disabled={!canSubmit}
            >
              {isSubmitting ? "Создаём…" : "Создать проект"}
            </Button>
          </div>
        ) : null}
      </form>
    </div>
  );
};

export default Block1ProjectInfo;


