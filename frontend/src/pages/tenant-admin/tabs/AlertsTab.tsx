// =============================================================
// src/pages/tenant-admin/tabs/AlertsTab.tsx
//
// "Alerts" tab in the admin panel. Simple wrapper over
// the AlertsPanel component from components/admin/AlertsPanel.
//
// Design contract:
// - Takes all available height of the parent section (min-h-0 flex-1)
// - Vertical overflow — scroll inside the tab
// - Padding around the perimeter
//
// Note: Core logic is in AlertsPanel — this tab only
// provides the layout wrapper and scroll ownership.
// =============================================================

import React from "react";
import { AlertsPanel } from "../../../components/admin/AlertsPanel";

const AlertsTab: React.FC = () => (
  <div className="min-h-0 flex-1 overflow-auto px-5 pb-5 pt-4">
    <AlertsPanel />
  </div>
);

export default AlertsTab;


