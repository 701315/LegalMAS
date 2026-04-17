import React from "react";
import { securityContent } from "../../../content/securityContent";

const SecurityTrustSection: React.FC = () => {
  return (
    <section className="mt-12">
      <div className="flex flex-wrap gap-3">
        {securityContent.trustBadges.map((badge) => (
          <div
            key={badge}
            className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-200"
          >
            {badge}
          </div>
        ))}
      </div>
    </section>
  );
};

export default SecurityTrustSection;

