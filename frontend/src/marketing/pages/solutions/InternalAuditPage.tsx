import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import Reveal from '../../motion/Reveal';
import { useContactModal } from "../../context/ContactModalContext";
import {
  ArrowRight,
  ClipboardCheck,
  FileSearch,
  History,
  Layers,
  GitCompare,
  ShieldCheck,
  CheckCircle2
} from "lucide-react";


const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];


const InternalAuditPage: React.FC = () => {
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
            {/* 1.1 PathCrumb */}
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05, ease }}
            >
              <PathCrumb root="Сценарии использования" leaf="Внутренний аудит" />
            </motion.div>


            {/* 1.2 Narrow Image — сразу после PathCrumb */}
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 16 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.15, ease }}
              className="mt-8 relative overflow-hidden rounded-none border border-[#E8E4DD] bg-white shadow-sm"
            >
              <img
                src="/ia-1.jpg"
                alt="Internal Audit Traceability"
                className="w-full h-auto object-cover"
                style={{ maxHeight: 280 }}
              />
            </motion.div>


            {/* 1.3 Intro Text — 55% ширины */}
            <motion.div
              className="mt-12 lg:w-[55%]"
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.3, ease }}
            >
              <p className="text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)] font-light">
                Структурирование массива, проверка по чек-листам, формирование доказательной
                базы и сравнение между периодами - рутинные процедуры, которые поглощают время
                аудитора. Steloom автоматизирует их: применяет единые правила ко всему массиву
                и формирует прослеживаемый аудиторский след - от вывода системы до конкретного
                абзаца первоисточника.
              </p>
            </motion.div>


            {/* 1.4 Large Serif Statement — H1 (clamp) */}
            <motion.h1
              className="mt-20 lg:mt-32 font-serif text-[clamp(2.5rem,5vw,4.2rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917] max-w-6xl"
              initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.45, ease }}
            >
              Аудиторский след, который не нужно собирать вручную - <br />
              <span className="italic font-light text-[var(--color-accent)]">
                от вывода системы до абзаца в первоисточнике.
              </span>
            </motion.h1>
          </div>
        </section>


        {/* ─── 2. THREE PILLARS SECTION ────────────────────────────────── */}
        <section className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
          <div
            className="mx-auto w-full px-6 lg:px-8"
            style={{ maxWidth: "var(--container-max-width)" }}
          >
            <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#E8E4DD]/60">

              {/* Блок 1 — Единый чек-лист */}
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center first:pl-0 last:pr-0">
                <Reveal>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40">
                    <ClipboardCheck className="h-12 w-12 text-[var(--color-accent)] opacity-30" />
                  </div>
                  <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                    <strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Единый чек-лист</strong>
                    Единые правила проверки применяются ко всему массиву - ни один документ
                    не выпадает из аудита. Исключение выборочного подхода и человеческих ошибок
                    при анализе тысяч договоров одновременно.
                  </p>
                </Reveal>
              </div>


              {/* Блок 2 — Аудиторский след */}
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center">
                <Reveal delay={0.1}>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40">
                    <FileSearch className="h-12 w-12 text-[var(--color-accent)] opacity-30" />
                  </div>
                  <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                    <strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Аудиторский след</strong>
                    Каждое замечание связано с конкретным пунктом документа. Заключение
                    оформлено с указанием изученных вопросов, выявленных отклонений и
                    оснований - готовая доказательная база для внешнего контроля.
                  </p>
                </Reveal>
              </div>


              {/* Блок 3 — Сравнение периодов */}
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center last:pr-0">
                <Reveal delay={0.2}>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40">
                    <History className="h-12 w-12 text-[var(--color-accent)] opacity-30" />
                  </div>
                  <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                    <strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Сравнение периодов</strong>
                    Результаты прошлых проверок остаются доступными для сопоставления.
                    Сравнивайте массивы между периодами, выявляйте динамику и новые
                    зоны риска, требующие внимания.
                  </p>
                </Reveal>
              </div>
            </div>
          </div>
        </section>


        {/* ─── 3. CAPABILITIES DETAIL SECTION ─────────────────────────── */}
        <section className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
          <div
            className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
            style={{ maxWidth: "var(--container-max-width)" }}
          >
            {/* Section heading */}
            <Reveal>
              <div className="max-w-2xl">
                <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-[#A8A29E] font-medium mb-4">
                  Что автоматизирует Steloom
                </p>
                <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-[1.15] tracking-[-0.02em] text-[#1A1917]">
                  Рутинные процедуры аудита - <br />
                  <span className="italic font-light text-[var(--color-accent)]">в едином потоке анализа</span>
                </h2>
              </div>
            </Reveal>

            {/* Rows: left = category with icon, right = bullet list */}
            <div className="mt-16">

              {/* Row 1: Структурирование массива */}
              <Reveal>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-8 border-t border-[#E8E4DD]/60">
                  <div className="md:col-span-4">
                    <div className="flex items-center gap-3">
                      <Layers className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                      <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917]">
                        Структурирование массива
                      </h3>
                    </div>
                  </div>
                  <div className="md:col-span-8">
                    <ul className="space-y-3">
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Автоматическая классификация по типам, датам, контрагентам, риск-категориям
                        </span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Исключение ручной сортировки и предварительной фильтрации
                        </span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Единое представление разнородных форматов (сканы, PDF, Word) в структурированном виде
                        </span>
                      </li>
                    </ul>
                  </div>
                </div>
              </Reveal>

              {/* Row 2: Проверка по чек-листам */}
              <Reveal delay={0.05}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-8 border-t border-[#E8E4DD]/60">
                  <div className="md:col-span-4">
                    <div className="flex items-center gap-3">
                      <ClipboardCheck className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                      <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917]">
                        Проверка по чек-листам
                      </h3>
                    </div>
                  </div>
                  <div className="md:col-span-8">
                    <ul className="space-y-3">
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Применение единых правил ко всем документам - 100% охват вместо выборочного аудита
                        </span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Выявление пропущенных обязательных условий, отклонений от типовых форм и внутренних политик
                        </span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Флаггирование документов, требующих профессионального суждения аудитора
                        </span>
                      </li>
                    </ul>
                  </div>
                </div>
              </Reveal>

              {/* Row 3: Аудиторский след и доказательность */}
              <Reveal delay={0.1}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-8 border-t border-[#E8E4DD]/60">
                  <div className="md:col-span-4">
                    <div className="flex items-center gap-3">
                      <ShieldCheck className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                      <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917]">
                        Аудиторский след и доказательность
                      </h3>
                    </div>
                  </div>
                  <div className="md:col-span-8">
                    <ul className="space-y-3">
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Каждое заключение сопровождается ссылкой на конкретный абзац первоисточника
                        </span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Полная история: что загружено, какие правила применены, какие отклонения выявлены
                        </span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Экспортируемые отчёты для внутреннего аудита и внешних проверок
                        </span>
                      </li>
                    </ul>
                  </div>
                </div>
              </Reveal>

              {/* Row 4: Сравнение периодов и мониторинг */}
              <Reveal delay={0.15}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-8 border-t border-[#E8E4DD]/60">
                  <div className="md:col-span-4">
                    <div className="flex items-center gap-3">
                      <GitCompare className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                      <h3 className="font-serif text-[1.25rem] tracking-tight text-[#1A1917]">
                        Сравнение периодов и мониторинг
                      </h3>
                    </div>
                  </div>
                  <div className="md:col-span-8">
                    <ul className="space-y-3">
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Сопоставление результатов проверок разных периодов - выявление динамики и новых рисков
                        </span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Отслеживание статусов корректирующих мероприятий (CAPA) и follow-up проверок
                        </span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">
                          Мониторинг изменений в договорном массиве между периодами аудита
                        </span>
                      </li>
                    </ul>
                  </div>
                </div>
              </Reveal>

            </div>
          </div>
        </section>


        {/* ─── 4. FINAL CTA SECTION ──────────────────────────── */}
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
                  Steloom не заменяет профессиональное суждение - <br />
                  <span className="italic font-light opacity-60 text-[var(--color-accent)]">он даёт ему опору в виде фактов</span>
                </h2>


                <div className="mt-7 space-y-5" style={{ maxWidth: 620 }}>
                  <p className="text-[1.0625rem] leading-[1.75] text-[#78756F]">
                    Система берёт на себя структурирование массива, первичную проверку по чек-листам
                    и формирование аудиторского следа - чтобы аудитор сосредоточился на оценке
                    реальных рисков, а не на сборе доказательств вручную.
                  </p>
                  <p className="text-[1.0625rem] leading-[1.75] text-[#78756F]">
                    Загрузите документы для аудита - Steloom структурирует массив, выделит
                    отклонения и сформирует прослеживаемую доказательную базу.
                    Каждый вывод - с ссылкой на первоисточник.
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


export default InternalAuditPage;

