// frontend/src/components/marketing/security/SecurityTrustSection.tsx

import React from "react";
import { securityContent } from "../../../content/securityContent";

const SecurityTrustSection: React.FC = () => {
  return (
    <section className="mt-10">
      <div className="flex flex-wrap gap-2">
        {securityContent.trustBadges.map((badge) => (
          <div
            key={badge}
            className="rounded-full border border-[#E5E2DA] bg-white px-4 py-2 text-xs font-medium text-stone-600"
          >
            {badge}
          </div>
        ))}
      </div>
    </section>
  );
};

export default SecurityTrustSection;

