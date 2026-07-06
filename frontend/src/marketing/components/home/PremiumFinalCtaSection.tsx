// src/marketing/components/home/PremiumFinalCtaSection.tsx
import React, { useEffect, useRef, useState } from "react";
import { landingContent } from "../../content/landingContent";

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

  const { finalCta } = landingContent;

  return (
    <section
      ref={ref}
      className="relative flex items-center justify-center overflow-hidden border-t border-[#E8E4DD] bg-[#F3F0EB]"
      style={{ minHeight: 480 }}
      data-header-theme="light"
    >
      {/* Subtle radial glow — warm terracotta */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 55% at 50% 50%, rgba(200,107,82,0.08) 0%, transparent 70%)",
        }}
      />

      <div
        className="relative mx-auto flex flex-col items-center px-6 py-20 text-center lg:px-8 lg:py-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <h2
          className="mt-6 font-serif text-[#1A1917]"
          style={{
            fontSize: "clamp(2.25rem, 4.5vw, 4rem)",
            lineHeight: 1.08,
            letterSpacing: "-0.02em",
            maxWidth: 720,
            ...fadeIn(100),
          }}
        >
          {finalCta.title.split("\n")[0]}
          <br />
          {finalCta.title.split("\n")[1]}
        </h2>

        <p
          className="mt-5 text-[1.0625rem] leading-[1.7] text-[#78756F]"
          style={{ maxWidth: 560, ...fadeIn(200) }}
        >
          {finalCta.description}
        </p>
      </div>
    </section>
  );
};

export default PremiumFinalCtaSection;


