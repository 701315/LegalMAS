import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useScrollReveal } from "../../../hooks/useScrollReveal";
import photoVladimir from "../assets/photos/vladimir.jpg";

/**
 * FounderSection — крупный портрет + цитата.
 * Фотография теперь является центральным визуальным элементом.
 */

const FounderSection: React.FC = () => {
  const left = useScrollReveal(0);
  const right = useScrollReveal(120);

  return (
    <section
      id="founder"
      className="relative bg-[#FAF8F5] py-24 lg:py-36 border-y border-[#E8E4DD]"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid items-center gap-16 lg:grid-cols-12 lg:gap-24">
          
          {/* ── Левая колонка: Крупный портрет (5 колонок) ────────────── */}
          <div
            ref={left.ref as React.Ref<HTMLDivElement>}
            style={left.style}
            className="lg:col-span-5"
          >
            <div className="relative group">
              {/* Рамка с закруглением как в блоке "Команда" */}
              <div className="aspect-[4/5] w-full overflow-hidden rounded-[2.5rem] border border-[#E8E4DD] bg-[#F3F0EB] shadow-sm transition-all duration-1000">
                <img
                  src={photoVladimir}
                  alt="Владимир Горелов"
                  className="h-full w-full object-cover grayscale-[0.3] group-hover:grayscale-0 transition-all duration-1000 scale-[1.02] group-hover:scale-105"
                />
              </div>
              
              {/* Подпись под фото */}
              <div className="mt-8">
                <div className="text-[1.125rem] font-serif italic text-[#1A1917]">
                  Владимир Горелов
                </div>
                <div className="mt-1 text-[0.8125rem] uppercase tracking-widest text-[#C86B52] font-bold">
                  Основатель Steloom
                </div>
              </div>
            </div>
          </div>

          {/* ── Правая колонка: Манифест и цитата (7 колонок) ─────────── */}
          <div
            ref={right.ref as React.Ref<HTMLDivElement>}
            style={right.style}
            className="lg:col-span-7"
          >
            <div className="relative border-l border-[#C86B52]/20 pl-8 lg:pl-16">
              <p className="eyebrow mb-12">От основателя</p>
              
              <blockquote className="flex flex-col gap-10">
                <p
                  className="font-serif leading-[1.2] tracking-tight text-[#1A1917]"
                  style={{ fontSize: "clamp(2rem, 3.5vw, 2.75rem)" }}
                >
                  «Современные AI-системы умеют быстро отвечать на вопросы. Но в юридической практике этого недостаточно».
                </p>

                <div className="space-y-6">
                  <p className="text-[1.125rem] leading-[1.7] text-[#78756F] max-w-2xl font-light">
                    Каждое заключение должно опираться на документы, быть проверяемым и выдерживать профессиональную оценку.
                  </p>
                  <p className="text-[1.125rem] leading-[1.7] text-[#1A1917] max-w-2xl italic font-serif opacity-80">
                    «Именно поэтому мы создали Steloom - платформу, которая не заменяет юридическое мышление, а помогает принимать решения на основе прозрачного анализа».
                  </p>
                </div>
              </blockquote>

              <div className="mt-16">
                <Link to="/about" className="cta-link group inline-flex items-center gap-2 text-[0.9375rem] font-semibold text-[#1A1917]">
                  Познакомиться с командой
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                </Link>
              </div>
            </div>
          </div>

        </div>
      </div>
    </section>
  );
};

export default FounderSection;


