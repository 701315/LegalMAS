// src/marketing/components/home/ApplicationSection/hooks/useApplicationStory.ts

import { useEffect, useState, useRef, useCallback } from 'react';
import type { RefObject } from 'react';
import type { PanelState, RoleId, StoryPhase } from '../types';
import {
  INTRO_DELAY_MS,
  PHASE_AUTO_DURATION_MS,
  STORY_TOP_OFFSET_PX,
} from '../constants';

interface UseApplicationStoryReturn {
  getPanelState: (id: RoleId) => PanelState;
  showTitle: boolean;
  showCta: boolean;
  onPanelEnter: (id: RoleId) => void;
  onPanelLeave: () => void;
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

function getNextPhase(phase: StoryPhase): StoryPhase | null {
  switch (phase) {
    case 'intro':
      return 'left';
    case 'left':
      return 'center';
    case 'center':
      return 'right';
    case 'right':
      return 'outro';
    default:
      return null;
  }
}

export function useApplicationStory(
  trackRef: RefObject<HTMLElement | null>,
): UseApplicationStoryReturn {
  const [autoPhase, setAutoPhase] = useState<StoryPhase>('intro');
  const [hoveredPanel, setHoveredPanel] = useState<RoleId | null>(null);
  const [isStoryActive, setIsStoryActive] = useState(false);

  const autoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wasActiveRef = useRef(false);

  const clearAutoTimer = useCallback(() => {
    if (autoTimerRef.current !== null) {
      clearTimeout(autoTimerRef.current);
      autoTimerRef.current = null;
    }
  }, []);

  // Определяем, что sticky-сцена реально "включилась"
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

      const stickyStartReached = rect.top <= STORY_TOP_OFFSET_PX + 1;
      const sectionStillPinned = rect.bottom >= viewportHeight;

      setIsStoryActive(stickyStartReached && sectionStillPinned);
      rafId = null;
    };

    const onScroll = () => {
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
    };
  }, [trackRef]);

  // Сброс / старт последовательности
  useEffect(() => {
    if (!isStoryActive) {
      clearAutoTimer();
      setAutoPhase('intro');
      setHoveredPanel(null);
      wasActiveRef.current = false;
      return;
    }

    // если только что вошли в active-zone — стартуем заново
    if (!wasActiveRef.current) {
      setAutoPhase('intro');
      setHoveredPanel(null);
      wasActiveRef.current = true;
    }
  }, [isStoryActive, clearAutoTimer]);

  // Авто-сценарий: intro 3s, далее по 5s на каждую колонку
  useEffect(() => {
    if (!isStoryActive) return;

    // hover полностью ставит авто-сценарий на паузу
    if (hoveredPanel) {
      clearAutoTimer();
      return;
    }

    clearAutoTimer();

    const nextPhase = getNextPhase(autoPhase);
    if (!nextPhase) return;

    const delay =
      autoPhase === 'intro' ? INTRO_DELAY_MS : PHASE_AUTO_DURATION_MS;

    autoTimerRef.current = setTimeout(() => {
      setAutoPhase(nextPhase);
    }, delay);

    return clearAutoTimer;
  }, [isStoryActive, autoPhase, hoveredPanel, clearAutoTimer]);

  useEffect(() => {
    return () => clearAutoTimer();
  }, [clearAutoTimer]);

  const onPanelEnter = useCallback((id: RoleId) => {
    setHoveredPanel(id);
  }, []);

  const onPanelLeave = useCallback(() => {
    setHoveredPanel(null);
  }, []);

  const getPanelState = useCallback(
    (id: RoleId): PanelState => {
      const autoRevealed = getRevealedPanels(autoPhase);

      // Hover override
      if (hoveredPanel) {
        if (id === hoveredPanel) return 'active';
        if (autoRevealed.has(id)) return 'dormant';
        return 'hidden';
      }

      // Авто-сценарий
      if (!autoRevealed.has(id)) return 'hidden';

      if (autoPhase === id) return 'active';

      return 'dormant';
    },
    [autoPhase, hoveredPanel],
  );

  const showTitle = !hoveredPanel && autoPhase === 'intro';
  const showCta = !hoveredPanel && autoPhase === 'outro';

  return {
    getPanelState,
    showTitle,
    showCta,
    onPanelEnter,
    onPanelLeave,
  };
}


