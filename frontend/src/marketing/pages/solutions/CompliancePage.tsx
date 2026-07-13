// src/marketing/pages/solutions/CompliancePage.tsx

import React from "react";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const CompliancePage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <RiskSection />
        <ComplianceMechanismSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default CompliancePage;

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
                Compliance без потери контроля
              </h1>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                По мере роста количества договоров становится сложнее
                обеспечивать единый стандарт проверки и быстро выявлять
                отклонения от внутренних требований компании.
              </p>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Steloom позволяет автоматически применять внутренние политики,
                выявлять отклонения и формировать проверяемые результаты
                для согласования и контроля.
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
      title: "Разные стандарты проверки",
      text: "Каждый юрист применяет playbook по-своему, что приводит к расхождениям в качестве анализа.",
    },
    {
      title: "Сложность масштабирования",
      text: "При росте количества договоров ручной контроль становится трудоемким и непрозрачным.",
    },
    {
      title: "Отсутствие прослеживаемости",
      text: "Сложно воспроизвести, каким образом был сделан вывод при повторной проверке.",
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
                Где возникает риск несоответствия
              </h2>
            </RevealItem>

            <div className="mt-12 grid gap-8 sm:grid-cols-3">
              {risks.map((risk) => (
                <RevealItem key={risk.title}>
                  <div className="rounded-xl border border-[var(--color-border)] bg-[var(--bg-card)] p-6">
                    <h3 className="text-[1rem] font-medium text-[var(--text-primary)]">
                      {risk.title}
                    </h3>
                    <p className="mt-3 text-[0.875rem] leading-[1.7] text-[var(--text-secondary)]">
                      {risk.text}
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
// 3. КАК ОБЕСПЕЧИВАЕТСЯ COMPLIANCE
// ─────────────────────────────────────────────────────────────

function ComplianceMechanismSection() {
  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="grid items-center gap-16 lg:grid-cols-12">
            <div className="lg:col-span-7">
              <RevealItem>
                <h2 className="section-title">
                  Как Steloom обеспечивает соответствие
                </h2>
              </RevealItem>

              <RevealItem>
                <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                  Платформа применяет внутренние стандарты ко всем документам
                  автоматически, выявляя отклонения и формируя findings
                  с привязкой к конкретным положениям.
                </p>
              </RevealItem>

              <RevealItem>
                <ul className="mt-8 space-y-4">
                  {[
                    "Проверка договоров по корпоративному playbook",
                    "Автоматическое выявление отклонений",
                    "Структурированная история findings",
                    "Основа для внутреннего и внешнего контроля",
                  ].map((item) => (
                    <li key={item} className="flex gap-3">
                      <span className="mt-2 h-1.5 w-1.5 rounded-full bg-[var(--color-accent)]" />
                      <span className="text-[0.9375rem] text-[var(--text-secondary)]">
                        {item}
                      </span>
                    </li>
                  ))}
                </ul>
              </RevealItem>
            </div>

            <div className="lg:col-span-5">
              <RevealItem>
                <PolicyMockup />
              </RevealItem>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// MOCKUP
// ─────────────────────────────────────────────────────────────

function PolicyMockup() {
  return (
    <div
      className="rounded-2xl border border-[var(--color-border)] bg-[var(--bg-card)] p-6"
      style={{ boxShadow: "var(--shadow-md)" }}
    >
      <p className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
        Policy Check
      </p>

      <div className="mt-4 space-y-3">
        {[
          { rule: "Арбитражная оговорка", status: "OK" },
          { rule: "Limitation of liability", status: "Deviation" },
          { rule: "Confidentiality clause", status: "OK" },
          { rule: "Termination rights", status: "Missing" },
        ].map((item) => (
          <div
            key={item.rule}
            className="flex items-center justify-between rounded-lg border border-[var(--color-border-subtle)] px-4 py-3"
          >
            <span className="text-[0.875rem] text-[var(--text-primary)]">
              {item.rule}
            </span>
            <span
              className={`text-[0.75rem] ${
                item.status === "OK"
                  ? "text-green-600"
                  : "text-[var(--color-accent)]"
              }`}
            >
              {item.status}
            </span>
          </div>
        ))}
      </div>
    </div>
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
                Усильте контроль соответствия
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


