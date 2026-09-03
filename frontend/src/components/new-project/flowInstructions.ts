// =============================================================
// src/components/new-project/flowInstructions.ts
//
// Инструкции для правой колонки FlowRightRail.
//
// Тексты (title, description, bullets, iconLabel) хранятся в
// словаре projects.flowInstructions.* и разрешаются на стороне
// UI-компонента через useTranslation("projects"). Здесь мы
// возвращаем только СТРУКТУРУ: icon (компонент lucide) и
// набор i18n-ключей, из которых UI сам собирает текст.
//
// Такой подход:
//   - не тянет useTranslation в файл констант
//   - позволяет компоненту прочитать столько буллетов, сколько
//     реально есть в словаре текущей локали
//   - устраняет хардкод русского текста в исходниках
// =============================================================

import {
  BookOpen,
  Cpu,
  Globe,
  Info,
  Rocket,
  Sparkles,
  Upload,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * Дескриптор одного шага мастера. Все текстовые поля выражены
 * как i18n-ключи внутри namespace "projects".
 */
export interface FlowStepInstructionDescriptor {
  /** i18n-ключ заголовка, например "flowInstructions.step1.title" */
  titleKey: string;
  /** i18n-ключ описания */
  descriptionKey: string;
  /**
   * Префикс i18n-ключей для буллетов. Реальные ключи:
   *   `${bulletsKeyPrefix}.0`, `${bulletsKeyPrefix}.1`, …
   * UI должен читать буллеты, пока t() возвращает не-пустое значение.
   */
  bulletsKeyPrefix: string;
  /** i18n-ключ короткой подписи под иконкой */
  iconLabelKey: string;
  /** Иконка lucide (не переводится) */
  icon: LucideIcon;
}

const NS = "flowInstructions";

// ── Intro: активного шага ещё нет ─────────────────────────
export const FLOW_INTRO: FlowStepInstructionDescriptor = {
  titleKey: `${NS}.intro.title`,
  descriptionKey: `${NS}.intro.description`,
  bulletsKeyPrefix: `${NS}.intro.bullets`,
  iconLabelKey: `${NS}.intro.iconLabel`,
  icon: Sparkles,
};

// ── Инструкции по шагам ────────────────────────────────────
export const FLOW_STEP_INSTRUCTIONS: Record<number, FlowStepInstructionDescriptor> = {
  1: {
    titleKey: `${NS}.step1.title`,
    descriptionKey: `${NS}.step1.description`,
    bulletsKeyPrefix: `${NS}.step1.bullets`,
    iconLabelKey: `${NS}.step1.iconLabel`,
    icon: Info,
  },
  2: {
    titleKey: `${NS}.step2.title`,
    descriptionKey: `${NS}.step2.description`,
    bulletsKeyPrefix: `${NS}.step2.bullets`,
    iconLabelKey: `${NS}.step2.iconLabel`,
    icon: Upload,
  },
  3: {
    titleKey: `${NS}.step3.title`,
    descriptionKey: `${NS}.step3.description`,
    bulletsKeyPrefix: `${NS}.step3.bullets`,
    iconLabelKey: `${NS}.step3.iconLabel`,
    icon: BookOpen,
  },
  4: {
    titleKey: `${NS}.step4.title`,
    descriptionKey: `${NS}.step4.description`,
    bulletsKeyPrefix: `${NS}.step4.bullets`,
    iconLabelKey: `${NS}.step4.iconLabel`,
    icon: Cpu,
  },
  5: {
    titleKey: `${NS}.step5.title`,
    descriptionKey: `${NS}.step5.description`,
    bulletsKeyPrefix: `${NS}.step5.bullets`,
    iconLabelKey: `${NS}.step5.iconLabel`,
    icon: Globe,
  },
  6: {
    titleKey: `${NS}.step6.title`,
    descriptionKey: `${NS}.step6.description`,
    bulletsKeyPrefix: `${NS}.step6.bullets`,
    iconLabelKey: `${NS}.step6.iconLabel`,
    icon: Rocket,
  },
};

/**
 * Возвращает дескриптор инструкции. UI-компонент сам вызовет
 * useTranslation("projects") и подставит переводы.
 */
export function getFlowInstruction(
  activeStep: number | null,
): FlowStepInstructionDescriptor {
  if (activeStep === null) {
    return FLOW_INTRO;
  }
  return FLOW_STEP_INSTRUCTIONS[activeStep] ?? FLOW_INTRO;
}

/**
 * Хелпер: сколько буллетов существует в текущей локали для дескриптора.
 * Читает ключи `${prefix}.0`, `${prefix}.1`, … пока получает валидные строки.
 *
 * @param tFn      — функция t из useTranslation("projects")
 * @param prefix   — bulletsKeyPrefix из дескриптора
 * @param maxCount — верхняя граница на всякий случай (по умолчанию 10)
 * @returns массив локализованных строк-буллетов
 */
export function collectBullets(
  tFn: (key: string, options?: Record<string, unknown>) => string,
  prefix: string,
  maxCount = 10,
): string[] {
  const bullets: string[] = [];
  for (let i = 0; i < maxCount; i++) {
    const key = `${prefix}.${i}`;
    const value = tFn(key, { defaultValue: "" });
    if (!value) {
      break;
    }
    bullets.push(value);
  }
  return bullets;
}


