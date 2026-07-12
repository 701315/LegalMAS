// src/marketing/components/security/SecurityFAQSection.tsx

import React, { useState } from 'react';
import { motion, useReducedMotion, AnimatePresence } from 'framer-motion';
import Reveal from '../../motion/Reveal';
import { faqContent, faqItems } from './content/securityContent';
import type { FAQItem } from './content/securityContent';

/**
 * SecurityFAQSection — editorial FAQ по безопасности.
 *
 * Композиция:
 *   • Editorial-заголовок (serif) + intro-описание
 *   • Disclaimer в компактной панели
 *   • Вертикальный список из 12 раскрывающихся групп
 *   • Каждая группа: номер + вопрос + иконка +/− + внутри ответ и tags
 *   • Все аккордеоны закрыты по умолчанию
 *   • Плавное раскрытие через AnimatePresence
 *
 * Визуальный стиль (идентичен PlatformTechnicalSection):
 *   • Off-white фон (#F3F0EB)
 *   • Тонкие горизонтальные разделители между группами (не карточки)
 *   • Editorial-подача, plus/minus SVG
 *   • max-width 960px для списка
 */

// ─────────────────────────────────────────────────────────────────────────────
// AccordionItem
// ─────────────────────────────────────────────────────────────────────────────

interface AccordionItemProps {
  item: FAQItem;
  index: number;
}

const AccordionItem: React.FC<AccordionItemProps> = ({ item, index }) => {
  const [open, setOpen] = useState(false);
  const shouldReduceMotion = useReducedMotion();

  const contentId = `security-faq-${index}`;

  return (
    <div className="border-b border-[#E8E4DD] last:border-b-0">
      {/* ── Trigger ─────────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={contentId}
        className="group flex w-full items-baseline justify-between gap-6 py-6 text-left transition-colors lg:py-7"
        style={{ cursor: 'pointer' }}
      >
        <div className="flex min-w-0 flex-1 items-baseline gap-5">
          {/* Порядковый номер */}
          <span
            className="shrink-0 text-[10px] font-medium uppercase tracking-[0.22em]"
            style={{ color: '#A8A29E' }}
          >
            {String(index + 1).padStart(2, '0')}
          </span>

          {/* Вопрос */}
          <span
            className="text-[1.0625rem] font-medium leading-tight tracking-[-0.005em] transition-colors lg:text-[1.125rem]"
            style={{ color: '#1A1917' }}
          >
            {item.question}
          </span>
        </div>

        {/* Иконка +/− */}
        <span
          className="relative shrink-0 transition-transform duration-300"
          style={{
            width: 14,
            height: 14,
            transform: open ? 'rotate(45deg)' : 'rotate(0deg)',
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
            animate={shouldReduceMotion ? undefined : { height: 'auto', opacity: 1 }}
            exit={shouldReduceMotion ? undefined : { height: 0, opacity: 0 }}
            transition={{
              duration: 0.35,
              ease: [0.22, 1, 0.36, 1],
            }}
            style={{ overflow: 'hidden' }}
          >
            <div className="ml-[calc(10px+1.25rem)] pb-7 pr-8 lg:ml-[calc(12px+1.25rem)]">
              {/* Ответ */}
              <p className="text-[0.9375rem] leading-[1.75] text-[#78756F]">
                {item.answer}
              </p>

              {/* Tags — review areas */}
              {item.tags && item.tags.length > 0 && (
                <div className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-2">
                  <span className="text-[10px] font-medium uppercase tracking-[0.22em] text-[#A8A29E]">
                    Review areas
                  </span>
                  <span className="text-[#D6D0C7]">·</span>
                  {item.tags.map((tag, i) => (
                    <React.Fragment key={tag}>
                      {i > 0 && <span className="text-[#D6D0C7]">·</span>}
                      <span className="text-[0.8125rem] font-medium text-[#78756F]">
                        {tag}
                      </span>
                    </React.Fragment>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Section
// ─────────────────────────────────────────────────────────────────────────────

const SecurityFAQSection: React.FC = () => {
  return (
    <section
      className="relative"
      style={{ background: '#F3F0EB' }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        {/* ── Header ─────────────────────────────────────────────────── */}
        <Reveal>
          <div className="mb-10 max-w-3xl lg:mb-14">
            <div className="eyebrow">{faqContent.eyebrow}</div>

            {/* ✅ Заголовок — унифицированная шкала */}
            <h2 className="mt-4 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">
              {faqContent.title.split('\n').map((line, i) => (
                <React.Fragment key={i}>
                  {i > 0 && <br />}
                  {line}
                </React.Fragment>
              ))}
            </h2>

            <p className="mt-5 text-[1rem] leading-[1.75] text-[#78756F]">
              {faqContent.description}
            </p>
          </div>
        </Reveal>

        {/* ── Disclaimer ─────────────────────────────────────────────── */}
        <Reveal delay={0.05}>
          <div
            className="mx-auto mb-14 lg:mb-20"
            style={{ maxWidth: 960 }}
          >
            <div className="border-l-2 border-[#D6D0C7] pl-5 py-2">
              <p className="text-[0.8125rem] leading-[1.7] text-[#A8A29E]">
                {faqContent.disclaimer}
              </p>
            </div>
          </div>
        </Reveal>

        {/* ── Accordion list ─────────────────────────────────────────── */}
        <Reveal delay={0.1}>
          <div className="mx-auto" style={{ maxWidth: 960 }}>
            {/* Верхний editorial-разделитель */}
            <div className="h-px w-full bg-[#E8E4DD]" aria-hidden="true" />

            {/* Список групп */}
            <div>
              {faqItems.map((item, i) => (
                <AccordionItem key={item.number} item={item} index={i} />
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
};

export default SecurityFAQSection;


