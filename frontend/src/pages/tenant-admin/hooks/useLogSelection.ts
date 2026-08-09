import React from "react";

// ─────────────────────────────────────────────
// Generic selection hook
// ─────────────────────────────────────────────

export function useLogSelection(deps: React.DependencyList = []) {
  const [selectedLogIdx, setSelectedLogIdx] = React.useState<number | null>(
    null,
  );

  React.useEffect(() => {
    setSelectedLogIdx(null);
  }, deps);

  return {
    selectedLogIdx,
    setSelectedLogIdx,
  };
}

// ─────────────────────────────────────────────
// Copy hook
// ─────────────────────────────────────────────

export function useLogCopy<T>(getValue: () => T | null) {
  const [copied, setCopied] = React.useState(false);
  const copyTimer = React.useRef<number | null>(null);

  React.useEffect(() => {
    return () => {
      if (copyTimer.current !== null) {
        window.clearTimeout(copyTimer.current);
      }
    };
  }, []);

  const handleCopy = async () => {
    const value = getValue();
    if (!value) return;

    try {
      await navigator.clipboard.writeText(
        JSON.stringify(value, null, 2),
      );
      setCopied(true);

      if (copyTimer.current !== null) {
        window.clearTimeout(copyTimer.current);
      }

      copyTimer.current = window.setTimeout(() => {
        setCopied(false);
      }, 1800);
    } catch {
      // noop
    }
  };

  return {
    copied,
    handleCopy,
  };
}

// ─────────────────────────────────────────────
// Domain-specific helper
// ─────────────────────────────────────────────

export function useLogsSelectionWithReset(
  resetDeps: React.DependencyList,
) {
  return useLogSelection(resetDeps);
}


