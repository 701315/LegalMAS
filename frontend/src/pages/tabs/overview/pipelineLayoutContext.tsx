// =============================================================
// src/pages/tabs/overview/pipelineLayoutContext.tsx
//
// Общий store координат этапов pipeline для двух представлений:
//   - expanded  (DocumentsPipelinePanel + PipelineStepCard)
//   - collapsed (CollapsedPipelineSummary)
//
// Задача: в collapsed rail иконки этапов должны стоять на тех же
// y-координатах, что и шапки соответствующих карточек в expanded.
//
// Ключевое архитектурное решение: координаты в store хранятся
// как offsets ОТ ПЕРВОЙ КАРТОЧКИ, а не от контейнера. Это делает
// координаты переносимыми между expanded и collapsed режимами:
// у первой иконки всегда y = 0, у остальных — реальная дельта
// от первой карточки в expanded. Отсутствие зависимости от
// родительских header'ов, padding'ов и обёрток обеспечивает
// стабильное попадание при переключении режимов.
//
// Реализация: все PipelineStepCard регистрируют свои refs
// в родительском PipelineLayoutProvider. Один общий
// ResizeObserver в провайдере измеряет все карточки одновременно
// через getBoundingClientRect и вычисляет дельты. Это гарантирует
// консистентность: все top-координаты измерены в один и тот же
// момент, из одной и той же layout-фазы браузера.
// =============================================================

import React from "react";

export interface StepLayoutEntry {
  /** Offset верха карточки от верха первой карточки, px */
  top: number;
  /** Высота карточки, px */
  height: number;
}

export interface PipelineLayoutState {
  /** step.code → координаты (относительно первой карточки) */
  entries: Record<string, StepLayoutEntry>;
  /** Порядок step.code в том виде, как они рендерились в expanded */
  order: string[];
}

interface PipelineLayoutContextValue {
  layout: PipelineLayoutState;
  /**
   * Регистрирует ref карточки для данного step.code.
   * Ref может держать null (стандартная React-семантика), пока
   * элемент не смонтирован. Возвращает cleanup-функцию.
   */
  registerCardRef: (
    code: string,
    ref: React.RefObject<HTMLElement | null>,
  ) => () => void;
  /**
   * Обновляет порядок этапов (вызывается expanded-view при рендере).
   * Идемпотентно.
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
 * Provider со встроенным ref-регистри и батч-измерением.
 *
 * cardsRef хранит текущие refs всех зарегистрированных карточек.
 * Один общий ResizeObserver слушает изменения размеров любой
 * карточки и триггерит remeasure всех сразу. Это гарантирует,
 * что координаты в store всегда взяты из одной layout-фазы.
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
   * Пересчитывает координаты всех карточек через getBoundingClientRect
   * и обновляет store, если координаты реально изменились.
   *
   * Координаты вычисляются как дельта от первой карточки в текущем
   * порядке (orderRef или порядок из cardsRef, если order ещё не
   * зарегистрирован).
   */
  const remeasure = React.useCallback(() => {
    const cards = cardsRef.current;
    if (cards.size === 0) return;

    // Определяем порядок: order из expanded имеет приоритет,
    // иначе — порядок вставки в Map (соответствует порядку рендера).
    const order = orderRef.current.length > 0
      ? orderRef.current
      : Array.from(cards.keys());

    // Ищем первую карточку с реально смонтированным элементом.
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
      // Проверяем, реально ли изменились координаты.
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

  // Общий ResizeObserver создаётся один раз на жизнь провайдера.
  React.useEffect(() => {
    observerRef.current = new ResizeObserver(() => {
      // requestAnimationFrame защищает от ResizeObserver loop errors:
      // remeasure триггерит setState → ререндер → возможные новые
      // изменения размеров. rAF гарантирует, что измерения происходят
      // после завершения текущей layout-фазы.
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

      // Подписываемся на изменения размеров этой карточки.
      const el = ref.current;
      if (el && observerRef.current) {
        observerRef.current.observe(el);
      }

      // Триггерим измерение сразу после регистрации,
      // чтобы координаты появились в store как можно раньше.
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
 * Хук для PipelineStepCard: регистрирует ref карточки в общем
 * ref-регистри и автоматически снимает регистрацию при unmount.
 *
 * Ref принимается с `HTMLElement | null` в generic — стандартная
 * React-семантика для DOM-ref, чей current может быть null до
 * первого рендера или после unmount.
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


