import React from "react";
import MarketingEditorialShell from "../components/shared/MarketingEditorialShell";
import { landingContent } from "../content/landingContent";

const CapabilitiesPage: React.FC = () => {
  const { capabilities } = landingContent;
  return (
    <MarketingEditorialShell
      eyebrow="Capabilities"
      title="Полный набор возможностей LegalMAS"
      description="Здесь подробно раскрываются ключевые функции платформы: playbook-driven review, работа с пакетами документов, explainable outputs, privacy-first архитектура и structured reporting."
      primaryLink={{ label: "Сценарии применения", to: "/solutions" }}
      secondaryLink={{ label: "Архитектура и pipeline", to: "/tech" }}
    >
      <div className="grid gap-5 lg:grid-cols-12">
        {capabilities.featured.map((item, idx) => {
          const Icon = item.icon;
          return (
            <div key={item.title} className={`rounded-[32px] border border-stone-900/10 p-7 lg:p-9 ${idx === 0 ? 'bg-[#ece5d8] lg:col-span-7' : 'bg-white/70 lg:col-span-5'}`}>
              <Icon className="h-6 w-6 text-stone-700" />
              <h2 className="mt-10 max-w-xl font-serif text-3xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-[2.3rem]">{item.title}</h2>
              <p className="mt-5 text-base leading-8 text-stone-700">{item.description}</p>
            </div>
          );
        })}

        {capabilities.support.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.title} className="rounded-[28px] border border-stone-900/10 bg-white/65 p-6 lg:col-span-4">
              <Icon className="h-5 w-5 text-stone-700" />
              <h3 className="mt-8 text-xl font-semibold text-stone-950">{item.title}</h3>
              <p className="mt-3 text-sm leading-7 text-stone-700">{item.description}</p>
            </div>
          );
        })}
      </div>
    </MarketingEditorialShell>
  );
};

export default CapabilitiesPage;

