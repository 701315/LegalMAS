import React from "react";
import MarketingPageHeader from "../components/marketing/MarketingPageHeader";
import DemoHeroSection from "../components/marketing/demo/DemoHeroSection";
import DemoAudienceSection from "../components/marketing/demo/DemoAudienceSection";
import DemoWhatYouSeeSection from "../components/marketing/demo/DemoWhatYouSeeSection";
import DemoFormSection from "../components/marketing/demo/DemoFormSection";
import DemoFaqSection from "../components/marketing/demo/DemoFaqSection";

const DemoPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <MarketingPageHeader />

      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
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

