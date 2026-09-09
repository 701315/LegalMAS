import React, { useState } from "react";
import { motion, useReducedMotion, AnimatePresence } from "framer-motion";
import { useTranslation } from "react-i18next";
import Reveal from "../../motion/Reveal";

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
    <div className="border-b border-[var(--border-color)] last:border-b-0">
      {/* ── Trigger ─────────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={contentId}
        // RTL FIX: text-left заменен на text-start
        className="group flex w-full items-baseline justify-between gap-6 py-6 text-start transition-colors lg:py-7"
        style={{ cursor: "pointer" }}
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
            className="text-body font-medium leading-tight tracking-[-0.005em] transition-colors lg:text-lg"
            style={{ color: open ? "#1A1917" : "#1A1917" }}
          >
            {title}
          </span>
        </div>

        {/* Иконка +/− (симметрична, rotate(45deg) работает одинаково хорошо в LTR и RTL) */}
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
            <line x1="7" y1="1" x2="7" y2="13" stroke="#78756F" strokeWidth="1.25" strokeLinecap="round" />
            <line x1="1" y1="7" x2="13" y2="7" stroke="#78756F" strokeWidth="1.25" strokeLinecap="round" />
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
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            style={{ overflow: "hidden" }}
          >
            {/* RTL FIX: ml заменен на ms (margin-start), pr заменен на pe (padding-end) */}
            <ul className="ms-[calc(10px+1.25rem)] space-y-3 pb-7 pe-8 lg:ms-[calc(12px+1.25rem)]">
              {items.map((item, itemIndex) => (
                <li
                  key={itemIndex} // RTL FIX: Используем индекс как стабильный ключ для строк
                  className="flex items-start gap-3 text-[var(--text-secondary)] text-start"
                >
                  <span
                    className="mt-2 flex h-1 w-1 shrink-0 rounded-full bg-[var(--accent-primary)]"
                    aria-hidden="true"
                  />
                  <span className="text-body-sm leading-[1.65]">
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
  const { t } = useTranslation("marketing");

  // RTL FIX: Защита от сбоев при получении массива из i18n
  const groupsRaw = t("platform.technical.groups", { returnObjects: true });
  const groups = Array.isArray(groupsRaw) ? groupsRaw : [];

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
            <div className="eyebrow text-start">{t("platform.technical.eyebrow", "Технические возможности")}</div>

            <h2 className="mt-4 text-h1 text-start">
              {t("platform.technical.title")}
            </h2>

            <p className="mt-5 text-body text-start">
              {t("platform.technical.intro")}
            </p>
          </div>
        </Reveal>

        {/* ── Accordion list ─────────────────────────────────────────── */}
        <Reveal delay={0.1}>
          <div className="mx-auto" style={{ maxWidth: 960 }}>
            {/* Верхний editorial-разделитель */}
            <div className="h-px w-full bg-[#E8E4DD]" aria-hidden="true" />

            {/* Список групп */}
            <div>
              {groups.map((group, i) => (
                <AccordionItem
                  key={i} // RTL FIX: Используем индекс, так как в JSON нет уникальных ID для групп
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

