import React from "react";
import clsx from "clsx";
import { marketingTheme } from "../marketingTheme";

interface MarketingSectionTitleProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  align?: "left" | "center";
  className?: string;
}

const MarketingSectionTitle: React.FC<MarketingSectionTitleProps> = ({
  eyebrow,
  title,
  subtitle,
  align = "left",
  className,
}) => {
  return (
    <div
      className={clsx(
        align === "center" ? "mx-auto max-w-3xl text-center" : "max-w-3xl",
        className
      )}
    >
      {eyebrow && <div className={marketingTheme.text.eyebrow}>{eyebrow}</div>}
      <h2 className={clsx("mt-4", marketingTheme.text.title)}>{title}</h2>
      {subtitle && <p className={marketingTheme.text.subtitle}>{subtitle}</p>}
    </div>
  );
};

export default MarketingSectionTitle;
