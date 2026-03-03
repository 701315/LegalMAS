// =============================================================
// src/components/ui/TriggerList.tsx
// Список применимых триггеров документа (applicable_triggers).
// =============================================================

import React from "react";

// Простая версия функции объединения className (как в ClassificationBadge)
function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

interface Props {
  triggers: string[];
  maxVisible?: number;
  className?: string;
}

/**
 * Показывает список YAML-триггеров.
 * Пример:
 *   <TriggerList triggers={document.applicable_triggers ?? []} />
 */
export const TriggerList: React.FC<Props> = ({
  triggers,
  maxVisible = 3,
  className,
}) => {
  if (!triggers || triggers.length === 0) {
    return (
      <span className="text-xs text-gray-400 italic">Нет триггеров</span>
    );
  }

  const visible = triggers.slice(0, maxVisible);
  const hidden = triggers.length - maxVisible;

  return (
    <div className={cn("flex flex-wrap gap-1", className)}>
      {visible.map((t) => (
        <span
          key={t}
          className="inline-block px-1.5 py-0.5 bg-purple-50
                     text-purple-700 text-xs rounded border border-purple-200"
          title={`Условный триггер: ${t}`}
        >
          ⚡ {t}
        </span>
      ))}
      {hidden > 0 && (
        <span className="text-xs text-gray-400 self-center">
          +{hidden} ещё
        </span>
      )}
    </div>
  );
};
