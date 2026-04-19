import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

const SecuritySplitSection: React.FC = () => {
  const { security } = landingContent;

  return (
    <MarketingSection id="security" className="bg-stone-950 text-[#f7f3ea] scroll-mt-24">
      <MarketingContainer size="section">
        <div className="grid gap-6 lg:grid-cols-12 lg:gap-8">
          <div className="rounded-[32px] border border-white/10 bg-white/[0.04] p-7 lg:col-span-5 lg:p-9">
            <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-400">
              Security
            </div>
            <h2 className="mt-4 max-w-md font-serif text-4xl leading-tight tracking-[-0.03em] text-white lg:text-5xl">
              {security.title}
            </h2>
            <p className="mt-5 max-w-xl text-base leading-8 text-stone-300">
              {security.description}
            </p>

            <div className="mt-8 flex flex-wrap gap-2.5">
              {security.badges.map((badge) => (
                <div
                  key={badge}
                  className="rounded-full border border-white/10 bg-white/[0.06] px-3.5 py-2 text-xs font-medium tracking-[0.01em] text-stone-200"
                >
                  {badge}
                </div>
              ))}
            </div>

            <Link
              to="/security#privacy"
              className="mt-8 inline-flex items-center gap-2 text-sm font-semibold text-white transition-colors hover:text-stone-300"
            >
              {security.linkLabel}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <div className="grid gap-4 lg:col-span-7 lg:grid-cols-3">
            {security.cards.map((card) => (
              <div
                key={card.title}
                className="flex h-full flex-col rounded-[28px] border border-white/10 bg-white/[0.03] p-6"
              >
                <h3 className="text-xl font-semibold tracking-tight text-white">
                  {card.title}
                </h3>

                <p className="mt-4 text-sm leading-7 text-stone-300">
                  {card.text}
                </p>

                {"image" in card && card.image && (
                  <div className="mt-auto pt-6">
                    <img
                      src={card.image}
                      alt={card.title}
                      className="h-44 w-full rounded-[20px] object-cover"
                      loading="lazy"
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="mt-12 rounded-[32px] border border-white/10 bg-white/[0.025] p-7 lg:p-9">
          <div className="grid gap-8 lg:grid-cols-[0.85fr_1.15fr] lg:gap-10">
            <div>
              <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-400">
                Security posture
              </div>
              <h3 className="mt-4 max-w-md font-serif text-3xl leading-tight tracking-[-0.03em] text-white lg:text-4xl">
                Контур доступа, данные и доказуемость для security review
              </h3>
              <p className="mt-5 max-w-xl text-base leading-8 text-stone-300">
                LegalMAS проектировался так, чтобы выдерживать вопросы не только юристов,
                но и CISO: где хранятся документы, как используется AI, кто получает доступ
                к результатам анализа и как это подтверждается в security‑опросниках.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="rounded-[24px] border border-white/10 bg-white/[0.04] px-4 py-5">
                <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400">
                  Access & identity
                </div>
                <p className="mt-3 text-sm leading-7 text-stone-300">
                  Разделение ролей для загрузки документов, запуска проверок и доступа к выводам.
                </p>
              </div>

              <div className="rounded-[24px] border border-white/10 bg-white/[0.04] px-4 py-5">
                <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400">
                  Data boundaries
                </div>
                <p className="mt-3 text-sm leading-7 text-stone-300">
                  Local‑first обработка и PII‑gateway перед внешними моделями для чувствительных сценариев.
                </p>
              </div>

              <div className="rounded-[24px] border border-white/10 bg-white/[0.04] px-4 py-5">
                <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400">
                  Auditability
                </div>
                <p className="mt-3 text-sm leading-7 text-stone-300">
                  Source‑linked outputs и прозрачный trail для review, контроля и внутреннего согласования.
                </p>
              </div>
            </div>
          </div>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default SecuritySplitSection;




