// src/marketing/components/home/ApplicationSection/constants.ts

/** Задержка перед первым reveal (показ заголовка) */
export const INTRO_DELAY_MS = 2500;

/** Сколько панель остаётся active, если пользователь не скроллит */
export const PHASE_AUTO_DURATION_MS = 5000;

/** Границы scroll-progress для каждой фазы */
export const PHASE_THRESHOLDS = {
  intro: 0,
  left: 0.15,
  center: 0.40,
  right: 0.65,
  outro: 0.88,
} as const;




