import React, { useState } from "react";
import { landingContent } from "../content/landingContent";
import LandingHeader from "../components/marketing/landing/LandingHeader";
import TrustStripSection from "../components/marketing/landing/TrustStripSection";
import PremiumHeroSection from "../components/marketing/landing/PremiumHeroSection";
import CapabilitiesBentoSection from "../components/marketing/landing/CapabilitiesBentoSection";
import WorkflowPreviewSection from "../components/marketing/landing/WorkflowPreviewSection";
import WhyChooseSection from "../components/marketing/landing/WhyChooseSection";
import SecuritySplitSection from "../components/marketing/landing/SecuritySplitSection";
import UseCasesSection from "../components/marketing/landing/UseCasesSection";
import ArchitecturePreviewSection from "../components/marketing/landing/ArchitecturePreviewSection";
import PremiumFinalCtaSection from "../components/marketing/landing/PremiumFinalCtaSection";
import LandingFooter from "../components/marketing/landing/LandingFooter";
import ContactModal from "../components/marketing/landing/ContactModal";

const LandingPage: React.FC = () => {
  const [contactOpen, setContactOpen] = useState(false);
  const [formEmail, setFormEmail] = useState("");
  const [formMessage, setFormMessage] = useState("");

  const handleContactSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const subject = encodeURIComponent("Запрос демо LegalMAS");
    const body = encodeURIComponent(`Email: ${formEmail}\n\n${formMessage}`);
    window.location.href = `mailto:vladimir.gorelov.mail@gmail.com?subject=${subject}&body=${body}`;
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white antialiased">
      <LandingHeader onOpenContact={() => setContactOpen(true)} />
      <PremiumHeroSection onOpenContact={() => setContactOpen(true)} />
      <TrustStripSection />
      <CapabilitiesBentoSection />
      <WorkflowPreviewSection />
      <WhyChooseSection />
      <SecuritySplitSection />
      <UseCasesSection />
      <ArchitecturePreviewSection />
      <PremiumFinalCtaSection onOpenContact={() => setContactOpen(true)} />
      <LandingFooter onOpenContact={() => setContactOpen(true)} />

      <ContactModal
        open={contactOpen}
        email={formEmail}
        message={formMessage}
        onEmailChange={setFormEmail}
        onMessageChange={setFormMessage}
        onClose={() => setContactOpen(false)}
        onSubmit={handleContactSubmit}
      />
    </div>
  );
};

export default LandingPage;