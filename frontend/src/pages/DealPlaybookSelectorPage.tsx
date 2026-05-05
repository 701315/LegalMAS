// =============================================================
// src/pages/DealPlaybookSelectorPage.tsx
// Выбор / создание playbook для конкретной сделки.
// Приведено к единому product-дизайну workspace.
// =============================================================

import React from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import DealPlaybookSelectorPanel from "../components/playbook/DealPlaybookSelectorPanel";
import type { Deal } from "../types";

interface DealPlaybookSelectorPageProps {
  deal?: Deal;
}

const DealPlaybookSelectorPage: React.FC<DealPlaybookSelectorPageProps> = ({
  deal,
}) => {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();

  if (!dealId) {
    return <Navigate to="/deals" replace />;
  }

  return (
    <DealPlaybookSelectorPanel
      dealId={dealId}
      deal={deal}
      mode="page"
      onCancel={() => navigate(`/projects/${dealId}`)}
      onFinished={() => navigate(`/projects/${dealId}`)}
    />
  );
};

export default DealPlaybookSelectorPage;

