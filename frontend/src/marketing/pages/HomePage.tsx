import React from "react";
import SiteHeader from "../components/shared/SiteHeader";
import PremiumHeroSection from "../components/home/PremiumHeroSection";
import ConceptTagsSection from "../components/home/ConceptTagsSection";
import KnowledgeGrowthSection from "../components/home/KnowledgeGrowthSection";
import SecurityFoundationSection from "../components/home/SecurityFoundationSection";
import { ApplicationSection } from "../components/home/ApplicationSection";
import FounderSection from "../components/home/FounderSection";
import FaqSection from "../components/home/FaqSection";
import PremiumFinalCtaSection from "../components/home/PremiumFinalCtaSection";
import SiteFooter from "../components/shared/SiteFooter";
import { ContactModalProvider } from "../context/ContactModalContext";

const HomePage: React.FC = () => {
  return (
    <ContactModalProvider>
      <SiteHeader variant="landing" />

      <main className="text-[#1A1917]"> {/* Фиксируем основной цвет для всего контента */}
        <PremiumHeroSection />
        
        {/* Каждую светлую секцию на всякий случай подтверждаем цветом */}
        <div className="bg-[#FAF8F5] text-[#1A1917]">
           <ConceptTagsSection />
           <KnowledgeGrowthSection />
           <SecurityFoundationSection />
           <ApplicationSection />
           <FounderSection />
           <FaqSection />
           <PremiumFinalCtaSection />
        </div>
      </main>

      <SiteFooter />
    </ContactModalProvider>
  );
};

export default HomePage;

