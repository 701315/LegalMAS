// src/marketing/pages/DemoPage.tsx
import React from "react";
import SiteHeader from "../components/shared/SiteHeader";
import MarketingPageFooter from "../components/shared/MarketingPageFooter";
import DemoHeroSection from "../components/demo/DemoHeroSection";
import DemoAudienceSection from "../components/demo/DemoAudienceSection";
import DemoWhatYouSeeSection from "../components/demo/DemoWhatYouSeeSection";
import DemoFormSection from "../components/demo/DemoFormSection";
import DemoFaqSection from "../components/demo/DemoFaqSection";

const DemoPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1A1917]">
      <SiteHeader forcedTheme="light" />

      <main
        className="mx-auto px-4 py-16 sm:px-6 lg:px-8 lg:py-24"
        style={{ paddingTop: 132, maxWidth: "var(--container-max-width)" }}
      >
        <DemoHeroSection />
        <DemoAudienceSection />
        <DemoWhatYouSeeSection />
        <DemoFormSection />
        <DemoFaqSection />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default DemoPage;


