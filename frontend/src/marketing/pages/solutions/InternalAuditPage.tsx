// src/marketing/pages/solutions/InternalAuditPage.tsx

import React from "react";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

const InternalAuditPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <AuditChallengeSection />
        <TimelineSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default InternalAuditPage;

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
                Внутренний аудит с полной прослеживаемостью
              </h1>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                По мере роста объема договоров ручная проверка становится
                трудоемкой, а результаты сложно воспроизвести при повторном
                аудите или внешнем контроле.
              </p>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Steloom обеспечивает последовательную проверку по единым
                правилам и сохраняет структурированную историю findings
                с полной привязкой к документам и правилам.
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
// 2. ПРОБЛЕМА АУДИТА
// ─────────────────────────────────────────────────────────────

function AuditChallengeSection() {
  const challenges = [
    {
      title: "Большие массивы договоров",
      text: "Проверка сотен и тысяч документов вручную требует значительных ресурсов.",
    },
    {
      title: "Невоспроизводимость результатов",
      text: "При повторной проверке сложно доказать, как был сформирован вывод.",
    },
    {
      title: "Отсутствие прозрачной истории",
      text: "Выводы хранятся в разных местах без четкой структуры.",
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
                Где возникает сложность аудита
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
// 3. TIMELINE (Тёмная секция — единственная на странице)
// ─────────────────────────────────────────────────────────────

function TimelineSection() {
  const periods = [
    { period: "Q1 2024", findings: 14 },
    { period: "Q2 2024", findings: 9 },
    { period: "Q3 2024", findings: 18 },
    { period: "Q4 2024", findings: 11 },
  ];

  return (
    <section data-header-theme="dark" className="bg-[var(--color-dark)]">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-3xl">
            <RevealItem>
              <h2
                className="font-serif tracking-[-0.03em] text-[var(--color-inverse)]"
                style={{
                  fontSize: "clamp(2.25rem, 4vw, 3.25rem)",
                  lineHeight: 1.05,
                }}
              >
                Воспроизводимая история проверки
              </h2>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-faint)]">
                Каждый период проверки сохраняется в структурированном виде.
                Findings остаются связанными с документами и правилами.
              </p>
            </RevealItem>

            <div className="mt-12 space-y-6">
              {periods.map((p) => (
                <RevealItem key={p.period}>
                  <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.05] px-6 py-5">
                    <span className="text-[0.9375rem] text-white/90">
                      {p.period}
                    </span>
                    <span className="text-[0.8125rem] text-white/60">
                      {p.findings} findings
                    </span>
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
                Сделайте аудит прозрачным
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


