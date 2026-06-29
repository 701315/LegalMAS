// src/marketing/components/home/ApplicationSection/hooks/useApplicationStory.ts

import { useEffect, useState, useRef, useCallback } from 'react';
import type { RefObject } from 'react';
import type { PanelState, RoleId, StoryPhase } from '../types';
import {
  INTRO_DELAY_MS,
  PHASE_AUTO_DURATION_MS,
  PHASE_THRESHOLDS,
  SCROLL_IDLE_MS,
} from '../constants';

interface UseApplicationStoryReturn {
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

function getNextPhase(phase: StoryPhase): StoryPhase | null {
  const idx = phaseIndex(phase);
  if (idx < 0 || idx >= PHASE_ORDER.length - 1) return null;
  return PHASE_ORDER[idx + 1];
}

function getRevealedPanels(phase: StoryPhase): Set<RoleId> {
  const revealed = new Set<RoleId>();

  if (phase === 'left' || phase === 'center' || phase === 'right' || phase === 'outro') {
    revealed.add('left');
  }

  if (phase === 'center' || phase === 'right' || phase === 'outro') {
    revealed.add('center');
  }

  if (phase === 'right' || phase === 'outro') {
    revealed.add('right');
  }

  return revealed;
}

export function useApplicationStory(
  trackRef: RefObject<HTMLElement | null>,
): UseApplicationStoryReturn {
  const [scrollPhase, setScrollPhase] = useState<StoryPhase>('intro');
  const [autoPhase, setAutoPhase] = useState<StoryPhase>('intro');
  const [isInView, setIsInView] = useState(false);
  const [isUserScrolling, setIsUserScrolling] = useState(false);

  const autoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hadScrollControlRef = useRef(false);

  const clearAutoTimer = useCallback(() => {
    if (autoTimerRef.current !== null) {
      clearTimeout(autoTimerRef.current);
      autoTimerRef.current = null;
    }
  }, []);

  const clearScrollIdleTimer = useCallback(() => {
    if (scrollIdleTimerRef.current !== null) {
      clearTimeout(scrollIdleTimerRef.current);
      scrollIdleTimerRef.current = null;
    }
  }, []);

  const scheduleAutoAdvance = useCallback(
    (fromPhase: StoryPhase) => {
      clearAutoTimer();

      const nextPhase = getNextPhase(fromPhase);
      if (!nextPhase) return;

      const delay =
        fromPhase === 'intro' ? INTRO_DELAY_MS : PHASE_AUTO_DURATION_MS;

      autoTimerRef.current = setTimeout(() => {
        setAutoPhase(nextPhase);
      }, delay);
    },
    [clearAutoTimer],
  );

  // ── Scroll tracking ──
  useEffect(() => {
    if (typeof window === 'undefined') return;

    let rafId: number | null = null;

    const update = () => {
      const el = trackRef.current;
      if (!el) {
        rafId = null;
        return;
      }

      const rect = el.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const totalScrollable = Math.max(el.offsetHeight - viewportHeight, 1);
      const passed = clamp(-rect.top, 0, totalScrollable);
      const progress = clamp(passed / totalScrollable, 0, 1);

      const visible = rect.top < viewportHeight && rect.bottom > 0;
      setIsInView(visible);
      setScrollPhase(phaseFromProgress(progress));

      rafId = null;
    };

    const onScroll = () => {
      setIsUserScrolling(true);
      hadScrollControlRef.current = true;
      clearScrollIdleTimer();

      scrollIdleTimerRef.current = setTimeout(() => {
        setIsUserScrolling(false);
      }, SCROLL_IDLE_MS);

      if (rafId !== null) return;
      rafId = window.requestAnimationFrame(update);
    };

    update();

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', update);

    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', update);
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
      }
      clearScrollIdleTimer();
    };
  }, [trackRef, clearScrollIdleTimer]);

  // ── Reset when section leaves viewport ──
  useEffect(() => {
    if (!isInView) {
      clearAutoTimer();
      clearScrollIdleTimer();
      setIsUserScrolling(false);
      setAutoPhase('intro');
      hadScrollControlRef.current = false;
    }
  }, [isInView, clearAutoTimer, clearScrollIdleTimer]);

  // ── While scrolling: scroll fully controls the story ──
  useEffect(() => {
    if (!isInView) return;

    if (isUserScrolling) {
      clearAutoTimer();
      setAutoPhase(scrollPhase);
    }
  }, [isInView, isUserScrolling, scrollPhase, clearAutoTimer]);

  // ── When user stopped scrolling: continue auto-sequence from current scroll phase ──
  useEffect(() => {
    if (!isInView || isUserScrolling) return;

    if (hadScrollControlRef.current) {
      setAutoPhase(scrollPhase);
      hadScrollControlRef.current = false;
      return;
    }

    scheduleAutoAdvance(autoPhase);

    return clearAutoTimer;
  }, [
    isInView,
    isUserScrolling,
    scrollPhase,
    autoPhase,
    scheduleAutoAdvance,
    clearAutoTimer,
  ]);

  useEffect(() => {
    return () => {
      clearAutoTimer();
      clearScrollIdleTimer();
    };
  }, [clearAutoTimer, clearScrollIdleTimer]);

  const effectivePhase: StoryPhase =
    !isInView ? 'intro' : isUserScrolling ? scrollPhase : autoPhase;

  const getPanelState = useCallback(
    (id: RoleId): PanelState => {
      const revealed = getRevealedPanels(effectivePhase);

      if (!revealed.has(id)) return 'hidden';
      if (effectivePhase === id) return 'active';
      return 'dormant';
    },
    [effectivePhase],
  );

  return {
    getPanelState,
    showTitle: effectivePhase === 'intro',
    showCta: effectivePhase === 'outro',
  };
}


