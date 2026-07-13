import React from "react";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

const CounterpartiesPage: React.FC = () => {
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

export default CounterpartiesPage;

function HeroSection({ onDemo }: { onDemo: () => void }) {
  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem><p className="eyebrow">Расширенный анализ</p></RevealItem>
            <RevealItem>
              <h1 className="mt-6 font-serif tracking-[-0.03em]" style={{ fontSize: "clamp(2.5rem, 5vw, 4rem)", lineHeight: 1.05 }}>
                Проверка контрагентов и связанных лиц
              </h1>
            </RevealItem>
            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Steloom автоматически выявляет контрагентов в тексте, таблицах и приложениях документов сделки, формирует единый реестр и обогащает профиль компаний через внешние и внутренние источники.
              </p>
            </RevealItem>
            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Команда видит, в каких контрактах и в какой роли фигурирует контрагент, и может оценить совокупную экспозицию в контексте всей сделки.
              </p>
            </RevealItem>
            <div className="mt-10"><button onClick={onDemo} className="cta-primary">Запросить демонстрацию</button></div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function RiskSection() {
  const risks = [
    {
      title: "Скрытая аффилированность",
      text: "Сложность выявления цепочек владения и конечных бенефициаров (UBO) вручную в больших Data Room.",
    },
    {
      title: "Санкционные риски",
      text: "Необходимость проверки сотен лиц по международным спискам, которые постоянно обновляются.",
    },
    {
      title: "Разрозненность данных",
      text: "Информация о финансовых показателях и судах контрагентов часто оторвана от текстов самих договоров.",
    },
  ];
  return (
    <section data-header-theme="light" className="bg-[var(--bg-surface)]">
      <div className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem><h2 className="section-title">Риски идентификации сторон</h2></RevealItem>
            <div className="mt-12 grid gap-8 sm:grid-cols-3">
              {risks.map((item) => (
                <RevealItem key={item.title}>
                  <div className="rounded-xl border border-[var(--color-border)] bg-[var(--bg-card)] p-6 h-full">
                    <h3 className="text-[1rem] font-medium text-[var(--text-primary)]">{item.title}</h3>
                    <p className="mt-3 text-[0.875rem] leading-[1.7] text-[var(--text-secondary)]">{item.text}</p>
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

function HowItHelpsSection() {
  const benefits = [
    "Автоматическое выявление лиц по всему пакету документов",
    "Risk aggregation: санкции, банкротство, суды, ownership",
    "Карточка контрагента с финансовым и юридическим контекстом",
    "Приоритизация критичных контрагентов для эскалации",
  ];
  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem><h2 className="section-title">Как Steloom решает эти задачи</h2></RevealItem>
            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Платформа формирует связанный слой анализа: каждый выявленный контрагент получает Registry Snapshot с данными из глобальных и локальных реестров.
              </p>
            </RevealItem>
            <div className="mt-12 grid gap-6 sm:grid-cols-2">
              {benefits.map((item) => (
                <RevealItem key={item}>
                  <div className="rounded-xl border border-[var(--color-border)] bg-[var(--bg-card)] p-6">
                    <p className="text-[0.9375rem] text-[var(--text-primary)]">{item}</p>
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

function CTASection({ onDemo }: { onDemo: () => void }) {
  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="mx-auto max-w-[720px] text-center">
            <RevealItem><div className="mx-auto mb-10 h-px w-4 bg-[var(--text-faint)]" /></RevealItem>
            <RevealItem><h2 className="section-title">Автоматизируйте KYC и проверку сторон</h2></RevealItem>
            <div className="mt-10"><button onClick={onDemo} className="cta-primary">Запросить демонстрацию</button></div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}


