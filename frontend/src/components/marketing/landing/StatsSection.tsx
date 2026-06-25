// src/components/marketing/landing/StatsSection.tsx

import React, { useEffect, useRef, useState } from "react";
import { useCountUp } from "../../../hooks/useCountUp";
import { landingContent } from "../../../content/landingContent";

function StatItem({
  value, suffix, prefix, label, sub, trigger,
}: {
  value: number; suffix: string; prefix?: string;
  label: string; sub: string; trigger: boolean;
}) {
  const count = useCountUp(value, 1600, trigger);
  return (
    <div className="flex flex-col items-center text-center">
      <div
        className="font-serif font-light text-stone-950"
        style={{ fontSize: "clamp(56px, 5vw, 80px)", lineHeight: 1, letterSpacing: "-0.03em" }}
      >
        {prefix}{count}{suffix}
      </div>
      <div className="mt-3 text-sm font-medium text-stone-800">{label}</div>
      <div className="mt-1 text-xs text-stone-400">{sub}</div>
    </div>
  );
}

const StatsSection: React.FC = () => {
  const ref = useRef<HTMLElement | null>(null);
  const [triggered, setTriggered] = useState(false);
  const [visible, setVisible] = useState(false);
  const { stats } = landingContent;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setTriggered(true);
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.2 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={ref}
      className="bg-[#F8F7F4] py-24"
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(20px)",
        transition: "opacity 0.7s ease, transform 0.7s ease",
      }}
    >
      <div className="mx-auto max-w-[1280px] px-6 lg:px-8">

        {/* Заголовок */}
        <div className="max-w-2xl">
          <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone-500">
            {stats.eyebrow}
          </div>
          <h2 className="mt-4 font-serif text-4xl leading-tight tracking-[-0.03em] text-stone-950 lg:text-5xl">
            {stats.title.split("\n").map((line, i) => (
              <React.Fragment key={i}>{line}{i === 0 && <br />}</React.Fragment>
            ))}
          </h2>
          <p className="mt-4 text-sm leading-7 text-stone-500">
            {stats.description}
          </p>
        </div>

        {/* Числа */}
        <div className="mt-14 rounded-[32px] border border-[#E5E2DA] bg-white px-8 py-14">
          <div className="grid grid-cols-1 divide-y divide-[#E5E2DA] md:grid-cols-3 md:divide-x md:divide-y-0">
            {stats.items.map((s, i) => (
              <div
                key={s.label}
                className={i > 0 ? "pt-10 md:pt-0 md:pl-12" : "pb-10 md:pb-0 md:pr-12"}
              >
                <StatItem {...s} trigger={triggered} />
              </div>
            ))}
          </div>

          <p
            className="mx-auto mt-10 text-center font-serif text-sm italic text-stone-400"
            style={{ maxWidth: 580, lineHeight: 1.8 }}
          >
            "{stats.quote}"
          </p>
        </div>
      </div>
    </section>
  );
};

export default StatsSection;

