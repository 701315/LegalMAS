// src/marketing/pages/SecurityPage.tsx

import React from "react";
import MarketingEditorialShell from "../components/shared/MarketingEditorialShell";
import { landingContent } from "../content/landingContent";

const SecurityPage: React.FC = () => {
  const { security } = landingContent;

  return (
    <MarketingEditorialShell
      title="Подход privacy-first и security layer внутри самого продукта"
      description="Для Steloom trust layer — это не отдельный маркетинговый абзац, а часть архитектуры: local-first processing, controlled cloud mode, role-based access и source-linked auditability."
    >
      <div className="grid gap-6 lg:grid-cols-12">
        <div className="rounded-[32px] border border-stone-900/10 bg-stone-950 p-7 text-[#f7f3ea] lg:col-span-5 lg:p-9">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400">
            Контур безопасности
          </div>

          <h2 className="mt-4 font-serif text-4xl leading-tight tracking-[-0.03em] text-white">
            {security.title}
          </h2>

          <p className="mt-5 text-base leading-8 text-stone-300">
            {security.description}
          </p>

          <div className="mt-8 flex flex-wrap gap-2.5">
            {security.badges.map((badge) => (
              <div
                key={badge}
                className="rounded-full border border-white/10 bg-white/[0.06] px-3.5 py-2 text-xs font-medium text-stone-200"
              >
                {badge}
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-4 lg:col-span-7 lg:grid-cols-3">
          {security.cards.map((card) => (
            <div
              key={card.title}
              className="rounded-[28px] border border-stone-900/10 bg-white/70 p-6"
            >
              <h3 className="text-xl font-semibold text-stone-950">
                {card.title}
              </h3>
              <p className="mt-3 text-sm leading-7 text-stone-700">
                {card.text}
              </p>
            </div>
          ))}
        </div>
      </div>
    </MarketingEditorialShell>
  );
};

export default SecurityPage;

