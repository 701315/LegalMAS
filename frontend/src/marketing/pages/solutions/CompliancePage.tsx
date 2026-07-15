import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import Reveal from '../../motion/Reveal';
import { useContactModal } from "../../context/ContactModalContext";
import { 
  ArrowRight, ShieldCheck, Zap, History, Building2, 
  CheckCircle2, AlertTriangle, Scale, ClipboardCheck 
} from "lucide-react";

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const CompliancePage: React.FC = () => {
  const { openContactModal } = useContactModal();
  const prefersReduced = useReducedMotion();

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1A1917] selection:bg-[var(--color-accent)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        {/* ─── 1. HERO SECTION (Dark Immersive) ───────────────────────── */}
        <section 
          className="relative flex min-h-[85dvh] items-center overflow-hidden bg-[#1A1917]"
          data-header-theme="dark"
        >
          <div className="absolute inset-0 z-0">
            <motion.img 
              src="/compl-1.png" 
              alt="Compliance Infrastructure" 
              className="h-full w-full object-cover object-center opacity-40 lg:opacity-60"
              initial={prefersReduced ? undefined : { scale: 1.02, opacity: 0 }}
              animate={prefersReduced ? undefined : { scale: 1, opacity: 0.6 }}
              transition={{ duration: 1.5, ease }}
            />
            <div 
              className="absolute inset-0" 
              style={{
                background: 'linear-gradient(90deg, #1A1917 0%, rgba(26,25,23,0.95) 25%, rgba(26,25,23,0.4) 60%, transparent 100%)'
              }} 
            />
          </div>

          <div
            className="relative z-10 mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
            style={{ maxWidth: "var(--container-max-width)" }}
          >
            <div className="grid gap-12 lg:grid-cols-12 lg:gap-16">
              <div className="lg:col-span-8 xl:col-span-7">
                <motion.div
                  initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
                  animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
                  transition={{ duration: 0.55, delay: 0.05, ease }}
                >
                  <PathCrumb root="Сценарии использования" leaf="Комплаенс и контроль" />
                </motion.div>

                <motion.div
                  className="mt-12 max-w-xl"
                  initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
                  animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
                  transition={{ duration: 0.55, delay: 0.22, ease }}
                >
                  <p className="text-[1.0625rem] leading-[1.75] text-white/70 font-light">
                    Обеспечьте непрерывный контроль соответствия договорного массива внутренним политикам 
                    и регуляторным требованиям. Автоматизируйте выявление критических отклонений, 
                    минимизируя влияние человеческого фактора на качество проверки.
                  </p>
                </motion.div>

                <motion.h1
                  className="mt-12 font-serif text-[clamp(2.5rem,5vw,4.2rem)] leading-[1.05] tracking-[-0.03em] text-[#FAF8F5]"
                  initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
                  animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
                  transition={{ duration: 0.6, delay: 0.4, ease }}
                >
                  Единый стандарт проверки - <br />
                  <span className="italic font-light text-[var(--color-accent)] brightness-125">
                    независимо от юрисдикции и объема данных.
                  </span>
                </motion.h1>

                <motion.div className="mt-12" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
                  <button onClick={openContactModal} className="cta-primary">
                    Запросить демонстрацию
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                </motion.div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── 2. BRIEF BLOCKS (Straight Corners) ─────────────────────── */}
        <section className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
          <div className="mx-auto w-full px-6 lg:px-8" style={{ maxWidth: "var(--container-max-width)" }}>
            <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#E8E4DD]/60">
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center first:pl-0 last:pr-0">
                <Reveal><div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40"><ShieldCheck className="h-12 w-12 text-[var(--color-accent)] opacity-30" /></div>
                <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light"><strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Policy Control</strong>Автоматически применяйте внутренние стандарты, исключая вариативность трактовок и пропуски условий.</p></Reveal>
              </div>
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center">
                <Reveal delay={0.1}><div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40"><Zap className="h-12 w-12 text-[var(--color-accent)] opacity-30" /></div>
                <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light"><strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Real-time Insights</strong>Моментально выявляйте аномалии, нетипичные риски и отклонения еще на этапе подготовки.</p></Reveal>
              </div>
              <div className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center last:pr-0">
                <Reveal delay={0.2}><div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[#E8E4DD]/40"><History className="h-12 w-12 text-[var(--color-accent)] opacity-30" /></div>
                <p className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light"><strong className="text-[#1A1917] block mb-2 font-serif italic text-lg tracking-tight">Audit Readiness</strong>Формируйте прозрачную историю комплаенс-проверок с полной прослеживаемостью вывода.</p></Reveal>
              </div>
            </div>
          </div>
        </section>

        {/* ─── 3. CAPABILITIES DETAIL SECTION (FULL VERSION) ──────────── */}
        <section className="bg-[#FAF8F5] border-t border-[#E8E4DD]/50">
          <div
            className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
            style={{ maxWidth: "var(--container-max-width)" }}
          >
            <Reveal>
              <div className="max-w-2xl mb-16">
                <p className="text-[0.8125rem] uppercase tracking-[0.12em] text-[#A8A29E] font-medium mb-4">
                  Что автоматизирует Steloom
                </p>
                <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-[1.15] tracking-[-0.02em] text-[#1A1917]">
                  Рутинные задачи комплаенс-контроля - <br />
                  <span className="italic font-light text-[var(--color-accent)]">в едином потоке анализа</span>
                </h2>
              </div>
            </Reveal>

            <div className="mt-16">
              {/* Row 1: Проверка контрагентов */}
              <Reveal>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[#E8E4DD]/60">
                  <div className="md:col-span-4">
                    <div className="flex items-center gap-3">
                      <Building2 className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                      <h3 className="font-serif text-[1.35rem] tracking-tight text-[#1A1917] italic">
                        Проверка контрагентов
                      </h3>
                    </div>
                  </div>
                  <div className="md:col-span-8">
                    <ul className="space-y-4">
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Анализ структуры владения и выявление аффилированности с государственными структурами</span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Флаггирование офшорных юрисдикций и нетипичных платежных реквизитов</span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Проверка наличия антикоррупционных оговорок и условий о конфликте интересов</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </Reveal>

              {/* Row 2: Анализ коррупционных рисков */}
              <Reveal delay={0.05}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[#E8E4DD]/60">
                  <div className="md:col-span-4">
                    <div className="flex items-center gap-3">
                      <AlertTriangle className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                      <h3 className="font-serif text-[1.35rem] tracking-tight text-[#1A1917] italic">
                        Анализ коррупционных рисков
                      </h3>
                    </div>
                  </div>
                  <div className="md:col-span-8">
                    <ul className="space-y-4">
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Выявление нетипичных платежных условий: расчёты через третьих лиц, нестандартные счета</span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Флаггирование навязанных субподрядчиков и необоснованных консультационных соглашений</span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Контроль соответствия условий сделки внутренним пороговым значениям и политикам</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </Reveal>

              {/* Row 3: Применение политик */}
              <Reveal delay={0.1}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[#E8E4DD]/60">
                  <div className="md:col-span-4">
                    <div className="flex items-center gap-3">
                      <Scale className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                      <h3 className="font-serif text-[1.35rem] tracking-tight text-[#1A1917] italic">
                        Применение политик
                      </h3>
                    </div>
                  </div>
                  <div className="md:col-span-8">
                    <ul className="space-y-4">
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Сопоставление каждого договора с внутренними плейбуками и типовыми формами</span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Выявление пропущенных обязательных условий, оговорок и положений</span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Классификация документов по типам, риск-категориям и юрисдикциям</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </Reveal>

              {/* Row 4: Аудит и прослеживаемость */}
              <Reveal delay={0.15}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[#E8E4DD]/60">
                  <div className="md:col-span-4">
                    <div className="flex items-center gap-3">
                      <ClipboardCheck className="h-5 w-5 text-[var(--color-accent)] opacity-50 flex-shrink-0" />
                      <h3 className="font-serif text-[1.35rem] tracking-tight text-[#1A1917] italic">
                        Аудит и прослеживаемость
                      </h3>
                    </div>
                  </div>
                  <div className="md:col-span-8">
                    <ul className="space-y-4">
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Каждое заключение сопровождается ссылкой на конкретный абзац первоисточника</span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Полная история проверок: что загружено, какие правила применены</span>
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="h-4 w-4 text-[var(--color-accent)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-[0.9375rem] leading-[1.65] text-[#78756F] font-light">Экспортируемые отчёты для внутреннего аудита и регуляторных проверок</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </Reveal>
            </div>
          </div>
        </section>

        {/* ─── 4. FINAL CTA SECTION (Pattern: SecurityCTA) ──────────────── */}
        <section className="relative bg-[#FAF8F5] py-28 lg:py-40 border-t border-[#E8E4DD]" data-header-theme="light">
          <div className="mx-auto w-full px-6 lg:px-8" style={{ maxWidth: 'var(--container-max-width)' }}>
            <Reveal><div className="mx-auto flex flex-col items-center text-center" style={{ maxWidth: 720 }}>
                <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />
                <h2 className="mt-10 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">Steloom не заменяет юридическую экспертизу <br /> <span className="italic font-light opacity-60 text-[var(--color-accent)]">и не выдает непрозрачные ответы</span></h2>
                <div className="mt-7 space-y-5 text-[1.0625rem] leading-[1.75] text-[#78756F]">
                  <p>Система сокращает ручную работу с документами, помогая не упустить существенные факты и данные.</p>
                  <p>Загрузите договорной массив - Steloom применит ваши комплаенс-плейбуки и выделит отклонения, требующие внимания специалистов.</p>
                </div>
                <div className="mt-10"><button onClick={openContactModal} className="cta-primary">Запросить демонстрацию <ArrowRight className="h-3.5 w-3.5" /></button></div>
                <p className="mt-8 text-[0.8125rem] leading-[1.6] text-[#A8A29E]">Обычно мы отвечаем в течение одного рабочего дня.</p>
            </div></Reveal>
          </div>
        </section>
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default CompliancePage;


