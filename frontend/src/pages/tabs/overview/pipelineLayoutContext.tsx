// =============================================================
// src/pages/tabs/overview/pipelineLayoutContext.tsx
//
// Shared store for pipeline step coordinates used by two views:
//   - expanded  (DocumentsPipelinePanel + PipelineStepCard)
//   - collapsed (CollapsedPipelineSummary)
//
// Goal: In collapsed rail, step icons must align at the same
// y-coordinates as the corresponding card headers in expanded view.
//
// Key architectural decision: coordinates in store are stored
// as offsets FROM THE FIRST CARD, not from the container. This
// makes coordinates portable between expanded and collapsed modes:
// the first icon always has y = 0, others have the real delta
// from the first card in expanded view. Independence from parent
// headers, padding, and wrappers ensures stable alignment when
// switching modes.
//
// Implementation: all PipelineStepCard components register their refs
// in the parent PipelineLayoutProvider. A single shared ResizeObserver
// in the provider measures all cards simultaneously via
// getBoundingClientRect and computes deltas. This guarantees
// consistency: all top-coordinates are measured at the same moment,
// from the same browser layout phase.
// =============================================================

import React from "react";

export interface StepLayoutEntry {
  /** Offset of card top from the first card top, in pixels */
  top: number;
  /** Card height in pixels */
  height: number;
}

export interface PipelineLayoutState {
  /** step.code → coordinates (relative to the first card) */
  entries: Record<string, StepLayoutEntry>;
  /** Order of step.code as rendered in expanded view */
  order: string[];
}

interface PipelineLayoutContextValue {
  layout: PipelineLayoutState;
  /**
   * Registers a card ref for the given step.code.
   * Ref may hold null (standard React semantics) until
   * the element is mounted. Returns a cleanup function.
   */
  registerCardRef: (
    code: string,
    ref: React.RefObject<HTMLElement | null>,
  ) => () => void;
  /**
   * Updates step order (called by expanded-view during render).
   * Idempotent.
   */
  reportOrder: (order: string[]) => void;
}

const NOOP_CTX: PipelineLayoutContextValue = {
  layout: { entries: {}, order: [] },
  registerCardRef: () => () => {},
  reportOrder: () => {},
};

const PipelineLayoutContext =
  React.createContext<PipelineLayoutContextValue>(NOOP_CTX);

/**
 * Provider with built-in ref registry and batch measurement.
 *
 * cardsRef holds current refs of all registered cards.
 * A single shared ResizeObserver listens for size changes on any
 * card and triggers remeasure of all at once. This guarantees
 * that coordinates in store are always captured from the same layout phase.
 */
export const PipelineLayoutProvider: React.FC<{
  children: React.ReactNode;
}> = ({ children }) => {
  const [layout, setLayout] = React.useState<PipelineLayoutState>({
    entries: {},
    order: [],
  });

  const cardsRef = React.useRef<
    Map<string, React.RefObject<HTMLElement | null>>
  >(new Map());
  const orderRef = React.useRef<string[]>([]);
  const observerRef = React.useRef<ResizeObserver | null>(null);

  /**
   * Recalculates coordinates for all cards via getBoundingClientRect
   * and updates store only if coordinates have actually changed.
   *
   * Coordinates are computed as delta from the first card in current
   * order (orderRef or insertion order from cardsRef if order not yet registered).
   */
  const remeasure = React.useCallback(() => {
    const cards = cardsRef.current;
    if (cards.size === 0) return;

    // Determine order: order from expanded has priority,
    // otherwise insertion order from Map (matches render order).
    const order = orderRef.current.length > 0
      ? orderRef.current
      : Array.from(cards.keys());

    // Find the first card with an actually mounted element.
    let firstTop: number | null = null;
    for (const code of order) {
      const el = cards.get(code)?.current;
      if (el) {
        const rect = el.getBoundingClientRect();
        if (rect.height > 0) {
          firstTop = rect.top;
          break;
        }
      }
    }
    if (firstTop === null) return;

    const nextEntries: Record<string, StepLayoutEntry> = {};
    for (const code of order) {
      const el = cards.get(code)?.current;
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      if (rect.height === 0) continue;
      nextEntries[code] = {
        top: rect.top - firstTop,
        height: rect.height,
      };
    }

    setLayout((prev) => {
      // Check if coordinates have actually changed.
      const prevKeys = Object.keys(prev.entries);
      const nextKeys = Object.keys(nextEntries);
      let changed = prevKeys.length !== nextKeys.length;

      if (!changed) {
        for (const key of nextKeys) {
          const p = prev.entries[key];
          const n = nextEntries[key];
          if (
            !p ||
            Math.abs(p.top - n.top) > 0.5 ||
            Math.abs(p.height - n.height) > 0.5
          ) {
            changed = true;
            break;
          }
        }
      }

      if (!changed) return prev;
      return {
        entries: nextEntries,
        order: prev.order,
      };
    });
  }, []);

  // Single ResizeObserver created once for provider lifetime.
  React.useEffect(() => {
    observerRef.current = new ResizeObserver(() => {
      // requestAnimationFrame protects from ResizeObserver loop errors:
      // remeasure triggers setState → re-render → potential new
      // size changes. rAF guarantees measurements occur after
      // current layout phase completes.
      window.requestAnimationFrame(remeasure);
    });
    return () => {
      observerRef.current?.disconnect();
      observerRef.current = null;
    };
  }, [remeasure]);

  const registerCardRef = React.useCallback(
    (code: string, ref: React.RefObject<HTMLElement | null>) => {
      cardsRef.current.set(code, ref);

      // Subscribe to size changes for this card.
      const el = ref.current;
      if (el && observerRef.current) {
        observerRef.current.observe(el);
      }

      // Trigger measurement immediately after registration
      // so coordinates appear in store as early as possible.
      window.requestAnimationFrame(remeasure);

      return () => {
        cardsRef.current.delete(code);
        if (el && observerRef.current) {
          observerRef.current.unobserve(el);
        }
        window.requestAnimationFrame(remeasure);
      };
    },
    [remeasure],
  );

  const reportOrder = React.useCallback(
    (order: string[]) => {
      const prev = orderRef.current;
      if (
        prev.length === order.length &&
        prev.every((code, i) => code === order[i])
      ) {
        return;
      }
      orderRef.current = order;
      setLayout((prev) => ({
        entries: prev.entries,
        order,
      }));
      window.requestAnimationFrame(remeasure);
    },
    [remeasure],
  );

  const value = React.useMemo<PipelineLayoutContextValue>(
    () => ({ layout, registerCardRef, reportOrder }),
    [layout, registerCardRef, reportOrder],
  );

  return (
    <PipelineLayoutContext.Provider value={value}>
      {children}
    </PipelineLayoutContext.Provider>
  );
};

export function usePipelineLayout(): PipelineLayoutContextValue {
  return React.useContext(PipelineLayoutContext);
}

/**
 * Hook for PipelineStepCard: registers card ref in shared
 * ref registry and automatically unregisters on unmount.
 *
 * Ref accepts `HTMLElement | null` in generic — standard
 * React semantics for DOM-ref whose current may be null before
 * first render or after unmount.
 */
export function usePipelineStepCardRegistration(
  code: string,
  ref: React.RefObject<HTMLElement | null>,
): void {
  const { registerCardRef } = usePipelineLayout();

  React.useEffect(() => {
    const cleanup = registerCardRef(code, ref);
    return cleanup;
  }, [code, ref, registerCardRef]);
}


