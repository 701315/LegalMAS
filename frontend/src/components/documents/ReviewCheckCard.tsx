// src/components/documents/ReviewCheckCard.tsx

import React, { useState } from "react";
import type { DocumentReviewCheckView } from "./DocumentDetails";
import type { OpenViewerAtFn } from "../../types";
import { SeverityBadge } from "../ui/SeverityBadge";

interface Props {
  check: DocumentReviewCheckView;
  documentId: string;
  onOpenCell?: (checkId: string, checkName: string) => void;
  onOpenAtLocation?: OpenViewerAtFn;
}

export const ReviewCheckCard: React.FC<Props> = ({
  check,
  documentId,
  onOpenCell,
  onOpenAtLocation,
}) => {
  const [expanded, setExpanded] = useState(false);

  const hasSegment = check.segmentId || check.segmentTitle;
  const hasEvidence = check.snippet || check.page != null || check.clauseUid;

  return (
    <div className="rounded-lg border border-gray-200 bg-white text-xs">
      {/* Header row */}
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 px-3 py-2.5 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex flex-col gap-1 min-w-0">
          <span className="font-medium text-gray-900 truncate">
            {check.checkName}
          </span>
          {hasSegment && (
            <span className="text-[10px] text-gray-400 truncate">
              {check.segmentTitle || check.segmentType || check.segmentId}
              {check.chunkIndex != null && ` · Chunk #${check.chunkIndex}`}
            </span>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {check.severity && (
            <div className="scale-90 origin-right">
              <SeverityBadge severity={check.severity} />
            </div>
          )}
          {check.result === "unclear" && (
            <span className="inline-flex items-center rounded border border-yellow-200 bg-yellow-50 px-1.5 py-0.5 text-[10px] text-yellow-700">
              Unclear
            </span>
          )}
          <span className="text-gray-400">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="border-t border-gray-100 px-3 py-2.5 space-y-2">
          {/* Snippet */}
          {check.snippet && (
            <p className="leading-5 text-gray-700 italic">
              &ldquo;{check.snippet}&rdquo;
            </p>
          )}

          {/* Location */}
          {(check.page != null || check.clauseUid) && (
            <div className="flex flex-wrap gap-3 text-[10px] text-gray-500">
              {check.page != null && <span>Страница: {check.page}</span>}
              {check.clauseUid && <span>Clause: {check.clauseUid}</span>}
            </div>
          )}

          {/* Segment detail */}
          {hasSegment && (
            <div className="rounded bg-gray-50 px-2 py-1.5 text-[10px] text-gray-600 space-y-0.5">
              {check.segmentTitle && (
                <div>
                  <span className="text-gray-400">Сегмент: </span>
                  {check.segmentTitle}
                  {check.isPrimarySegment && (
                    <span className="ml-1.5 text-blue-600 font-medium">
                      (основной)
                    </span>
                  )}
                </div>
              )}
              {check.segmentType && (
                <div>
                  <span className="text-gray-400">Тип: </span>
                  {check.segmentType}
                </div>
              )}
              {check.chunkIndex != null && (
                <div>
                  <span className="text-gray-400">Chunk #</span>
                  {check.chunkIndex}
                </div>
              )}
            </div>
          )}

          {/* Extracted fields (collapsed) */}
          {check.extractedFields.length > 0 && (
            <div className="space-y-1">
              {check.extractedFields.map((f, i) => (
                <div
                  key={`${f.fieldName}-${i}`}
                  className="flex items-start justify-between gap-2 text-[10px]"
                >
                  <span className="text-gray-500">{f.fieldName}</span>
                  <span className="font-medium text-gray-800 text-right max-w-[55%] break-words">
                    {f.fieldValue}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {onOpenCell && (
              <button
                type="button"
                className="text-[11px] text-blue-600 hover:underline"
                onClick={() => onOpenCell(check.checkId, check.checkName)}
              >
                Детали в DD Matrix →
              </button>
            )}
            {onOpenAtLocation && hasEvidence && (
              <button
                type="button"
                className="text-[11px] text-blue-600 hover:underline"
                onClick={() =>
                  onOpenAtLocation({
                    documentId,
                    page: check.page,
                    clauseUid: check.clauseUid,
                    elementId: null,
                    segmentId: check.segmentId,
                    chunkId: check.chunkId,
                    chunkIndex: check.chunkIndex,
                  })
                }
              >
                Открыть в документе →
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

