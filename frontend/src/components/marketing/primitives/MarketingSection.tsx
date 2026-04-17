import React from "react";
import clsx from "clsx";
import { marketingTheme } from "../marketingTheme";

interface MarketingSectionProps {
  children: React.ReactNode;
  className?: string;
  id?: string;
  density?: "base" | "compact" | "relaxed";
}

const densityMap = {
  base: marketingTheme.section.base,
  compact: marketingTheme.section.compact,
  relaxed: marketingTheme.section.relaxed,
};

const MarketingSection: React.FC<MarketingSectionProps> = ({
  children,
  className,
  id,
  density = "base",
}) => {
  return (
    <section id={id} className={clsx(densityMap[density], className)}>
      {children}
    </section>
  );
};

export default MarketingSection;

