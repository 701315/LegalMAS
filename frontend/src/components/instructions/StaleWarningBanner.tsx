// src/components/instructions/StaleWarningBanner.tsx
// Предупреждение о stale override.
// Показывается когда is_stale=true.

import React from "react";
import { AlertTriangle } from "lucide-react";
import Button from "../ui/Button";

interface StaleWarningBannerProps {
  // Для tenant override — нет rebase, только предупреждение
  scope: "tenant" | "deal";
  onRebase?: () => void;
  isRebasing?: boolean;
}

const StaleWarningBanner: React.FC<StaleWarningBannerProps> = ({
  scope,
  onRebase,
  isRebasing = false,
}) => {
  return (
    <div className="flex items-start justify-between gap-3 rounded-xl border border-[color:var(--color-warning-border,#fbbf24)] bg-[color:var(--color-warning-bg,#fef9c3)] px-4 py-3">
      <div className="flex items-start gap-2.5 min-w-0">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--color-warning-text,#92400e)]"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <div className="text-xs font-semibold text-[color:var(--color-warning-text,#92400e)]">
            Override устарел
          </div>
          <p className="mt-0.5 text-[11px] text-[color:var(--color-warning-text,#92400e)]">
            Базовая версия инструкции была обновлена после создания этого
            override. Текущий override помечен как stale и не может быть
            активирован.
          </p>
          {scope === "deal" && (
            <p className="mt-1 text-[11px] text-[color:var(--color-warning-text,#92400e)]">
              Выполните rebase — укажите новую базовую версию и при
              необходимости скорректируйте patch operations.
            </p>
          )}
          {scope === "tenant" && (
            <p className="mt-1 text-[11px] text-[color:var(--color-warning-text,#92400e)]">
              Создайте новый override на актуальной базовой версии.
            </p>
          )}
        </div>
      </div>

      {scope === "deal" && onRebase && (
        <Button
          variant="secondary"
          size="sm"
          onClick={onRebase}
          isLoading={isRebasing}
          disabled={isRebasing}
          className="shrink-0"
        >
          Rebase
        </Button>
      )}
    </div>
  );
};

export default StaleWarningBanner;


