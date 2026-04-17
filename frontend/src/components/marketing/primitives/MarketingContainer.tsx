import React from "react";
import clsx from "clsx";
import { marketingTheme } from "../marketingTheme";

interface MarketingContainerProps {
  children: React.ReactNode;
  size?: "hero" | "section" | "prose";
  className?: string;
}

const MarketingContainer: React.FC<MarketingContainerProps> = ({
  children,
  size = "section",
  className,
}) => {
  return (
    <div className={clsx(marketingTheme.container[size], className)}>
      {children}
    </div>
  );
};

export default MarketingContainer;

