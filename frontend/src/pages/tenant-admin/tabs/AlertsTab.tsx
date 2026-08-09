// =============================================================
// src/pages/tenant-admin/tabs/AlertsTab.tsx
//
// Вкладка "Алерты" в admin panel. Простая обёртка над AlertsPanel
// компонентом из components/admin/AlertsPanel.
//
// Design contract:
// - Занимает всю доступную высоту parent секции (min-h-0 flex-1)
// - Вертикальный overflow — scroll внутри tab
// - Padding по periметру
//
// Note: содержательная логика в AlertsPanel — этот tab только
// провайдит layout wrapper и scroll ownership.
// =============================================================

import React from "react";
import { AlertsPanel } from "../../../components/admin/AlertsPanel";

const AlertsTab: React.FC = () => (
  <div className="min-h-0 flex-1 overflow-auto px-5 pb-5 pt-4">
    <AlertsPanel />
  </div>
);

export default AlertsTab;


