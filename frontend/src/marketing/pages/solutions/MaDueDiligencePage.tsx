// src/marketing/pages/solutions/MaDueDiligencePage.tsx

import React from "react";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

// ─────────────────────────────────────────────────────────────
// Page Component
// ─────────────────────────────────────────────────────────────

const MaDueDiligencePage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <WorkflowSection />
        <OutcomeSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default MaDueDiligencePage;

// ─────────────────────────────────────────────────────────────
// 1. HERO SECTION
// ─────────────────────────────────────────────────────────────

function HeroSection({ onDemo }: { onDemo: () => void }) {
  return (
    <section
      className="bg-[var(--bg-base)]"
      data-header-theme="light"
    >
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
                M&A и Due Diligence без хаоса в data room
              </h1>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Чем больше документов в сделке, тем сложнее сохранить единый стандарт проверки.
                Разные юристы замечают разные риски, выводы оказываются в разных таблицах,
                а переход от итогового замечания к конкретному положению договора занимает время.
              </p>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Steloom работает со всей data room как с единым массивом документов:
                классифицирует, применяет релевантные сценарии анализа и формирует
                структурированный DD grid по всему проекту.
              </p>
            </RevealItem>

            <RevealItem>
              <div className="mt-10">
                <button
                  type="button"
                  onClick={onDemo}
                  className="cta-primary"
                >
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
// 2. WORKFLOW SECTION
// ─────────────────────────────────────────────────────────────

function WorkflowSection() {
  return (
    <section
      className="bg-[var(--bg-surface)]"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="grid items-center gap-16 lg:grid-cols-12">
            {/* Left Column */}
            <div className="lg:col-span-7">
              <RevealItem>
                <h2 className="section-title">
                  Единый процесс анализа всей сделки
                </h2>
              </RevealItem>

              <RevealItem>
                <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                  Платформа автоматически определяет тип каждого документа,
                  применяет соответствующий сценарий проверки и собирает
                  результаты в структурированный DD grid.
                </p>
              </RevealItem>

              <RevealItem>
                <ul className="mt-8 space-y-4">
                  {[
                    "Автоматическая классификация документов",
                    "Типоспецифичный анализ для каждого документа",
                    "Структурированный DD grid по категориям рисков",
                    "Привязка каждого finding к источнику",
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

            {/* Right Column */}
            <div className="lg:col-span-5">
              <RevealItem>
                <DDGridMockup />
              </RevealItem>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// DD GRID MOCKUP
// ─────────────────────────────────────────────────────────────

function DDGridMockup() {
  return (
    <div
      className="rounded-2xl border border-[var(--color-border)] bg-[var(--bg-card)] p-6"
      style={{ boxShadow: "var(--shadow-md)" }}
    >
      <p className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
        DD Grid
      </p>

      <div className="mt-4 space-y-3">
        {[
          { name: "SPA Draft", findings: 4 },
          { name: "Lease Agreement", findings: 2 },
          { name: "IP License", findings: 1 },
          { name: "Shareholder Agreement", findings: 5 },
        ].map((row) => (
          <div
            key={row.name}
            className="flex items-center justify-between rounded-lg border border-[var(--color-border-subtle)] px-4 py-3"
          >
            <span className="text-[0.875rem] text-[var(--text-primary)]">
              {row.name}
            </span>
            <span className="text-[0.75rem] text-[var(--text-muted)]">
              {row.findings} findings
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// 3. OUTCOME SECTION
// ─────────────────────────────────────────────────────────────

function OutcomeSection() {
  return (
    <section
      className="bg-[var(--bg-base)]"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-3xl">
            <RevealItem>
              <h2 className="section-title">
                Что получает команда
              </h2>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Вместо разрозненных таблиц и комментариев — единая структура
                проверки по всей сделке.
              </p>
            </RevealItem>

            <RevealItem>
              <div className="mt-12 grid gap-6 sm:grid-cols-2">
                {[
                  "Единый стандарт проверки по всей data room",
                  "Быстрый переход от summary к документу",
                  "Прозрачная структура findings",
                  "Воспроизводимый процесс анализа",
                ].map((item) => (
                  <div
                    key={item}
                    className="rounded-xl border border-[var(--color-border)] bg-[var(--bg-card)] p-6"
                  >
                    <p className="text-[0.9375rem] text-[var(--text-primary)]">
                      {item}
                    </p>
                  </div>
                ))}
              </div>
            </RevealItem>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// 4. CTA SECTION
// ─────────────────────────────────────────────────────────────

function CTASection({ onDemo }: { onDemo: () => void }) {
  return (
    <section
      className="bg-[var(--bg-base)]"
      data-header-theme="light"
    >
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
                Посмотрите, как это работает на ваших документах
              </h2>
            </RevealItem>

            <RevealItem>
              <div className="mt-10">
                <button
                  type="button"
                  onClick={onDemo}
                  className="cta-primary"
                >
                  Запросить демонстрацию
                </button>
              </div>
            </RevealItem>

            <RevealItem>
              <p className="mt-6 text-[0.8125rem] text-[var(--text-muted)]">
                Среднее время демонстрации: 30–45 минут
              </p>
            </RevealItem>
          </div>
        </Reveal>
      </div>
    </section>
  );
}


