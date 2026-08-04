// src/components/instructions/ConcurrencyStatusBar.tsx
// Показывает текущее состояние ETag concurrency flow.
// Рендерится только когда есть что показать (не idle).

import React from "react";
import { AlertTriangle, Loader2, XCircle } from "lucide-react";
import type { ETagConcurrencyState } from "../../hooks/instructions/useETagConcurrency";
import Button from "../ui/Button";

interface ConcurrencyStatusBarProps {
  state: ETagConcurrencyState;
  onRetryAfterStale?: () => void;
  onDismissConflict?: () => void;
}

const ConcurrencyStatusBar: React.FC<ConcurrencyStatusBarProps> = ({
  state,
  onRetryAfterStale,
  onDismissConflict,
}) => {
  if (state.status === "idle" || state.status === "success") {
    return null;
  }

  // loading / saving
  if (state.status === "loading" || state.status === "saving") {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-3 py-2">
        <Loader2
          className="h-3.5 w-3.5 shrink-0 animate-spin text-[var(--text-muted)]"
          aria-hidden="true"
        />
        <span className="text-[11px] text-[var(--text-secondary)]">
          {state.status === "loading"
            ? "Загружаем данные версии…"
            : "Сохраняем черновик…"}
        </span>
      </div>
    );
  }

  // stale — 428: ETag устарел, перечитали, нужно повторить
  if (state.status === "stale") {
    return (
      <div className="flex items-center justify-between gap-3 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2">
        <div className="flex items-center gap-2 min-w-0">
          <AlertTriangle
            className="h-3.5 w-3.5 shrink-0 text-[var(--color-warning-text)]"
            aria-hidden="true"
          />
          <span className="text-[11px] text-[var(--color-warning-text)]">
            Данные были обновлены на сервере. Нажмите «Сохранить» ещё раз
            чтобы применить изменения.
          </span>
        </div>
        {onRetryAfterStale && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onRetryAfterStale}
            className="shrink-0"
          >
            Повторить
          </Button>
        )}
      </div>
    );
  }

  // conflict — 412: параллельное редактирование
  if (state.status === "conflict") {
    return (
      <div className="flex items-center justify-between gap-3 rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-3 py-2">
        <div className="flex items-center gap-2 min-w-0">
          <XCircle
            className="h-3.5 w-3.5 shrink-0 text-[var(--color-error-text)]"
            aria-hidden="true"
          />
          <span className="text-[11px] text-[var(--color-error-text)]">
            Конфликт редактирования — версия была изменена другим
            пользователем. Ваши изменения не сохранены. Просмотрите свежие
            данные и повторно примените изменения.
          </span>
        </div>
        {onDismissConflict && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onDismissConflict}
            className="shrink-0"
          >
            Понятно
          </Button>
        )}
      </div>
    );
  }

  // error
  if (state.status === "error") {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-3 py-2">
        <XCircle
          className="h-3.5 w-3.5 shrink-0 text-[var(--color-error-text)]"
          aria-hidden="true"
        />
        <span className="text-[11px] text-[var(--color-error-text)]">
          {state.errorMessage ?? "Ошибка сохранения."}
        </span>
      </div>
    );
  }

  return null;
};

export default ConcurrencyStatusBar;


