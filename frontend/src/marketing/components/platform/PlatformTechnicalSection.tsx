// src/marketing/components/platform/PlatformTechnicalSection.tsx

import React, { useState } from "react";
import { motion, useReducedMotion, AnimatePresence } from "framer-motion";
import Reveal from "../../motion/Reveal";
import { TECHNICAL_CONTENT } from "./content/platformContent";

/**
 * PlatformTechnicalSection — финальная секция страницы Platform.
 *
 * Композиция:
 *   • Editorial-заголовок (serif, крупный) + сдержанное intro-описание
 *   • Ниже — вертикальный список из 11 раскрывающихся групп
 *   • Каждая группа: заголовок + иконка +/− + внутри bullets
 *   • Все аккордеоны закрыты по умолчанию
 *   • Плавное раскрытие через AnimatePresence (opacity + height)
 *
 * Позиция: ПОСЛЕДНЯЯ секция страницы перед footer.
 *
 * Визуальный стиль:
 *   • Off-white фон (#F3F0EB) — контраст с CTA (белый) сверху
 *   • Тонкие горизонтальные разделители между группами (не карточки)
 *   • Editorial-подача: без иконок в bullets, только тонкие точки
 *   • Плюс/минус — простой SVG, не lucide (полный контроль стиля)
 *
 * Смысловая роль:
 *   Технический deep-dive для читателя, который прошёл всю страницу
 *   и хочет узнать детали. НЕ в верхних секциях — там смысловая
 *   архитектура, здесь — техническая полнота.
 */

// ─────────────────────────────────────────────────────────────────────────────
// AccordionItem — одна раскрывающаяся группа
// ─────────────────────────────────────────────────────────────────────────────

interface AccordionItemProps {
  title: string;
  items: string[];
  index: number;
}

const AccordionItem: React.FC<AccordionItemProps> = ({ title, items, index }) => {
  const [open, setOpen] = useState(false);
  const shouldReduceMotion = useReducedMotion();

  const contentId = `technical-accordion-${index}`;

  return (
    <div className="border-b border-[#E8E4DD] last:border-b-0">
      {/* ── Trigger ─────────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={contentId}
        className="group flex w-full items-baseline justify-between gap-6 py-6 text-left transition-colors lg:py-7"
        style={{
          cursor: "pointer",
        }}
      >
        <div className="flex items-baseline gap-5 min-w-0 flex-1">
          {/* Порядковый номер */}
          <span
            className="text-[10px] font-medium uppercase tracking-[0.22em] shrink-0"
            style={{ color: "#A8A29E" }}
          >
            {String(index + 1).padStart(2, "0")}
          </span>

          {/* Заголовок */}
          <span
            className="text-[1.0625rem] font-medium leading-tight tracking-[-0.005em] transition-colors lg:text-[1.125rem]"
            style={{ color: open ? "#1A1917" : "#1A1917" }}
          >
            {title}
          </span>
        </div>

        {/* Иконка +/− */}
        <span
          className="relative shrink-0 transition-transform duration-300"
          style={{
            width: 14,
            height: 14,
            transform: open ? "rotate(45deg)" : "rotate(0deg)",
          }}
          aria-hidden="true"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <line
              x1="7"
              y1="1"
              x2="7"
              y2="13"
              stroke="#78756F"
              strokeWidth="1.25"
              strokeLinecap="round"
            />
            <line
              x1="1"
              y1="7"
              x2="13"
              y2="7"
              stroke="#78756F"
              strokeWidth="1.25"
              strokeLinecap="round"
            />
          </svg>
        </span>
      </button>

      {/* ── Content — раскрывающийся блок ───────────────────────────── */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={contentId}
            key="content"
            initial={shouldReduceMotion ? undefined : { height: 0, opacity: 0 }}
            animate={shouldReduceMotion ? undefined : { height: "auto", opacity: 1 }}
            exit={shouldReduceMotion ? undefined : { height: 0, opacity: 0 }}
            transition={{
              duration: 0.35,
              ease: [0.22, 1, 0.36, 1],
            }}
            style={{ overflow: "hidden" }}
          >
            <ul className="ml-[calc(10px+1.25rem)] space-y-3 pb-7 pr-8 lg:ml-[calc(12px+1.25rem)]">
              {items.map((item) => (
                <li
                  key={item}
                  className="flex items-start gap-3 text-[#78756F]"
                >
                  <span
                    className="mt-2 flex h-1 w-1 shrink-0 rounded-full bg-[#C86B52]"
                    aria-hidden="true"
                  />
                  <span className="text-[0.9375rem] leading-[1.65]">
                    {item}
                  </span>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Section
// ─────────────────────────────────────────────────────────────────────────────

const PlatformTechnicalSection: React.FC = () => {
  return (
    <section
      className="relative"
      style={{ background: "#F3F0EB" }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        {/* ── Header ─────────────────────────────────────────────────── */}
        <Reveal>
          <div className="mb-14 max-w-3xl lg:mb-20">
            <div className="eyebrow">Технические возможности</div>

            <h2 className="mt-4 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">              {TECHNICAL_CONTENT.title}
            </h2>

            <p className="mt-5 text-[1rem] leading-[1.75] text-[#78756F]">
              {TECHNICAL_CONTENT.intro}
            </p>
          </div>
        </Reveal>

        {/* ── Accordion list ─────────────────────────────────────────── */}
        <Reveal delay={0.1}>
          <div
            className="mx-auto"
            style={{ maxWidth: 960 }}
          >
            {/* Верхний editorial-разделитель */}
            <div className="h-px w-full bg-[#E8E4DD]" aria-hidden="true" />

            {/* Список групп */}
            <div>
              {TECHNICAL_CONTENT.groups.map((group, i) => (
                <AccordionItem
                  key={group.title}
                  title={group.title}
                  items={group.items}
                  index={i}
                />
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
};

export default PlatformTechnicalSection;



