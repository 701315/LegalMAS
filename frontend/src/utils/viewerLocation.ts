import type { OpenViewerAtPayload } from "../types";

export type RawViewerLocation =
  | {
      page?: number | null;
      start_page?: number | null;
      clause_uid?: string | null;
      element_id?: string | null;
      segment_id?: string | null;
      chunk_id?: string | null;
      chunk_index?: number | null;
    }
  | null
  | undefined;

export function buildViewerLocationPayload(
  documentId: string,
  loc?: RawViewerLocation,
): OpenViewerAtPayload {
  const payload: OpenViewerAtPayload = { documentId };

  const page = loc?.page ?? loc?.start_page ?? undefined;
  if (typeof page === "number") {
    payload.page = page;
  }

  if (loc?.clause_uid) {
    payload.clauseUid = loc.clause_uid;
  }

  if (loc?.element_id) {
    payload.elementId = loc.element_id;
  }

  if (loc?.segment_id) {
    payload.segmentId = loc.segment_id;
  }

  if (loc?.chunk_id) {
    payload.chunkId = loc.chunk_id;
  }

  if (typeof loc?.chunk_index === "number") {
    payload.chunkIndex = loc.chunk_index;
  }

  return payload;
}

