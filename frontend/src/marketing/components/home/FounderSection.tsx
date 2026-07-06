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
      className="bg-[#FAF8F5] py-20 lg:py-28"
      data-header-theme="light"
    >
      <div
        className="mx-auto px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-12 lg:grid-cols-[1fr_1.6fr] lg:gap-20 lg:items-start">
          
          {/* ── Левая: Attribution ─────────────────────────── */}
          <div
            ref={content.ref as React.Ref<HTMLDivElement>}
            style={content.style}
          >
            <div className="mb-10">
              <span className="eyebrow">От основателя</span>
            </div>

            <div className="mb-6">
              <div className="h-20 w-20 overflow-hidden rounded-full border-2 border-[#E8E4DD]">
                <img
                  src={photoVladimir}
                  alt="Vladimir Gorelov"
                  className="h-full w-full object-cover"
                />
              </div>
            </div>

            <div className="mb-8">
              <div className="text-[0.9375rem] font-medium text-[#1A1917]">
                Vladimir Gorelov
              </div>
              <div className="mt-1 text-sm text-[#78756F]">
                Основатель и CEO, Steloom
              </div>
            </div>

            <Link to="/about" className="cta-link mt-8">
              О команде и миссии
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

          {/* ── Правая: Цитата ─────────────────────────────── */}
          <div
            ref={quote.ref as React.Ref<HTMLDivElement>}
            style={quote.style}
          >
            <blockquote>
              <p
                className="font-serif leading-[1.4] tracking-[-0.02em] text-[#1A1917]"
                style={{ fontSize: "clamp(1.75rem, 2.8vw, 2.5rem)" }}
              >
                «Юридическим командам не нужен ещё один AI, который просто даёт быстрые ответы.
                Им нужна система, где каждый вывод можно проследить до источника —
                и где логика достаточно прозрачна, чтобы на неё можно было опереться в решении».
              </p>

              <p
                className="mt-8 font-serif leading-[1.5] tracking-[-0.01em] text-[#78756F]"
                style={{ fontSize: "clamp(1.25rem, 1.8vw, 1.75rem)" }}
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


