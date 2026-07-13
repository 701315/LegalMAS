// src/marketing/pages/solutions/ContractReviewPage.tsx

import React from "react";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const ContractReviewPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <HowItWorksSection />
        <OutcomeSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default ContractReviewPage;

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
              <p className="eyebrow">По направлению</p>
            </RevealItem>

            <RevealItem>
              <h1
                className="mt-6 font-serif tracking-[-0.03em]"
                style={{
                  fontSize: "clamp(2.5rem, 5vw, 4rem)",
                  lineHeight: 1.05,
                }}
              >
                Contract Review с единым стандартом findings
              </h1>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                При проверке отдельных договоров и пакетов контрактов
                важно быстро выявлять отклонения от стандартных позиций,
                отсутствующие положения и рискованные формулировки.
              </p>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Steloom выделяет отклонения от корпоративного playbook
                и формирует структурированные findings, связанные
                с конкретным положением документа.
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
// 2. HOW IT WORKS
// ─────────────────────────────────────────────────────────────

function HowItWorksSection() {
  const steps = [
    {
      title: "1. Классификация договора",
      text: "Платформа определяет тип документа и применяет релевантный сценарий анализа.",
    },
    {
      title: "2. Сравнение с playbook",
      text: "Каждое положение проверяется на соответствие корпоративным стандартам.",
    },
    {
      title: "3. Формирование findings",
      text: "Выводы структурируются и остаются привязанными к конкретным фрагментам договора.",
    },
  ];

  return (
    <section data-header-theme="light" className="bg-[var(--bg-surface)]">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-3xl">
            <RevealItem>
              <h2 className="section-title">
                Как работает проверка договора
              </h2>
            </RevealItem>

            <div className="mt-12 space-y-10">
              {steps.map((step) => (
                <RevealItem key={step.title}>
                  <div>
                    <h3 className="text-[1.25rem] font-medium text-[var(--text-primary)]">
                      {step.title}
                    </h3>
                    <p className="mt-3 text-[1rem] leading-[1.7] text-[var(--text-secondary)]">
                      {step.text}
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
// 3. OUTCOME
// ─────────────────────────────────────────────────────────────

function OutcomeSection() {
  const outcomes = [
    "Единый формат findings по всем документам проекта",
    "Быстрый переход от summary к тексту договора",
    "Снижение зависимости от конкретного исполнителя",
    "Прозрачная структура для согласования с бизнесом",
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
                Что получает команда
              </h2>
            </RevealItem>

            <div className="mt-12 grid gap-6 sm:grid-cols-2">
              {outcomes.map((item) => (
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
                Ускорьте проверку договоров
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


