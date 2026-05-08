// =============================================================
// src/pages/tabs/grid/gridTab.types.ts
// =============================================================

import type { OpenViewerAtPayload } from "../../../types";
import type {
  LayoutElement,
  SizedChunkMeta,
} from "../../../components/viewer/DocumentViewerModal";

export interface GridTabProps {
  dealId: string;
  runId: string | null;
}

export type GridScope = "all" | "global" | "doctype";
export type GridMode = "matrix" | "list";
export type GridDataSource = "legacy" | "review";
export type NormalizedOrigin = "global" | "doctype" | "other";

export type ViewerState = {
  location: OpenViewerAtPayload;
  pdfUrl: string;
  layoutElements?: LayoutElement[];
  sizedChunks?: SizedChunkMeta[];
} | null;


