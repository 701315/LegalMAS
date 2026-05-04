// =============================================================
// src/components/ui/Tabs.tsx
// Простая реализация вкладок (Tabs), приведённая к общему стилю UI:
// tokens, мягкие радиусы, muted/accent, keyboard navigation.
// =============================================================

import React from "react";
import { twMerge } from "tailwind-merge";

interface TabsProps {
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
}

interface TabsListProps {
  children: React.ReactNode;
  className?: string;
  "aria-label"?: string;
}

interface TabsTriggerProps {
  value: string;
  children: React.ReactNode;
  disabled?: boolean;
  className?: string;
}

interface TabsContentProps {
  value: string;
  children: React.ReactNode;
  className?: string;
}

interface TabsContextValue {
  currentValue: string;
  onChange: (value: string) => void;
  baseId: string;
  registerTrigger: (value: string, ref: HTMLButtonElement | null) => void;
  getOrderedTriggers: () => Array<{
    value: string;
    ref: HTMLButtonElement | null;
    disabled: boolean;
  }>;
  setTriggerDisabled: (value: string, disabled: boolean) => void;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

function cn(...classes: Array<string | false | null | undefined>) {
  return twMerge(classes.filter(Boolean).join(" "));
}

function getSafeId(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
}

function useTabsContext(componentName: string): TabsContextValue {
  const context = React.useContext(TabsContext);

  if (!context) {
    throw new Error(`${componentName} must be used within <Tabs>.`);
  }

  return context;
}

export const Tabs: React.FC<TabsProps> = ({
  value,
  onChange,
  children,
  className,
}) => {
  const reactId = React.useId();
  const baseId = React.useMemo(
    () => `tabs-${reactId.replace(/[:]/g, "")}`,
    [reactId],
  );

  const triggersRef = React.useRef<
    Map<string, { ref: HTMLButtonElement | null; disabled: boolean }>
  >(new Map());

  const registerTrigger = React.useCallback(
    (triggerValue: string, ref: HTMLButtonElement | null) => {
      const existing = triggersRef.current.get(triggerValue);

      triggersRef.current.set(triggerValue, {
        ref,
        disabled: existing?.disabled ?? false,
      });
    },
    [],
  );

  const setTriggerDisabled = React.useCallback(
    (triggerValue: string, disabled: boolean) => {
      const existing = triggersRef.current.get(triggerValue);

      triggersRef.current.set(triggerValue, {
        ref: existing?.ref ?? null,
        disabled,
      });
    },
    [],
  );

  const getOrderedTriggers = React.useCallback(() => {
    return Array.from(triggersRef.current.entries()).map(([triggerValue, item]) => ({
      value: triggerValue,
      ref: item.ref,
      disabled: item.disabled,
    }));
  }, []);

  const contextValue = React.useMemo<TabsContextValue>(
    () => ({
      currentValue: value,
      onChange,
      baseId,
      registerTrigger,
      getOrderedTriggers,
      setTriggerDisabled,
    }),
    [value, onChange, baseId, registerTrigger, getOrderedTriggers, setTriggerDisabled],
  );

  return (
    <TabsContext.Provider value={contextValue}>
      <div data-active-tab={value} className={className}>
        {children}
      </div>
    </TabsContext.Provider>
  );
};

export const TabsList: React.FC<TabsListProps> = ({
  children,
  className,
  "aria-label": ariaLabel = "Tabs",
}) => {
  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex items-center gap-1 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-1",
        className,
      )}
    >
      {children}
    </div>
  );
};

export const TabsTrigger: React.FC<TabsTriggerProps> = ({
  value,
  children,
  disabled = false,
  className,
}) => {
  const {
    currentValue,
    onChange,
    baseId,
    registerTrigger,
    getOrderedTriggers,
    setTriggerDisabled,
  } = useTabsContext("TabsTrigger");

  const isActive = currentValue === value;
  const safeId = getSafeId(value);
  const tabId = `${baseId}-tab-${safeId}`;
  const panelId = `${baseId}-panel-${safeId}`;

  const buttonRef = React.useRef<HTMLButtonElement | null>(null);

  React.useEffect(() => {
    registerTrigger(value, buttonRef.current);

    return () => {
      registerTrigger(value, null);
      setTriggerDisabled(value, false);
    };
  }, [registerTrigger, setTriggerDisabled, value]);

  React.useEffect(() => {
    setTriggerDisabled(value, disabled);
  }, [disabled, setTriggerDisabled, value]);

  const focusAdjacentTab = React.useCallback(
    (direction: 1 | -1) => {
      const enabledTriggers = getOrderedTriggers().filter(
        (item) => item.ref && !item.disabled,
      );

      if (!enabledTriggers.length) {
        return;
      }

      const currentIndex = enabledTriggers.findIndex(
        (item) => item.value === value,
      );

      if (currentIndex === -1) {
        enabledTriggers[0].ref?.focus();
        return;
      }

      const nextIndex =
        (currentIndex + direction + enabledTriggers.length) %
        enabledTriggers.length;

      enabledTriggers[nextIndex].ref?.focus();
      onChange(enabledTriggers[nextIndex].value);
    },
    [getOrderedTriggers, onChange, value],
  );

  const focusBoundaryTab = React.useCallback(
    (position: "first" | "last") => {
      const enabledTriggers = getOrderedTriggers().filter(
        (item) => item.ref && !item.disabled,
      );

      if (!enabledTriggers.length) {
        return;
      }

      const target =
        position === "first"
          ? enabledTriggers[0]
          : enabledTriggers[enabledTriggers.length - 1];

      target.ref?.focus();
      onChange(target.value);
    },
    [getOrderedTriggers, onChange],
  );

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        event.preventDefault();
        focusAdjacentTab(1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        event.preventDefault();
        focusAdjacentTab(-1);
        break;
      case "Home":
        event.preventDefault();
        focusBoundaryTab("first");
        break;
      case "End":
        event.preventDefault();
        focusBoundaryTab("last");
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        if (!disabled) {
          onChange(value);
        }
        break;
      default:
        break;
    }
  };

  return (
    <button
      ref={buttonRef}
      type="button"
      role="tab"
      id={tabId}
      aria-selected={isActive}
      aria-controls={panelId}
      tabIndex={isActive ? 0 : -1}
      disabled={disabled}
      onClick={() => {
        if (!disabled) {
          onChange(value);
        }
      }}
      onKeyDown={handleKeyDown}
      className={cn(
        "relative inline-flex items-center justify-center whitespace-nowrap rounded-xl px-3.5 py-1.5 text-xs font-medium tracking-[-0.01em]",
        "transition-[background-color,color,box-shadow] duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]",
        disabled &&
          "cursor-not-allowed opacity-50 hover:bg-transparent hover:text-[var(--text-muted)]",
        !disabled &&
          (isActive
            ? "bg-[var(--accent-muted)] text-[var(--accent-primary)] shadow-sm"
            : "text-[var(--text-muted)] hover:bg-[var(--bg-card)] hover:text-[var(--text-primary)]"),
        className,
      )}
    >
      {children}

      {isActive && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-[var(--accent-primary)]"
        />
      )}
    </button>
  );
};

export const TabsContent: React.FC<TabsContentProps> = ({
  value,
  children,
  className,
}) => {
  const { currentValue, baseId } = useTabsContext("TabsContent");

  const safeId = getSafeId(value);
  const tabId = `${baseId}-tab-${safeId}`;
  const panelId = `${baseId}-panel-${safeId}`;

  if (value !== currentValue) {
    return null;
  }

  return (
    <div
      role="tabpanel"
      id={panelId}
      aria-labelledby={tabId}
      tabIndex={0}
      className={cn("mt-4 outline-none", className)}
    >
      {children}
    </div>
  );
};


