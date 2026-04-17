import React from "react";
import clsx from "clsx";
import { marketingTheme } from "../marketingTheme";

interface MarketingBadgeProps {
  children: React.ReactNode;
  className?: string;
  tone?: "default" | "success";
}

const MarketingBadge: React.FC<MarketingBadgeProps> = ({
  children,
  className,
  tone = "default",
}) => {
  return (
    <div
      className={clsx(
        tone === "success" ? marketingTheme.badge.success : marketingTheme.badge.base,
        className
      )}
    >
      {children}
    </div>
  );
};

export default MarketingBadge;

