// frontend/src/pages/tenant-instructions/TenantBasePlaybooksPage.tsx

import React from "react";
import PlaybookStudioPage from "../playbooks/PlaybookStudioPage";

const TenantBasePlaybooksPage: React.FC = () => {
  return <PlaybookStudioPage scope="tenant" />;
};

export default TenantBasePlaybooksPage;

