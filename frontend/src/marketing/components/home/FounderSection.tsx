import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useScrollReveal } from "../../../hooks/useScrollReveal";
import photoVladimir from "../assets/photos/vladimir.jpg";

const FounderSection: React.FC = () => {
  const left = useScrollReveal(0);
  const right = useScrollReveal(120);

  return (
    <section
      id="founder"
      className="relative bg-[#FAF8F5] py-20 lg:py-28 border-y border-[#E8E4DD] scroll-mt-0"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        {/* Используем ту же сетку и выравнивание по верхнему краю (items-start) */}
        <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-20">
          
          {/* ── Левая колонка: Attribution (5 колонок как в примере) ── */}
          <div
            ref={left.ref as React.Ref<HTMLDivElement>}
            style={left.style}
            className="lg:col-span-5 flex flex-col"
          >
            <div className="mb-10">
              <span className="eyebrow">От основателя</span>
            </div>

            <div className="flex flex-col gap-6">
              <div className="h-16 w-16 overflow-hidden rounded-full border border-[#E8E4DD] grayscale-[0.2] hover:grayscale-0 transition-all duration-700">
                <img
                  src={photoVladimir}
                  alt="Vladimir Gorelov"
                  className="h-full w-full object-cover scale-105"
                />
              </div>
              
              <div>
                <div className="text-[1rem] font-semibold text-[#1A1917] tracking-tight">
                  Владимир Горелов
                </div>
                <div className="mt-1 text-[0.875rem] text-[#78756F]">
                  Steloom
                </div>
              </div>
            </div>

            <div className="mt-12">
              <Link to="/about" className="cta-link">
                О команде
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>

          {/* ── Правая колонка: Цитата (7 колонок) ── */}
          <div
            ref={right.ref as React.Ref<HTMLDivElement>}
            style={right.style}
            className="lg:col-span-7 relative"
          >
            {/* Линия и отступ в точном соответствии с визуальным весом примера */}
            <div className="relative border-l border-[#C86B52]/30 pl-8 lg:pl-12">
              <blockquote className="flex flex-col gap-10">
                <p
                  className="font-serif leading-[1.3] tracking-tight text-[#1A1917]"
                  style={{ fontSize: "clamp(1.75rem, 2.8vw, 2.25rem)" }}
                >
                  «Современные AI-системы умеют быстро отвечать на вопросы. Но в юридической практике этого недостаточно. Каждое заключение должно опираться на документы, быть проверяемым и выдерживать профессиональную оценку».
                </p>

                <p className="text-[1.0625rem] leading-[1.7] text-[#78756F] max-w-2xl italic">
                  «Именно поэтому мы создали Steloom - платформу, которая не заменяет юридическое мышление, а помогает принимать решения на основе прозрачного анализа, подтверждённых фактов и полной прослеживаемости каждого вывода».
                </p>
              </blockquote>

              <div className="mt-12 flex items-center gap-4 opacity-30">

              </div>
            </div>
          </div>

        </div>
      </div>
    </section>
  );
};

export default FounderSection;


