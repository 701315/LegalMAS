// src/marketing/motion/Reveal.tsx

import React from "react";
import { motion, useReducedMotion, type Variants } from "framer-motion";

/**
 * Reveal — универсальная обёртка для плавного появления элементов при скролле.
 *
 * Используется во всех секциях страницы Platform (и может применяться в других
 * маркетинговых страницах). Реализует единый и очень сдержанный паттерн:
 *   • opacity 0 → 1
 *   • translateY +y → 0
 *
 * Никаких bounce, spring, rotate, scale — в соответствии с брифом.
 *
 * Дополнительно:
 *   • Уважает системную настройку `prefers-reduced-motion` — если пользователь
 *     отключил анимации, элемент появляется мгновенно без движения.
 *   • Срабатывает один раз при первом попадании в viewport (`once: true`).
 *   • Поддерживает stagger через children: <Reveal stagger> оборачивает
 *     детей в motion-контекст, где каждый прямой ребёнок появляется
 *     с задержкой относительно предыдущего.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Типы
// ─────────────────────────────────────────────────────────────────────────────

interface RevealProps {
  children: React.ReactNode;
  /**
   * Смещение по Y в пикселях, с которого начинается анимация.
   * По умолчанию 12 — очень деликатное появление.
   */
  y?: number;
  /**
   * Длительность анимации в секундах.
   */
  duration?: number;
  /**
   * Задержка перед стартом.
   */
  delay?: number;
  /**
   * Если true — включает stagger-режим: обёртка становится motion-контейнером,
   * а прямые дети должны быть <RevealItem />, чтобы получить последовательное
   * появление.
   */
  stagger?: boolean;
  /**
   * Задержка между появлениями дочерних RevealItem (только при stagger=true).
   * По умолчанию 0.08с — плавный «поток».
   */
  staggerDelay?: number;
  /**
   * HTML-тег обёртки. По умолчанию div.
   */
  as?: "div" | "section" | "article" | "header" | "footer" | "ul" | "ol";
  /**
   * className для обёртки.
   */
  className?: string;
  /**
   * Отступ viewport для более раннего/позднего срабатывания.
   * По умолчанию "-80px" — секция начинает появляться, немного не доходя
   * до нижнего края экрана.
   */
  margin?: `${number}px` | `-${number}px`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Варианты анимации
// ─────────────────────────────────────────────────────────────────────────────

const buildVariants = (y: number, duration: number, delay: number): Variants => ({
  hidden: {
    opacity: 0,
    y,
  },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration,
      delay,
      ease: [0.22, 1, 0.36, 1], // мягкая easeOutQuart-подобная кривая
    },
  },
});

const buildContainerVariants = (staggerDelay: number): Variants => ({
  hidden: {},
  visible: {
    transition: {
      staggerChildren: staggerDelay,
      delayChildren: 0.05,
    },
  },
});

// ─────────────────────────────────────────────────────────────────────────────
// Reveal
// ─────────────────────────────────────────────────────────────────────────────

const Reveal: React.FC<RevealProps> = ({
  children,
  y = 12,
  duration = 0.55,
  delay = 0,
  stagger = false,
  staggerDelay = 0.08,
  as = "div",
  className,
  margin = "-80px",
}) => {
  const shouldReduceMotion = useReducedMotion();

  // Если пользователь предпочитает reduced motion — рендерим обычный элемент
  // без Framer Motion. Это дешевле и полностью соответствует ожиданиям.
  if (shouldReduceMotion) {
    const Tag = as;
    return <Tag className={className}>{children}</Tag>;
  }

  const MotionTag = motion[as] as React.ComponentType<
    React.ComponentPropsWithoutRef<typeof motion.div>
  >;

  if (stagger) {
    return (
      <MotionTag
        className={className}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin }}
        variants={buildContainerVariants(staggerDelay)}
      >
        {children}
      </MotionTag>
    );
  }

  return (
    <MotionTag
      className={className}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin }}
      variants={buildVariants(y, duration, delay)}
    >
      {children}
    </MotionTag>
  );
};

export default Reveal;

// ─────────────────────────────────────────────────────────────────────────────
// RevealItem
// ─────────────────────────────────────────────────────────────────────────────

interface RevealItemProps {
  children: React.ReactNode;
  y?: number;
  duration?: number;
  as?: "div" | "li" | "article" | "section";
  className?: string;
}

/**
 * RevealItem — дочерний элемент для использования внутри <Reveal stagger>.
 * Получает варианты из родительского motion-контекста автоматически
 * (Framer Motion наследует variants через контекст).
 */
export const RevealItem: React.FC<RevealItemProps> = ({
  children,
  y = 10,
  duration = 0.5,
  as = "div",
  className,
}) => {
  const shouldReduceMotion = useReducedMotion();

  if (shouldReduceMotion) {
    const Tag = as;
    return <Tag className={className}>{children}</Tag>;
  }

  const MotionTag = motion[as] as React.ComponentType<
    React.ComponentPropsWithoutRef<typeof motion.div>
  >;

  return (
    <MotionTag
      className={className}
      variants={{
        hidden: { opacity: 0, y },
        visible: {
          opacity: 1,
          y: 0,
          transition: {
            duration,
            ease: [0.22, 1, 0.36, 1],
          },
        },
      }}
    >
      {children}
    </MotionTag>
  );
};


