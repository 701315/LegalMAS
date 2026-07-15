import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import Reveal from '../../motion/Reveal';
import { useContactModal } from "../../context/ContactModalContext";
import { ArrowRight, Library, AlertTriangle, Link as LinkIcon } from "lucide-react";

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const ContractReviewPage: React.FC = () => {
  const { openContactModal } = useContactModal();
  const prefersReduced = useReducedMotion();

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1A1917] selection:bg-[var(--color-accent)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        {/* ─── 1. HERO SECTION (Split 1/3 vs 2/3) ──────────────────────── */}
        <section className="relative overflow-hidden bg-[#FAF8F5]">
          <div
            className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
            style={{ maxWidth: "var(--container-max-width)" }}
          >
            {/* 1.1 PathCrumb */}
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05, ease }}
              className="mb-12 lg:mb-16"
            >
              <PathCrumb root="Сценарии использования" leaf="Анализ договоров" />
            </motion.div>

            {/* 1.2 Grid Layout: Текст (1/3) и Картинка (2/3) */}
            <div className="grid gap-12 lg:grid-cols-12 lg:gap-16 items-start">
              
              {/* Левая колонка (1/3) */}
              <div className="lg:col-span-4">
                <motion.div
                  initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
                  animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
                  transition={{ duration: 0.55, delay: 0.22, ease }}
                >
                  <p className="text-[1.0625rem] leading-[1.75] text-[var(--text-secondary)] font-light">
                    Оптимизируйте процесс проверки договорного массива, обеспечивая автоматическое 
                    выявление отклонений от корпоративных стандартов и минимизацию рисков 
                    ручного анализа в условиях сжатых сроков и больших объемов данных.
                  </p>
                  
                  <div className="pt-8">
                    <button onClick={openContactModal} className="cta-primary">
                      Запросить демо
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </motion.div>
              </div>

              {/* Правая колонка (2/3) — Картинка cr-1.jpg */}
              <div className="lg:col-span-8">
                <motion.div
                  initial={prefersReduced ? undefined : { opacity: 0, y: 20 }}
                  animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
                  transition={{ duration: 0.8, delay: 0.4, ease }}
                  className="relative overflow-hidden rounded-none border border-[#E8E4DD] bg-white shadow-sm"
                >
                  <img 
                    src="/cr-1.jpg" 
                    alt="Contract Review Workspace" 
                    className="w-full h-auto object-cover"
                  />
                </motion.div>
              </div>
            </div>

            {/* 1.3 Large Serif Statement */}
            <motion.h1
              className="mt-20 lg:mt-32 font-serif text-[clamp(2.5rem,5vw,4.2rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917] max-w-6xl"
              initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.6, ease }}
            >
              Каждое положение договора — <br />
              <span className="italic font-light text-[var(--color-accent)]">
                под полным контролем вашей методологии и playbook.
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
                    <Library className="h-12 w-12 text-[var(--color-accent)] opacity-30" />
                  </div>
                  <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                    <strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Единый стандарт</strong>
                    Автоматически сопоставляйте положения любых договоров с вашим внутренним playbook, 
                    обеспечивая идентичный уровень проверки независимо от исполнителя.
                  </p>
                </Reveal>
              </div>

              {/* Блок 2 */}
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center">
                <Reveal delay={0.1}>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40">
                    <AlertTriangle className="h-12 w-12 text-[var(--color-accent)] opacity-30" />
                  </div>
                  <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                    <strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Выявление аномалий</strong>
                    Система моментально подсвечивает отсутствующие условия, нетипичные формулировки 
                    и скрытые риски, требующие немедленного внимания эксперта.
                  </p>
                </Reveal>
              </div>

              {/* Блок 3 */}
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center last:pr-0">
                <Reveal delay={0.2}>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40">
                    <LinkIcon className="h-12 w-12 text-[var(--color-accent)] opacity-30" />
                  </div>
                  <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                    <strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Связанность данных</strong>
                    Получайте структурированные findings с прямой ссылкой на текст источника. 
                    Формируйте реестры и отчеты, готовые к интеграции в ваши рабочие процессы.
                  </p>
                </Reveal>
              </div>
            </div>
          </div>
        </section>

        {/* ─── 3. FINAL CTA SECTION ───────────────────────────────────── */}
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
                <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />
                <h2 className="mt-10 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">
                  Steloom не заменяет юридическую экспертизу <br /> 
                  <span className="italic font-light opacity-60 text-[var(--color-accent)]">и не выдает непрозрачные ответы</span>
                </h2>
                <div className="mt-7 space-y-5" style={{ maxWidth: 620 }}>
                  <p className="text-[1.0625rem] leading-[1.75] text-[#78756F]">
                    Система сокращает ручную работу с документами, помогает не упустить 
                    существенные факты и данные, освобождая время для глубокой правовой оценки.
                  </p>
                  <p className="text-[1.0625rem] leading-[1.75] text-[#78756F]">
                    Загрузите договорной массив - Steloom выделит существенные условия и поможет 
                    вашей команде сфокусироваться на рисках, которые действительно 
                    влияют на бизнес-результат и условия сделки.
                  </p>
                </div>
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
                <p className="mt-8 text-[0.8125rem] leading-[1.6] text-[#A8A29E]">
                  Обычно мы отвечаем и назначаем встречу в течение одного рабочего дня.
                </p>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default ContractReviewPage;


