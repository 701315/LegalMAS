// src/marketing/pages/solutions/CorporateLegalPage.tsx

import React from "react";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const CorporateLegalPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <RiskSection />
        <HowItHelpsSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default CorporateLegalPage;

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
                Единый стандарт проверки для корпоративного департамента
              </h1>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Корпоративные юридические департаменты сопровождают закупки,
                продажи, HR и коммерческие проекты. При росте количества договоров
                сложнее быстро выявлять отклонения от внутренних требований.
              </p>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Steloom автоматически применяет внутренние стандарты и формирует
                проверяемые findings для согласования с бизнесом и руководством.
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
// 2. ГДЕ ВОЗНИКАЮТ РИСКИ
// ─────────────────────────────────────────────────────────────

function RiskSection() {
  const risks = [
    {
      title: "Разрозненные проверки",
      text: "Разные юристы по-разному интерпретируют стандарты и формулировки.",
    },
    {
      title: "Сложность согласования",
      text: "Отсутствие структурированных findings усложняет коммуникацию с бизнесом.",
    },
    {
      title: "Риск пропущенных отклонений",
      text: "При большом объеме договоров сложно гарантировать полное покрытие.",
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
                Где департамент теряет контроль
              </h2>
            </RevealItem>

            <div className="mt-12 grid gap-8 sm:grid-cols-3">
              {risks.map((item) => (
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
// 3. КАК ПОМОГАЕТ STOOM
// ─────────────────────────────────────────────────────────────

function HowItHelpsSection() {
  const benefits = [
    "Проверка договоров по корпоративному playbook",
    "Автоматическое выявление отклонений",
    "Структурированные findings для согласования",
    "Прозрачная основа для управления рисками",
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
                Как Steloom помогает департаменту
              </h2>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Платформа обеспечивает единый стандарт проверки независимо
                от количества договоров и исполнителей.
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
                Усильте контроль и прозрачность проверки
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


