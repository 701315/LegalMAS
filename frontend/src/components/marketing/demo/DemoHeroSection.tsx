import React from "react";
import { demoContent } from "../../../content/demoContent";
import MarketingPageIntro from "../MarketingPageIntro";

const DemoHeroSection: React.FC = () => {
  return (
    <MarketingPageIntro
      eyebrow={demoContent.hero.eyebrow}
      title={demoContent.hero.title}
      description={demoContent.hero.description}
    />
  );
};

export default DemoHeroSection;

