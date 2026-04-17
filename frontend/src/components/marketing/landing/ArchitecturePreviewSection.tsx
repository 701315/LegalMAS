import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { landingContent } from "../../../content/landingContent";
import MarketingContainer from "../primitives/MarketingContainer";
import MarketingSection from "../primitives/MarketingSection";

const ArchitecturePreviewSection: React.FC = () => {
  const { architecturePreview } = landingContent;

  return (
    <MarketingSection
      id="architecture"
      className="bg-slate-900/40 scroll-mt-24"
    >
      <MarketingContainer size="section">
        {/* Верхний слой: позиционирование пайплайна */}
        <div className="grid gap-8 lg:grid-cols-[0.92fr_1.08fr]">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
              Architecture
            </div>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight text-white lg:text-5xl">
              {architecturePreview.title}
            </h2>
            <p className="mt-4 max-w-xl text-base leading-relaxed text-slate-400 lg:text-lg">
              {architecturePreview.description}
            </p>

            <Link
              to="/tech#pipeline"
              className="mt-8 inline-flex items-center gap-2 text-sm font-medium text-white transition-colors hover:text-slate-300"
            >
              {architecturePreview.linkLabel}
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <div className="rounded-[32px] border border-white/10 bg-white/[0.03] p-6 lg:p-8">
            <div className="grid gap-3 sm:grid-cols-2">
              {architecturePreview.bullets.map((item) => (
                <div
                  key={item}
                  className="rounded-2xl border border-white/10 bg-white/[0.025] px-4 py-4 text-sm text-slate-300"
                >
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Нижний слой: зачем клиенту именно pipeline, а не "LLM с промптом" */}
        <div className="mt-14 border-t border-white/5 pt-10">
          <div className="grid gap-10 lg:grid-cols-[0.95fr_1.05fr]">
            <div className="max-w-xl">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
                Why pipeline matters
              </div>
              <h3 className="mt-3 text-xl font-semibold tracking-tight text-white lg:text-2xl">
                Управляемый document pipeline вместо одноразовых AI‑ответов
              </h3>
              <p className="mt-4 text-sm leading-relaxed text-slate-400 lg:text-base">
                Для юридических команд важно не просто “получить ответ от модели”,
                а повторяемо прогонять десятки и сотни документов через один и тот
                же сценарий анализа, с понятными шагами, контрольными точками и
                возможностью вернутьcя к любому этапу. Поэтому LegalMAS — это
                пайплайн, а не single‑prompt.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              {/* Consistency & repeatability */}
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-4">
                <div className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                  Consistency
                </div>
                <p className="mt-2 text-xs leading-relaxed text-slate-400 lg:text-sm">
                  Один и тот же playbook‑сценарий применяется к каждому пакету
                  документов. Результаты не зависят от того, “как спросил
                  человек”, а от структуры пайплайна.
                </p>
              </div>

              {/* Control & observability */}
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-4">
                <div className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                  Control
                </div>
                <p className="mt-2 text-xs leading-relaxed text-slate-400 lg:text-sm">
                  Каждый шаг — от OCR до risk checks и нормализации — можно
                  наблюдать, тестировать и улучшать. Это ближе к управлению
                  системой, чем к “чёрному ящику” из одного промпта.
                </p>
              </div>

              {/* Scale & collaboration */}
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-4">
                <div className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                  Scale
                </div>
                <p className="mt-2 text-xs leading-relaxed text-slate-400 lg:text-sm">
                  Пайплайн можно адаптировать под разные типы сделок и команд,
                  не переписывая промпты. Юристы и операционные команды работают
                  в одном потоке, а не в наборе разрозненных AI‑запросов.
                </p>
              </div>
            </div>
          </div>
        </div>
      </MarketingContainer>
    </MarketingSection>
  );
};

export default ArchitecturePreviewSection;


