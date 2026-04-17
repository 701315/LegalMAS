import React from "react";
import { solutionsContent } from "../../../content/solutionsContent";
import MarketingPageIntro from "../MarketingPageIntro";

const SolutionsHeroSection: React.FC = () => {
  return (
    <MarketingPageIntro
      eyebrow={solutionsContent.hero.eyebrow}
      title={solutionsContent.hero.title}
      description={solutionsContent.hero.description}
    />
  );
};

export default SolutionsHeroSection;
