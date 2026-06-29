import React, { useState, useEffect, useRef } from "react";
import { ScrollProvider, useScroll } from "../context/ScrollContext";
import LandingHeader from "../components/home/LandingHeader";
import PremiumHeroSection from "../components/home/PremiumHeroSection";
import ConceptTagsSection from "../components/home/ConceptTagsSection";
import KnowledgeGrowthSection from "../components/home/KnowledgeGrowthSection";
import SecurityFoundationSection from "../components/home/SecurityFoundationSection";
import { ApplicationSection } from "../components/home/ApplicationSection";
import ArchitecturePreviewSection from "../components/home/ArchitecturePreviewSection";
import FaqSection from "../components/home/FaqSection";
import PremiumFinalCtaSection from "../components/home/PremiumFinalCtaSection";
import LandingFooter from "../components/home/LandingFooter";
import ContactModal from "../components/home/ContactModal";

const getClosestSnapSection = (container: HTMLElement): HTMLElement | null => {
  const sections = Array.from(
    container.querySelectorAll<HTMLElement>("[data-snap]")
  );

  if (sections.length === 0) return null;

  const scrollTop = container.scrollTop;
  let currentSection: HTMLElement | null = null;
  let minDistance = Infinity;

  for (const section of sections) {
    const distance = Math.abs(section.offsetTop - scrollTop);
    if (distance < minDistance) {
      minDistance = distance;
      currentSection = section;
    }
  }

  return currentSection;
};

const resolveHeaderTheme = (
  section: HTMLElement | null
): "light" | "dark" => {
  return section?.dataset.headerTheme === "dark" ? "dark" : "light";
};

const LandingPageInner: React.FC = () => {
  const { scrollContainerRef, setScrolled, setHeaderTheme } = useScroll();
  const [contactOpen, setContactOpen] = useState(false);
  const [formEmail, setFormEmail] = useState("");
  const [formMessage, setFormMessage] = useState("");
  const isScrolling = useRef(false);

  // Следим за скроллом → обновляем контекст scroll state + header theme
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    let rafId: number | null = null;

    const updateScrollState = () => {
      setScrolled(container.scrollTop > 32);

      const currentSection = getClosestSnapSection(container);
      const nextTheme = resolveHeaderTheme(currentSection);
      setHeaderTheme(nextTheme);
    };

    const handleScroll = () => {
      if (rafId !== null) return;

      rafId = requestAnimationFrame(() => {
        updateScrollState();
        rafId = null;
      });
    };

    updateScrollState();

    container.addEventListener("scroll", handleScroll, { passive: true });

    return () => {
      container.removeEventListener("scroll", handleScroll);
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [scrollContainerRef, setScrolled, setHeaderTheme]);

  // Wheel snap helper
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (isScrolling.current) return;

      const sections = Array.from(
        container.querySelectorAll<HTMLElement>("[data-snap]")
      );
      if (sections.length === 0) return;

      const scrollTop = container.scrollTop;
      const direction = e.deltaY > 0 ? 1 : -1;

      let currentIndex = 0;
      let minDistance = Infinity;

      for (let i = 0; i < sections.length; i++) {
        const distance = Math.abs(sections[i].offsetTop - scrollTop);
        if (distance < minDistance) {
          minDistance = distance;
          currentIndex = i;
        }
      }

      const nextIndex = Math.max(
        0,
        Math.min(sections.length - 1, currentIndex + direction)
      );

      if (nextIndex === currentIndex) return;

      isScrolling.current = true;

      container.scrollTo({
        top: sections[nextIndex].offsetTop,
        behavior: "smooth",
      });

      setTimeout(() => {
        isScrolling.current = false;
      }, 900);
    };

    container.addEventListener("wheel", handleWheel, { passive: false });
    return () => container.removeEventListener("wheel", handleWheel);
  }, [scrollContainerRef]);

  const handleContactSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const subject = encodeURIComponent("Запрос демо Steloom");
    const body = encodeURIComponent(`Email: ${formEmail}\n\n${formMessage}`);
    window.location.href = `mailto:vladimir.gorelov.mail@gmail.com?subject=${subject}&body=${body}`;
  };

  return (
    <>
      <LandingHeader />

      <div
        ref={scrollContainerRef}
        className="bg-[#F8F7F4] text-stone-950 antialiased"
        style={{
          overflowY: "scroll",
          height: "100vh",
          scrollPaddingTop: "68px",
          scrollSnapType: "y mandatory",
        }}
      >
        {/* 1. Hero + теги */}
        <div
          data-snap
          data-header-theme="dark"
          style={{ scrollSnapAlign: "start" }}
        >
          <PremiumHeroSection />
          <ConceptTagsSection />
        </div>

        {/* 2. Возможности — Растущее знание */}
        <div
          data-snap
          data-header-theme="light"
          style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}
        >
          <KnowledgeGrowthSection />
        </div>

        {/* 3. Безопасность — Основание */}
        <div
          data-snap
          data-header-theme="light"
          style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}
        >
          <SecurityFoundationSection />
        </div>

        {/* 4. Применение — Сценарии */}
        <div
          data-snap
          data-header-theme="light"
          style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}
        >
          <ApplicationSection />
        </div>

        {/* 5. Архитектура */}
        <div
          data-snap
          data-header-theme="light"
          style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}
        >
          <ArchitecturePreviewSection />
        </div>

        {/* 6. FAQ + CTA */}
        <div
          data-snap
          data-header-theme="light"
          style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}
        >
          <FaqSection />
          <PremiumFinalCtaSection onOpenContact={() => setContactOpen(true)} />
        </div>

        {/* 7. Футер */}
        <div
          data-snap
          data-header-theme="light"
          style={{ scrollSnapAlign: "start", scrollSnapStop: "always" }}
        >
          <LandingFooter />
        </div>
      </div>

      <ContactModal
        open={contactOpen}
        email={formEmail}
        message={formMessage}
        onEmailChange={setFormEmail}
        onMessageChange={setFormMessage}
        onClose={() => setContactOpen(false)}
        onSubmit={handleContactSubmit}
      />
    </>
  );
};

const LandingPage: React.FC = () => (
  <ScrollProvider>
    <LandingPageInner />
  </ScrollProvider>
);

export default LandingPage;


