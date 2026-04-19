import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

const ArchitecturePreviewSection: React.FC = () => {
  const { architecturePreview } = landingContent;

  return (
    <MarketingSection id="architecture" className="bg-[#ece5d8] scroll-mt-24">
      <MarketingContainer size="section">
        <div className="grid gap-6 lg:grid-cols-12">
          <div className="rounded-[32px] border border-stone-900/10 bg-stone-950 p-7 text-[#f7f3ea] lg:col-span-5 lg:p-9">
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-400">
              Architecture
            </div>
            <h2 className="mt-4 max-w-md font-serif text-4xl leading-tight tracking-[-0.03em] text-white lg:text-5xl">
              {architecturePreview.title}
            </h2>
            <p className="mt-5 max-w-xl text-base leading-8 text-stone-300">
              {architecturePreview.description}
            </p>

            <Link
              to="/tech#pipeline"
              className="mt-8 inline-flex items-center gap-2 text-sm font-semibold text-white transition-colors hover:text-stone-300"
            >
              {architecturePreview.linkLabel}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <div className="rounded-[32px] border border-stone-900/10 bg-[#f7f3ea] p-7 lg:col-span-7 lg:p-9">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {architecturePreview.bullets.map((item) => (
                <div
                  key={item}
                  className="rounded-[22px] border border-stone-900/10 bg-white/70 px-4 py-4 text-sm leading-6 text-stone-700"
                >
                  {item}
                </div>
              ))}
            </div>

            <div className="mt-8 border-t border-stone-900/10 pt-8">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-[24px] bg-white/70 px-4 py-4">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                    Consistency
                  </div>
                  <p className="mt-3 text-sm leading-7 text-stone-700">
                    Один playbook‑сценарий применяется ко всему пакету документов, а не к одному чату.
                  </p>
                </div>
                <div className="rounded-[24px] bg-white/70 px-4 py-4">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                    Control
                  </div>
                  <p className="mt-3 text-sm leading-7 text-stone-700">
                    От OCR до checks execution каждый шаг наблюдаем, тестируем и управляем.
                  </p>
                </div>
                <div className="rounded-[24px] bg-white/70 px-4 py-4">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                    Scale
                  </div>
                  <p className="mt-3 text-sm leading-7 text-stone-700">
                    Пайплайн адаптируется под разные сделки и команды без разрозненных prompt‑паттернов.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default ArchitecturePreviewSection;


