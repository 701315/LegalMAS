// =============================================================
// src/pages/tabs/GridTab.tsx
// Стабильная точка входа для вкладки DD Grid.
//
// V1.12.4:
// - вкладка полностью переведена на DD Grid V1 (dd-grid-v1 endpoint);
// - визуал и UX идентичны предыдущей реализации;
// - QC / Export / Filters переиспользуются через legacy-адаптер;
// - иерархические V1-заголовки матрицы и V1-drawer будут подключены
//   отдельными шагами (V1.12.5 / V1.12.7).
//
// Legacy grid/GridTabPage.tsx оставлен в репозитории как reference,
// но точкой входа больше не является.
// =============================================================

import React from "react";

import DDGridV1TabPage from "./dd-grid-v1/DDGridV1TabPage";
import type { GridTabProps } from "./grid/gridTab.types";

export const GridTab: React.FC<GridTabProps> = (props) => {
  return <DDGridV1TabPage {...props} />;
};

export default GridTab;



