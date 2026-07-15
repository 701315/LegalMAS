import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import Reveal from '../../motion/Reveal';
import { useContactModal } from "../../context/ContactModalContext";
import { ArrowRight, Database, Target, FileCheck } from "lucide-react";

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const MaDueDiligencePage: React.FC = () => {
  const { openContactModal } = useContactModal();
  const prefersReduced = useReducedMotion();

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1A1917] selection:bg-[var(--color-accent)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        {/* ─── 1. HERO SECTION ────────────────────────────────────────── */}
        <section className="relative overflow-hidden bg-[#FAF8F5]">
          <div
            className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
            style={{ maxWidth: "var(--container-max-width)" }}
          >
            {/* 1.1 PathCrumb — Одна строка */}
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05, ease }}
            >
              <PathCrumb root="Сценарии использования" leaf="M&A и Due Diligence" />
            </motion.div>

            {/* 1.2 Intro Text — Половина ширины (lg:w-1/2) */}
            <motion.div
              className="mt-12 lg:w-1/2"
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.22, ease }}
            >
              <p className="text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)] font-light">
                Минимизируйте объем трудоемкой работы путем оптимизации правового анализа документов, 
                автоматизации извлечения важнейшей правовой информации и выявления ключевых рисков 
                в массивах, насчитывающих тысячи документов.
              </p>
            </motion.div>

            {/* 1.3 Full Width Image — Прямые углы (rounded-none) */}
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 20 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.4, ease }}
              className="mt-16 relative overflow-hidden rounded-none border border-[#E8E4DD] bg-white shadow-sm"
            >
              <img 
                src="/ma-1.png" 
                alt="Due Diligence Infrastructure" 
                className="w-full h-auto object-cover"
              />
            </motion.div>

            {/* 1.4 Large Serif Statement — Паттерн H1 (clamp) */}
            <motion.h1
              className="mt-20 lg:mt-32 font-serif text-[clamp(2.5rem,5vw,4.2rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917] max-w-6xl"
              initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.5, ease }}
            >
              Независимо от языка оригинала или юрисдикции применимого права — <br />
              <span className="italic font-light text-[var(--color-accent)]">
                Steloom обеспечивает единый стандарт качества проверки.
              </span>
            </motion.h1>
          </div>
        </section>

        {/* ─── 2. THREE BLOCKS SECTION ────────────────────────────────── */}
        <section className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
          <div
            className="mx-auto w-full px-6 lg:px-8"
            style={{ maxWidth: "var(--container-max-width)" }}
          >
            <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#E8E4DD]/60">
              
              {/* Блок 1 */}
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center first:pl-0 last:pr-0">
                <Reveal>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40">
                    <Database className="h-12 w-12 text-[var(--color-accent)] opacity-30" />
                  </div>
                  <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                    <strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Объемы и формат</strong>
                    Определяй самостоятельно объемы анализируемой информации. Качество и полнота анализа 
                    не зависит от количества и формата загруженных документов.
                  </p>
                </Reveal>
              </div>

              {/* Блок 2 */}
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center">
                <Reveal delay={0.1}>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40">
                    <Target className="h-12 w-12 text-[var(--color-accent)] opacity-30" />
                  </div>
                  <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                    <strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Акценты и направления</strong>
                    Настраивай сам предмет анализа документов через инструкции. Выявляй как общие для всех документов риски / положения, 
                    так и специфические для конкретных типов.
                  </p>
                </Reveal>
              </div>

              {/* Блок 3 */}
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center last:pr-0">
                <Reveal delay={0.2}>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40">
                    <FileCheck className="h-12 w-12 text-[var(--color-accent)] opacity-30" />
                  </div>
                  <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                    <strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Систематизация данных</strong>
                    Получай результаты в удобном формате (DD grid, реестры) и сохраняй проверяемую связь 
                    каждого вывода с документом-источником.
                  </p>
                </Reveal>
              </div>
            </div>
          </div>
        </section>

        {/* ─── 3. FINAL CTA SECTION (Pattern: SecurityCTA) ──────────────── */}
        <section
          className="relative"
          style={{ background: '#FAF8F5' }}
          data-header-theme="light"
        >
          <div
            className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40"
            style={{ maxWidth: 'var(--container-max-width)' }}
          >
            <Reveal>
              <div
                className="mx-auto flex flex-col items-center text-center"
                style={{ maxWidth: 720 }}
              >
                {/* Верхний тонкий якорь */}
                <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />

                {/* Заголовок — унифицированная шкала clamp */}
                <h2 className="mt-10 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">
                  Steloom не заменяет юридическую экспертизу <br /> 
                  <span className="italic font-light opacity-60 text-[var(--color-accent)]">и не выдает непрозрачные ответы</span>
                </h2>

                {/* Абзацы — Паттерн: 1.0625rem / 1.75 / #78756F */}
                <div className="mt-7 space-y-5" style={{ maxWidth: 620 }}>
                  <p className="text-[1.0625rem] leading-[1.75] text-[#78756F]">
                    Система сокращает ручную работу с документами, помогает не упустить 
                    существенные факты и данные, освобождая время для стратегии.
                  </p>
                  <p className="text-[1.0625rem] leading-[1.75] text-[#78756F]">
                    Загрузите документы сделки — Steloom структурирует data room и поможет 
                    вашей команде сфокусироваться на рисках, которые действительно 
                    влияют на closing, цену и условия сделки.
                  </p>
                </div>

                {/* Одна CTA-кнопка */}
                <div className="mt-10 flex items-center justify-center">
                  <button
                    type="button"
                    onClick={openContactModal}
                    className="cta-primary"
                  >
                    Запросить демонстрацию
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default MaDueDiligencePage;


