// src/marketing/components/security/SecurityFAQSection.tsx
import React, { useState } from 'react';
import { motion, useReducedMotion, AnimatePresence } from 'framer-motion';
import Reveal from '../../motion/Reveal';
import { useTranslation } from 'react-i18next';

interface FAQItem {
  number: string;
  question: string;
  answer: string;
  tags?: string[];
}

interface AccordionItemProps {
  item: FAQItem;
  index: number;
  reviewAreasLabel: string;
}

const AccordionItem: React.FC<AccordionItemProps> = ({ item, index, reviewAreasLabel }) => {
  const [open, setOpen] = useState(false);
  const shouldReduceMotion = useReducedMotion();
  const contentId = `security-faq-${index}`;

  return (
    <div className="border-b border-[var(--border-color)] last:border-b-0">
      {/* ── Trigger ─────────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={contentId}
        // RTL FIX: text-left заменен на text-start
        className="group flex w-full items-baseline justify-between gap-6 py-6 text-start transition-colors lg:py-7"
        style={{ cursor: 'pointer' }}
      >
        <div className="flex min-w-0 flex-1 items-baseline gap-5">
          <span
            className="shrink-0 text-meta font-medium uppercase"
            style={{ color: '#A8A29E' }}
          >
            {item.number}
          </span>

          <span
            className="text-body font-medium leading-tight transition-colors lg:text-lg"
            style={{ color: '#1A1917' }}
          >
            {item.question}
          </span>
        </div>

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
            <line x1="7" y1="1" x2="7" y2="13" stroke="#78756F" strokeWidth="1.25" strokeLinecap="round" />
            <line x1="1" y1="7" x2="13" y2="7" stroke="#78756F" strokeWidth="1.25" strokeLinecap="round" />
          </svg>
        </span>
      </button>

      {/* ── Content ───────────────────────────────────────────────────── */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={contentId}
            key="content"
            initial={shouldReduceMotion ? undefined : { height: 0, opacity: 0 }}
            animate={shouldReduceMotion ? undefined : { height: 'auto', opacity: 1 }}
            exit={shouldReduceMotion ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            style={{ overflow: 'hidden' }}
          >
            {/* RTL FIX: ml заменен на ms (margin-start), pr на pe (padding-end) */}
            <div className="ms-[calc(10px+1.25rem)] pb-7 pe-8 lg:ms-[calc(12px+1.25rem)]">
              <p className="text-body-sm leading-relaxed text-[var(--text-secondary)]">
                {item.answer}
              </p>

              {item.tags && item.tags.length > 0 && (
                <div className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-2">
                  <span className="text-meta font-medium uppercase text-[var(--text-muted)]">
                    {reviewAreasLabel}
                  </span>
                  <span className="text-[var(--text-faint)]">·</span>
                  {item.tags.map((tag, i) => (
                    <React.Fragment key={tag}>
                      {i > 0 && <span className="text-[var(--text-faint)]">·</span>}
                      <span className="text-eyebrow font-medium text-[var(--text-secondary)]">
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
  const { t } = useTranslation('security');

  const faqContent = {
    eyebrow: t('faq.eyebrow'),
    title: t('faq.title'),
    description: t('faq.description'),
    disclaimer: t('faq.disclaimer'),
    reviewAreasLabel: t('faq.reviewAreasLabel'),
  };

  // Защитная проверка массива
  const faqItemsRaw = t('faq.items', { returnObjects: true });
  const faqItems = Array.isArray(faqItemsRaw) ? faqItemsRaw : [];

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

            {/* ✅ Заголовок — используем whitespace-pre-line */}
            <h2 className="mt-4 text-h1 whitespace-pre-line">
              {faqContent.title}
            </h2>

            <p className="mt-5 text-body">
              {faqContent.description}
            </p>
          </div>
        </Reveal>

        {/* ── Disclaimer ─────────────────────────────────────────────── */}
        <Reveal delay={0.05}>
          <div className="mx-auto mb-14 lg:mb-20" style={{ maxWidth: 960 }}>
            {/* RTL FIX: border-l-2, pl-5 заменены на border-s-2, ps-5 */}
            <div className="border-s-2 border-[#D6D0C7] ps-5 py-2">
              <p className="text-eyebrow leading-relaxed text-[var(--text-muted)]">
                {faqContent.disclaimer}
              </p>
            </div>
          </div>
        </Reveal>

        {/* ── Accordion list ─────────────────────────────────────────── */}
        <Reveal delay={0.1}>
          <div className="mx-auto" style={{ maxWidth: 960 }}>
            <div className="h-px w-full bg-[#E8E4DD]" aria-hidden="true" />

            <div>
              {faqItems.map((item, i) => (
                <AccordionItem 
                  key={item.number} 
                  item={item} 
                  index={i} 
                  reviewAreasLabel={faqContent.reviewAreasLabel}
                />
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
};

export default SecurityFAQSection;