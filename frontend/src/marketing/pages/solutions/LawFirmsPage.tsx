// src/marketing/pages/solutions/LawFirmsPage.tsx

import React from "react";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const LawFirmsPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <GrowthChallengeSection />
        <HowSteloomHelpsSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default LawFirmsPage;

// ─────────────────────────────────────────────────────────────
// 1. HERO
// ─────────────────────────────────────────────────────────────

function HeroSection({ onDemo }: { onDemo: () => void }) {
  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem>
              <p className="eyebrow">По типу команды</p>
            </RevealItem>

            <RevealItem>
              <h1
                className="mt-6 font-serif tracking-[-0.03em]"
                style={{
                  fontSize: "clamp(2.5rem, 5vw, 4rem)",
                  lineHeight: 1.05,
                }}
              >
                Масштабируйте экспертизу юридической фирмы
              </h1>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Когда одновременно ведется несколько проектов, становится сложнее
                поддерживать единый стандарт анализа и качество выводов.
              </p>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Steloom автоматизирует первичный этап проверки документов,
                позволяя команде сосредоточиться на юридической оценке
                и стратегических рекомендациях клиенту.
              </p>
            </RevealItem>

            <RevealItem>
              <div className="mt-10">
                <button onClick={onDemo} className="cta-primary">
                  Запросить демонстрацию
                </button>
              </div>
            </RevealItem>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// 2. ПРОБЛЕМА РОСТА
// ─────────────────────────────────────────────────────────────

function GrowthChallengeSection() {
  const challenges = [
    {
      title: "Разный уровень анализа",
      text: "Качество проверки зависит от опыта конкретного юриста.",
    },
    {
      title: "Рост числа проектов",
      text: "С увеличением количества сделок сложнее сохранять единый стандарт.",
    },
    {
      title: "Повторяющиеся задачи",
      text: "Юристы тратят время на однотипные проверки вместо стратегической работы.",
    },
  ];

  return (
    <section data-header-theme="light" className="bg-[var(--bg-surface)]">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem>
              <h2 className="section-title">
                Что мешает масштабированию практики
              </h2>
            </RevealItem>

            <div className="mt-12 grid gap-8 sm:grid-cols-3">
              {challenges.map((item) => (
                <RevealItem key={item.title}>
                  <div className="rounded-xl border border-[var(--color-border)] bg-[var(--bg-card)] p-6">
                    <h3 className="text-[1rem] font-medium text-[var(--text-primary)]">
                      {item.title}
                    </h3>
                    <p className="mt-3 text-[0.875rem] leading-[1.7] text-[var(--text-secondary)]">
                      {item.text}
                    </p>
                  </div>
                </RevealItem>
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// 3. КАК STOOM УСИЛИВАЕТ КОМАНДУ
// ─────────────────────────────────────────────────────────────

function HowSteloomHelpsSection() {
  const benefits = [
    "Единый стандарт проверки по всем проектам",
    "Структурированные findings для клиентских отчетов",
    "Снижение зависимости от конкретного исполнителя",
    "Больше времени на юридическую оценку и стратегию",
  ];

  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem>
              <h2 className="section-title">
                Как Steloom усиливает команду
              </h2>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Платформа применяет корпоративный playbook ко всем проектам
                и формирует структурированные выводы, пригодные для клиентских
                рекомендаций и юридических заключений.
              </p>
            </RevealItem>

            <div className="mt-12 grid gap-6 sm:grid-cols-2">
              {benefits.map((item) => (
                <RevealItem key={item}>
                  <div className="rounded-xl border border-[var(--color-border)] bg-[var(--bg-card)] p-6">
                    <p className="text-[0.9375rem] text-[var(--text-primary)]">
                      {item}
                    </p>
                  </div>
                </RevealItem>
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// 4. CTA
// ─────────────────────────────────────────────────────────────

function CTASection({ onDemo }: { onDemo: () => void }) {
  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="mx-auto max-w-[720px] text-center">
            <RevealItem>
              <div className="mx-auto mb-10 h-px w-4 bg-[var(--text-faint)]" />
            </RevealItem>

            <RevealItem>
              <h2 className="section-title">
                Масштабируйте практику без потери качества
              </h2>
            </RevealItem>

            <RevealItem>
              <div className="mt-10">
                <button onClick={onDemo} className="cta-primary">
                  Запросить демонстрацию
                </button>
              </div>
            </RevealItem>
          </div>
        </Reveal>
      </div>
    </section>
  );
}


