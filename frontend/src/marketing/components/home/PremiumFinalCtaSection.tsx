// src/marketing/components/home/PremiumFinalCtaSection.tsx

import React, { useEffect, useRef, useState } from "react";

const PremiumFinalCtaSection: React.FC = () => {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.2 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const fadeIn = (delay: number): React.CSSProperties => ({
    opacity: visible ? 1 : 0,
    transform: visible ? "translateY(0)" : "translateY(16px)",
    transition: `opacity 0.8s cubic-bezier(0.16,1,0.3,1) ${delay}ms, transform 0.8s cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
  });

  return (
    <section
      ref={ref}
      className="relative flex items-center justify-center overflow-hidden bg-[#111827]"
      style={{ height: "50vh", minHeight: 320 }}
    >
      <video
        autoPlay
        muted
        loop
        playsInline
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 h-full w-full object-cover"
        style={{ opacity: 0.1 }}
      >
        <source src="/video/cta-bg.mp4" type="video/mp4" />
      </video>

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 70% 60% at 50% 50%, rgba(47,90,74,0.18) 0%, transparent 70%)",
        }}
      />

      <div className="relative mx-auto flex max-w-[1280px] flex-col items-center px-6 text-center lg:px-8">
        <div style={fadeIn(0)}>
          <span className="inline-block rounded-full border border-[#2F5A4A]/50 px-3.5 py-1 text-[11px] font-medium uppercase tracking-[0.09em] text-[#5BA88A]">
            Интеллектуальный слой для юридической работы
          </span>
        </div>

        <h2
          className="mt-5 font-serif font-light text-white"
          style={{
            fontSize: "clamp(28px, 3.5vw, 56px)",
            lineHeight: 1.08,
            letterSpacing: "-0.02em",
            maxWidth: 640,
            ...fadeIn(100),
          }}
        >
          Превращайте документы
          <br />
          в структурированное знание.
        </h2>

        <p
          className="mt-4 text-sm leading-7 text-stone-400"
          style={{ maxWidth: 480, ...fadeIn(200) }}
        >
          Steloom даёт команде проверяемое и пригодное к действию знание
          из любого набора документов — быстро и без потери контроля.
        </p>
      </div>
    </section>
  );
};

export default PremiumFinalCtaSection;


