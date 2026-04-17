import React from "react";

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  align?: "left" | "center";
}

const SectionHeader: React.FC<SectionHeaderProps> = ({
  title,
  subtitle,
  align = "center",
}) => {
  return (
    <div className={align === "center" ? "text-center max-w-3xl mx-auto" : "max-w-3xl"}>
      <h2 className="text-3xl lg:text-4xl font-bold text-white tracking-tight">{title}</h2>
      {subtitle && (
        <p className="mt-4 text-base lg:text-lg text-slate-400 leading-relaxed">{subtitle}</p>
      )}
    </div>
  );
};

export default SectionHeader;

