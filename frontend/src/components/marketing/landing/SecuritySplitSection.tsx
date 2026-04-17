import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";
import MarketingBadge from "../primitives/MarketingBadge";

const SecuritySplitSection: React.FC = () => {
  const { security } = landingContent;

  return (
    <MarketingSection id="security" className="bg-slate-950 scroll-mt-24">
      <MarketingContainer size="section">
        {/* Верхний основной слой: позиционирование security как части архитектуры */}
        <div className="grid gap-8 lg:grid-cols-[0.95fr_1.05fr]">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Security
            </div>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white lg:text-5xl">
              {security.title}
            </h2>
            <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-400 lg:text-lg">
              {security.description}
            </p>

            <div className="mt-6 flex flex-wrap gap-3">
              {security.badges.map((badge) => (
                <MarketingBadge key={badge}>{badge}</MarketingBadge>
              ))}
            </div>

            <Link
              to="/security#privacy"
              className="mt-8 inline-flex items-center gap-2 text-sm font-medium text-white transition-colors hover:text-slate-300"
            >
              {security.linkLabel}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <div className="grid gap-4">
            {security.cards.map((card) => (
              <div
                key={card.title}
                className="rounded-[28px] border border-white/10 bg-white/[0.03] p-6 lg:p-7"
              >
                <h3 className="text-xl font-semibold text-white">{card.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-slate-400 lg:text-base">
                  {card.text}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Нижний слой: security posture — то, что смотрит CISO / комплаенс */}
        <div className="mt-14 border-t border-white/5 pt-10">
          <div className="grid gap-10 lg:grid-cols-[0.95fr_1.05fr]">
            <div className="max-w-xl">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Security posture
              </div>
              <h3 className="mt-3 text-xl font-semibold tracking-tight text-white lg:text-2xl">
                Контур доступа, данные и доказуемость для security‑review
              </h3>
              <p className="mt-4 text-sm leading-relaxed text-slate-400 lg:text-base">
                LegalMAS проектировался так, чтобы выдерживать вопросы не только
                юристов, но и CISO: где хранятся документы, как используется AI,
                кто и каким образом может получить доступ к результатам анализа и
                как всё это доказать на security‑опроснике.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              {/* Access & identity */}
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-4">
                <div className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                  Access & identity
                </div>
                <p className="mt-2 text-xs leading-relaxed text-slate-400 lg:text-sm">
                  Разделение ролей для загрузки документов, запуска проверок и
                  доступа к выводам. Платформа готова к интеграции с SSO и
                  принципом наименьших привилегий в вашем контуре.
                </p>
              </div>

              {/* Data boundaries & LLM usage */}
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-4">
                <div className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                  Data boundaries
                </div>
                <p className="mt-2 text-xs leading-relaxed text-slate-400 lg:text-sm">
                  Local‑first обработка документов и PII‑gateway перед внешними
                  моделями. Внешние LLM не обучаются на ваших данных, используются
                  только на этапе inference в строго ограниченных сценариях.
                </p>
              </div>

              {/* Compliance & auditability */}
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-4">
                <div className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                  Compliance & audit
                </div>
                <p className="mt-2 text-xs leading-relaxed text-slate-400 lg:text-sm">
                  Логирование ключевых действий, source‑linked выводы и
                  восстановимая история сессий позволяют проходить security‑опросы
                  и внутренний аудит без “серой зоны” вокруг AI‑компоненты.
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


