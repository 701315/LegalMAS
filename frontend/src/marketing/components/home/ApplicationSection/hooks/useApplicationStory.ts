// src/marketing/components/home/ApplicationSection/hooks/useApplicationStory.ts

import { useEffect, useState, useRef, useCallback } from 'react';
import type { RefObject } from 'react';
import type { PanelState, RoleId, StoryPhase } from '../types';
import {
  INTRO_DELAY_MS,
  PHASE_AUTO_DURATION_MS,
  PHASE_THRESHOLDS,
} from '../constants';

interface UseApplicationStoryReturn {
  phase: StoryPhase;
  getPanelState: (id: RoleId) => PanelState;
  showTitle: boolean;
  showCta: boolean;
}

const PHASE_ORDER: StoryPhase[] = ['intro', 'left', 'center', 'right', 'outro'];

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function phaseFromProgress(progress: number): StoryPhase {
  if (progress >= PHASE_THRESHOLDS.outro) return 'outro';
  if (progress >= PHASE_THRESHOLDS.right) return 'right';
  if (progress >= PHASE_THRESHOLDS.center) return 'center';
  if (progress >= PHASE_THRESHOLDS.left) return 'left';
  return 'intro';
}

function phaseIndex(phase: StoryPhase): number {
  return PHASE_ORDER.indexOf(phase);
}

/** Какие панели уже "раскрыты" на данной фазе */
function getRevealedPanels(phase: StoryPhase): Set<RoleId> {
  const revealed = new Set<RoleId>();
  const idx = phaseIndex(phase);
  if (idx >= 1) revealed.add('left');
  if (idx >= 2) revealed.add('center');
  if (idx >= 3) revealed.add('right');
  return revealed;
}

export function useApplicationStory(
  trackRef: RefObject<HTMLElement | null>,
): UseApplicationStoryReturn {
  const [scrollPhase, setScrollPhase] = useState<StoryPhase>('intro');
  const [timerPhase, setTimerPhase] = useState<StoryPhase>('intro');
  const [isInView, setIsInView] = useState(false);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastScrollProgressRef = useRef(0);
  const userScrolledRef = useRef(false);
  const prevProgressRef = useRef(0);

  // ── Scroll progress tracking ──
  useEffect(() => {
    if (typeof window === 'undefined') return;

    let rafId: number | null = null;

    const update = () => {
      const el = trackRef.current;
      if (!el) return;

      const rect = el.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const totalScrollable = Math.max(el.offsetHeight - viewportHeight, 1);
      const passed = clamp(-rect.top, 0, totalScrollable);
      const progress = clamp(passed / totalScrollable, 0, 1);

      // Определяем, в видимой ли зоне секция
      const sectionInView = rect.top < viewportHeight && rect.bottom > 0;
      setIsInView(sectionInView);

      // Детектируем реальный scroll пользователя
      const delta = Math.abs(progress - prevProgressRef.current);
      if (delta > 0.005) {
        userScrolledRef.current = true;
      }
      prevProgressRef.current = progress;

      lastScrollProgressRef.current = progress;
      setScrollPhase(phaseFromProgress(progress));

      rafId = null;
    };

    const onScroll = () => {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(update);
    };

    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', update);

    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', update);
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [trackRef]);

  // ── Auto-advance timer ──
  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const scheduleNext = useCallback(
    (currentPhase: StoryPhase) => {
      clearTimer();

      const idx = phaseIndex(currentPhase);
      if (idx >= PHASE_ORDER.length - 1) return; // уже outro

      const delay = currentPhase === 'intro' ? INTRO_DELAY_MS : PHASE_AUTO_DURATION_MS;

      timerRef.current = setTimeout(() => {
        const nextPhase = PHASE_ORDER[idx + 1];
        setTimerPhase(nextPhase);
      }, delay);
    },
    [clearTimer],
  );

  // Запуск / сброс таймера
  useEffect(() => {
    if (!isInView) {
      clearTimer();
      setTimerPhase('intro');
      userScrolledRef.current = false;
      return;
    }

    // Если пользователь не скроллил (или scroll progress ≈ 0) — запускаем таймер
    if (!userScrolledRef.current || lastScrollProgressRef.current < 0.02) {
      scheduleNext(timerPhase);
    }

    return clearTimer;
  }, [isInView, timerPhase, scheduleNext, clearTimer]);

  // При scroll — сбрасываем таймер и перезапускаем от текущей scroll-фазы
  useEffect(() => {
    if (userScrolledRef.current && isInView) {
      clearTimer();
      // Перезапускаем таймер от текущей scroll-фазы
      // Это значит: если пользователь остановился, через 5 сек пойдёт следующая
      const restartTimer = setTimeout(() => {
        scheduleNext(scrollPhase);
      }, 300); // небольшая задержка чтобы не дёргать при быстром scroll

      return () => clearTimeout(restartTimer);
    }
  }, [scrollPhase, isInView, clearTimer, scheduleNext]);

  // Очистка при unmount
  useEffect(() => clearTimer, [clearTimer]);

  // ── Итоговая фаза: берём максимальную из scroll и timer ──
  const effectivePhase: StoryPhase = (() => {
    const si = phaseIndex(scrollPhase);
    const ti = phaseIndex(timerPhase);
    return si >= ti ? scrollPhase : timerPhase;
  })();

  // ── Panel state logic ──
  const getPanelState = useCallback(
    (id: RoleId): PanelState => {
      const revealed = getRevealedPanels(effectivePhase);

      if (!revealed.has(id)) return 'hidden';

      // Активная панель — та, что соответствует текущей фазе
      if (effectivePhase === id) return 'active';

      // Outro — все dormant
      if (effectivePhase === 'outro') return 'dormant';

      return 'dormant';
    },
    [effectivePhase],
  );

  return {
    phase: effectivePhase,
    getPanelState,
    showTitle: effectivePhase === 'intro',
    showCta: effectivePhase === 'outro',
  };
}


