// =============================================================
// src/components/ui/Tabs.tsx
// Простая реализация вкладок (Tabs) на React.
// =============================================================

import React from "react";

interface TabsProps {
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}

interface TabsTriggerOwnProps {
  value: string;
  children: React.ReactNode;
}

interface TabsTriggerInjectedProps {
  currentValue?: string;
  onChange?: (value: string) => void;
}

export type TabsTriggerProps = TabsTriggerOwnProps & TabsTriggerInjectedProps;

interface TabsContentOwnProps {
  value: string;
  children: React.ReactNode;
}

interface TabsContentInjectedProps {
  currentValue: string;
}

export type TabsContentProps = TabsContentOwnProps & TabsContentInjectedProps;

/**
 * Обёртка для группы табов.
 * Пример:
 *   <Tabs value={active} onChange={setActive}>
 *     ...
 *   </Tabs>
 */
export const Tabs: React.FC<TabsProps> = ({ value, onChange, children }) => {
  return (
    <div data-active-tab={value}>
      {React.Children.map(children, (child) => {
        if (!React.isValidElement(child)) return child;

        // child может быть TabsTrigger или TabsContent.
        // Для TabsTrigger пробрасываем currentValue и onChange,
        // для TabsContent — только currentValue.
        const childType = child.type;

        if (childType === TabsTrigger) {
          return React.cloneElement(
            child as React.ReactElement<TabsTriggerProps>,
            {
              currentValue: value,
              onChange,
            },
          );
        }

        if (childType === TabsContent) {
          return React.cloneElement(
            child as React.ReactElement<TabsContentProps>,
            {
              currentValue: value,
            },
          );
        }

        // Для любых других потомков ничего не меняем
        return child;
      })}
    </div>
  );
};

/**
 * Кнопка-вкладка.
 * Используется внутри Tabs.
 */
export const TabsTrigger: React.FC<TabsTriggerProps> = ({
  value,
  currentValue,
  onChange,
  children,
}) => {
  const isActive = currentValue === value;
  return (
    <button
      type="button"
      onClick={() => onChange && onChange(value)}
      className={
        isActive
          ? "px-3 py-2 text-sm font-medium border-b-2 border-blue-600 text-blue-600"
          : "px-3 py-2 text-sm font-medium text-gray-500 hover:text-gray-700"
      }
    >
      {children}
    </button>
  );
};

/**
 * Контент вкладки.
 * Показывает children только если value === currentValue.
 */
export const TabsContent: React.FC<TabsContentProps> = ({
  value,
  currentValue,
  children,
}) => {
  if (value !== currentValue) return null;
  return <div className="mt-4">{children}</div>;
};
