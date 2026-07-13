import React from "react";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

const RealEstatePage: React.FC = () => {
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

export default RealEstatePage;

function HeroSection({ onDemo }: { onDemo: () => void }) {
  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem><p className="eyebrow">Расширенный анализ</p></RevealItem>
            <RevealItem>
              <h1 className="mt-6 font-serif tracking-[-0.03em]" style={{ fontSize: "clamp(2.5rem, 5vw, 4rem)", lineHeight: 1.05 }}>
                Анализ недвижимого имущества и прав
              </h1>
            </RevealItem>
            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Steloom выявляет объекты недвижимости в документах сделки — адреса, кадастровые номера и площади — и формирует реестр активов проекта.
              </p>
            </RevealItem>
            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Каждый объект сопоставляется с данными внешних реестров (ЕГРН, DLD) для мгновенной верификации прав и обременений.
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
      title: "Скрытые обременения",
      text: "Риск пропустить ипотеку, арест или сервитут, зафиксированные в приложениях или исторических документах.",
    },
    {
      title: "Неактуальные данные",
      text: "Расхождения между текстом договора и текущим статусом объекта в государственном реестре.",
    },
    {
      title: "Сложность верификации",
      text: "Трудоемкость ручного сопоставления сотен кадастровых номеров с актуальными выписками.",
    },
  ];
  return (
    <section data-header-theme="light" className="bg-[var(--bg-surface)]">
      <div className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem><h2 className="section-title">Риски при проверке активов</h2></RevealItem>
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
    "Автоматическое выявление объектов недвижимости в документах",
    "Реестровая верификация в режиме реального времени",
    "Проверка цепочки прав (Title Chain) и зонирования",
    "Карточка объекта с реестровым snapshot и ссылками",
  ];
  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem><h2 className="section-title">Единый реестр активов</h2></RevealItem>
            <RevealItem>
              <p className="mt-6 text-[1.0625rem] leading-[1.7] text-[var(--text-secondary)]">
                Команда получает рабочий интерфейс для проверки прав и реестрового статуса с прямой привязкой к исходным документам из Data Room.
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
            <RevealItem><h2 className="section-title">Инвентаризируйте активы быстрее</h2></RevealItem>
            <div className="mt-10"><button onClick={onDemo} className="cta-primary">Запросить демонстрацию</button></div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}


