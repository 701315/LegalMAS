// src/marketing/components/home/ApplicationSection/constants.ts

/** Задержка перед первым reveal после входа в секцию */
export const INTRO_DELAY_MS = 2500;

/** Сколько панель остаётся active, если пользователь не скроллит */
export const PHASE_AUTO_DURATION_MS = 5000;

/** Через сколько ms после остановки scroll считаем что пользователь не скроллит */
export const SCROLL_IDLE_MS = 180;

/** Границы scroll-progress для фаз */
export const PHASE_THRESHOLDS = {
  intro: 0,
  left: 0.15,
  center: 0.4,
  right: 0.65,
  outro: 0.88,
} as const;






