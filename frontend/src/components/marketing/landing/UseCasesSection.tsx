import React from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, SearchCheck } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

const UseCasesSection: React.FC = () => {
  const { useCases } = landingContent;

  return (
    <MarketingSection id="use-cases" className="bg-[#f7f3ea] scroll-mt-24">
      <MarketingContainer size="section">
        <div className="grid gap-10 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
              Use cases
            </div>
            <h2 className="mt-4 max-w-md font-serif text-4xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-5xl">
              {useCases.title}
            </h2>
            <Link
              to="/solutions"
              className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-stone-900 transition-colors hover:text-stone-600"
            >
              Открыть все сценарии
              <ArrowUpRight className="h-4 w-4" />
            </Link>

            <div className="mt-8 rounded-[28px] border border-stone-900/10 bg-white/70 p-6 lg:p-7">
              <SearchCheck className="h-5 w-5 text-stone-700" />
              <h3 className="mt-10 max-w-sm font-serif text-3xl leading-tight tracking-[-0.03em] text-stone-950">
                Проверка активов \ партнеров
              </h3>
              <p className="mt-4 max-w-lg text-sm leading-7 text-stone-700 lg:text-base">
                Проведение дополнительной проверки активов \ контрагентов из анализируемых
                документов по выбранным критериям через сторонние сервисы и агрегирование
                результатов их проверки в основной отчет.
              </p>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:col-span-8">
            {useCases.items.map((item, index) => {
              const Icon = item.icon;
              const tones = ["bg-white/70", "bg-[#efe9dd]", "bg-[#f2ece2]", "bg-white/75"];

              return (
                <div
                  key={item.title}
                  className={`rounded-[28px] border border-stone-900/10 p-6 lg:p-7 ${tones[index % tones.length]}`}
                >
                  <Icon className="h-5 w-5 text-stone-700" />
                  <h3 className="mt-10 max-w-sm font-serif text-3xl leading-tight tracking-[-0.03em] text-stone-950">
                    {item.title}
                  </h3>
                  <p className="mt-4 max-w-lg text-sm leading-7 text-stone-700 lg:text-base">
                    {item.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default UseCasesSection;




