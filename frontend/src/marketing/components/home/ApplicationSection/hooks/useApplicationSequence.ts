// src/marketing/components/home/ApplicationSection/hooks/useApplicationSequence.ts

import { useState, useEffect, useRef, useCallback } from 'react';
import type { SequenceStep, RoleId, PanelState } from '../types';
import { SEQUENCE_STEP_DURATION, SEQUENCE_START_DELAY } from '../constants';

interface UseApplicationSequenceReturn {
  getPanelState: (id: RoleId) => PanelState;
  onPanelEnter: (id: RoleId) => void;
  onPanelLeave: () => void;
  showTitle: boolean;
}

const SEQUENCE: SequenceStep[] = ['black', 'left', 'center', 'right', 'idle'];

function getRevealedPanels(step: SequenceStep): Set<RoleId> {
  const revealed = new Set<RoleId>();
  const order: RoleId[] = ['left', 'center', 'right'];
  const stepIndex = SEQUENCE.indexOf(step);

  for (let i = 0; i < order.length; i++) {
    if (stepIndex >= i + 1) {
      revealed.add(order[i]);
    }
  }

  return revealed;
}

function getSequenceLead(step: SequenceStep): RoleId | null {
  if (step === 'left' || step === 'center' || step === 'right') return step;
  return null;
}

export function useApplicationSequence(
  isVisible: boolean,
  reducedMotion: boolean,
): UseApplicationSequenceReturn {
  const [step, setStep] = useState<SequenceStep>('black');
  const [hoverTarget, setHoverTarget] = useState<RoleId | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Reset when section leaves viewport, start when it enters
  useEffect(() => {
    if (!isVisible) {
      // Section left viewport — reset everything
      clearTimer();
      setStep('black');
      setHoverTarget(null);
      return;
    }

    // Section entered viewport — start sequence
    if (reducedMotion) {
      setStep('idle');
      return;
    }

    let stepIndex = 0;

    const advance = () => {
      stepIndex++;
      if (stepIndex < SEQUENCE.length) {
        setStep(SEQUENCE[stepIndex]);

        if (SEQUENCE[stepIndex] !== 'idle') {
          timerRef.current = setTimeout(advance, SEQUENCE_STEP_DURATION);
        }
      }
    };

    // Start with delay — show title on black screen first
    timerRef.current = setTimeout(advance, SEQUENCE_START_DELAY);

    return clearTimer;
  }, [isVisible, reducedMotion, clearTimer]);

  // Cleanup on unmount
  useEffect(() => clearTimer, [clearTimer]);

  const onPanelEnter = useCallback((id: RoleId) => {
    setHoverTarget(id);
  }, []);

  const onPanelLeave = useCallback(() => {
    setHoverTarget(null);
  }, []);

  const getPanelState = useCallback(
    (id: RoleId): PanelState => {
      const revealed = getRevealedPanels(step);

      if (!revealed.has(id)) return 'hidden';

      const sequenceLead = getSequenceLead(step);
      const isIdle = step === 'idle';

      if (!isIdle) {
        if (id === sequenceLead) return 'active';
        return 'dormant';
      }

      if (hoverTarget === id) return 'active';
      return 'dormant';
    },
    [step, hoverTarget],
  );

  const showTitle = step === 'black';

  return {
    getPanelState,
    onPanelEnter,
    onPanelLeave,
    showTitle,
  };
}

