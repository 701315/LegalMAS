import React from "react";
import type {
  PipelineStageViewDTO,
  StructurePreviewDTO,
  StructureSectionPreviewDTO,
} from "../../../types";

interface Props {
  stage: PipelineStageViewDTO;
}

function isStructurePreview(
  preview: PipelineStageViewDTO["preview"],
): preview is StructurePreviewDTO {
  return !!preview && preview.type === "structure";
}

export const StructureStageViewer: React.FC<Props> = ({ stage }) => {
  const preview = stage.preview;

  if (!isStructurePreview(preview)) {
    return (
      <div className="text-sm text-gray-500">
        Для этой стадии нет STRUCTURE‑превью.
      </div>
    );
  }

  const meta = stage.meta;
  const textEnriched = meta?.text_enriched === true;
  const sections = preview.sections ?? [];

  return (
    <div className="flex h-full gap-4">
      <div className="w-72 shrink-0 border-r border-gray-200 pr-4">
        <div className="mb-3 space-y-1">
          <p className="text-xs font-medium text-gray-700 flex items-center gap-2">
            STRUCTURE
            <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium bg-gray-100 text-gray-700 border border-gray-200">
              {stage.representation.view_mode}
            </span>
          </p>

          <p className="text-[11px] text-gray-500">
            {stage.representation.label}
          </p>

          {stage.representation.provenance?.preview_source_label && (
            <p className="text-[11px] text-gray-400">
              {stage.representation.provenance.preview_source_label}
            </p>
          )}

          {textEnriched ? (
            <p className="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-100 rounded px-2 py-1 mt-1">
              Текст секций обогащён из CHUNKS по clause_uid.
            </p>
          ) : (
            <p className="text-[11px] text-gray-500 bg-gray-50 border border-gray-100 rounded px-2 py-1 mt-1">
              Используется текст из clause tree (canonical STRUCTURE).
            </p>
          )}

          {meta?.section_count != null && (
            <p className="text-[11px] text-gray-400 mt-1">
              Секций: {meta.section_count}
            </p>
          )}
        </div>

        <div className="space-y-1 overflow-auto max-h-[calc(100vh-200px)] pr-1">
          {sections.map((section) => (
            <SectionItem key={section.id} section={section} />
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <StructureSectionsDetail sections={sections} textEnriched={textEnriched} />
      </div>
    </div>
  );
};

interface SectionItemProps {
  section: StructureSectionPreviewDTO;
}

const SectionItem: React.FC<SectionItemProps> = ({ section }) => {
  const indent = (section.level ?? 1) - 1;
  const hasClauseUid = !!section.clause_uid;

  return (
    <div
      className="flex items-center text-xs text-gray-700 py-0.5"
      title={
        hasClauseUid
          ? `clause_uid: ${section.clause_uid}`
          : "Для этой секции нет clause_uid"
      }
      style={{ paddingLeft: `${indent * 10}px` }}
    >
      <span className="truncate">
        {section.title || "Без названия"}
      </span>

      {hasClauseUid && (
        <span className="ml-2 inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-100">
          clause_uid
        </span>
      )}
    </div>
  );
};

interface StructureSectionsDetailProps {
  sections: StructureSectionPreviewDTO[];
  textEnriched: boolean;
}

const StructureSectionsDetail: React.FC<StructureSectionsDetailProps> = ({
  sections,
  textEnriched,
}) => {
  if (!sections.length) {
    return (
      <div className="text-sm text-gray-500">
        В STRUCTURE пока нет секций.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {sections.map((section) => (
        <SectionBlock
          key={section.id}
          section={section}
          textEnriched={textEnriched}
        />
      ))}
    </div>
  );
};

interface SectionBlockProps {
  section: StructureSectionPreviewDTO;
  textEnriched: boolean;
}

const SectionBlock: React.FC<SectionBlockProps> = ({
  section,
  textEnriched,
}) => {
  const hasClauseUid = !!section.clause_uid;
  const pageRange =
    section.page_from != null || section.page_to != null
      ? `${section.page_from ?? "?"}–${section.page_to ?? "?"}`
      : null;

  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-white">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold text-gray-800">
            {section.title || "Без названия"}
          </p>
          <p className="text-[11px] text-gray-400">
            Уровень: {section.level ?? 1}
            {pageRange && ` · стр.: ${pageRange}`}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {hasClauseUid && (
            <span className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-100">
              clause_uid
            </span>
          )}
          {textEnriched && (
            <span className="inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-100">
              enriched
            </span>
          )}
        </div>
      </div>

      {section.text_preview && (
        <pre className="mt-2 text-xs text-gray-800 whitespace-pre-wrap bg-gray-50 rounded-md px-2 py-1 max-h-64 overflow-auto">
          {section.text_preview}
        </pre>
      )}

      {!section.text_preview && (
        <p className="mt-2 text-xs text-gray-400">
          Для этой секции нет текстового превью.
        </p>
      )}
    </div>
  );
};

