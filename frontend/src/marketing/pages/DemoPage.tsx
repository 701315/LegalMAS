import React from "react";
import MarketingPageHeader from "../components/shared/MarketingPageHeader";
import DemoHeroSection from "../components/demo/DemoHeroSection";
import DemoAudienceSection from "../components/demo/DemoAudienceSection";
import DemoWhatYouSeeSection from "../components/demo/DemoWhatYouSeeSection";
import DemoFormSection from "../components/demo/DemoFormSection";
import DemoFaqSection from "../components/demo/DemoFaqSection";

const DemoPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <MarketingPageHeader />

      <main className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <DemoHeroSection />
        <DemoAudienceSection />
        <DemoWhatYouSeeSection />
        <DemoFormSection />
        <DemoFaqSection />
      </main>
    </div>
  );
};

export default DemoPage;

