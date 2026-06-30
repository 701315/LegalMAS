// src/marketing/components/home/FounderSection.tsx

import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useScrollReveal } from "../../../hooks/useScrollReveal";
import photoVladimir from "../assets/photos/vladimir.jpg";

const FounderSection: React.FC = () => {
  const content = useScrollReveal(0);
  const quote = useScrollReveal(120);

  return (
    <section
      className="bg-[#F8F7F4] py-24 sm:py-32"
      data-header-theme="light"
    >
      <div className="mx-auto max-w-[1280px] px-4 sm:px-6 lg:px-10 xl:px-12">
        <div className="grid gap-16 lg:grid-cols-[1fr_1.6fr] lg:gap-24 lg:items-start">
          {/* ── Левая: Attribution ─────────────────────────── */}
          <div
            ref={content.ref as React.Ref<HTMLDivElement>}
            style={content.style}
          >
            <div className="mb-10 flex items-center gap-3">
              <div className="h-px w-10 bg-stone-300" />
              <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400">
                От основателя
              </span>
            </div>

            <div className="mb-6">
              <div className="h-20 w-20 overflow-hidden rounded-full border-2 border-[#E5E2DA]">
                <img
                  src={photoVladimir}
                  alt="Vladimir Gorelov"
                  className="h-full w-full object-cover"
                />
              </div>
            </div>

            <div className="mb-8">
              <div className="text-base font-medium text-stone-900">
                Vladimir Gorelov
              </div>
              <div className="mt-1 text-sm text-stone-500">
                Основатель и CEO, Steloom
              </div>
            </div>

            <Link
              to="/about"
              className="group inline-flex items-center gap-2 text-sm font-medium text-stone-500 transition-colors hover:text-stone-900"
            >
              О команде и миссии
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </div>

          {/* ── Правая: Цитата ─────────────────────────────── */}
          <div
            ref={quote.ref as React.Ref<HTMLDivElement>}
            style={quote.style}
          >
            <blockquote>
              <p
                className="font-serif font-light leading-[1.5] tracking-[-0.01em] text-stone-800"
                style={{ fontSize: "clamp(1.5rem, 2.4vw, 2.125rem)" }}
              >
                «Юридическим командам не нужен ещё один AI, который просто даёт быстрые ответы.
                Им нужна система, где каждый вывод можно проследить до источника —
                и где логика достаточно прозрачна, чтобы на неё можно было опереться в решении».
              </p>

              <p
                className="mt-8 font-serif font-light leading-[1.5] tracking-[-0.01em] text-stone-500"
                style={{ fontSize: "clamp(1.25rem, 1.8vw, 1.625rem)" }}
              >
                «Steloom — это именно такая система. Не shortcut к ответу,
                а основание для защищаемого и проверяемого вывода».
              </p>
            </blockquote>
          </div>
        </div>
      </div>
    </section>
  );
};

export default FounderSection;


