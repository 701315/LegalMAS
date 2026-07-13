// src/marketing/pages/solutions/AuditCompliancePage.tsx

import React from "react";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const AuditCompliancePage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <TransparencyRiskSection />
        <AuditControlSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default AuditCompliancePage;

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
                Прозрачный внутренний аудит и compliance‑контроль
              </h1>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Внутренний аудит регулярно проверяет большие массивы договоров.
                Руководству важно понимать не только результат проверки,
                но и каким образом он был сформирован.
              </p>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Steloom формирует структурированную историю findings
                с полной прослеживаемостью каждого вывода —
                прозрачную основу для внутреннего и внешнего контроля.
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
// 2. ГДЕ ТЕРЯЕТСЯ ПРОЗРАЧНОСТЬ
// ─────────────────────────────────────────────────────────────

function TransparencyRiskSection() {
  const risks = [
    {
      title: "Ручная проверка",
      text: "Результаты зависят от конкретного аудитора и его интерпретации.",
    },
    {
      title: "Отсутствие единой истории",
      text: "Findings хранятся в разных таблицах и документах.",
    },
    {
      title: "Сложность повторной проверки",
      text: "При внешнем аудите сложно воспроизвести ход анализа.",
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
                Где теряется прозрачность аудита
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
// 3. КАК STOOM УСИЛИВАЕТ AUDIT-ФУНКЦИЮ
// ─────────────────────────────────────────────────────────────

function AuditControlSection() {
  const benefits = [
    "Единая структура findings по всему договорному массиву",
    "Привязка каждого вывода к документу и правилу",
    "Воспроизводимая методология проверки",
    "Прозрачная основа для отчета перед руководством",
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
                Как Steloom усиливает audit‑функцию
              </h2>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Платформа позволяет не просто выявлять отклонения,
                но и формировать воспроизводимую историю анализа,
                которая может быть повторно проверена и обоснована.
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
                Усильте прозрачность внутреннего контроля
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


