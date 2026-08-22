# src/services/document_layout/service.py

"""
Document Layout Service (v3 Layered Orchestration Final).

Единый координатор и оркестратор всех 10 слоев извлечения макета:
1. DoclingExtractor -> семантические атомы и таблицы;
2. PyMuPDFEnricher -> визуальные стили;
3. PageRegionSegmenter (Layer 1) -> регионы страницы с height-gating 25%;
4. ReadingOrderReconstructor (Layer 2) -> поколоночный естественный порядок чтения;
5. LanguageClassifier (Layer 3) -> классификация языков атомов;
6. StructuralNodeBuilder (Layer 4) -> составные узлы StructuralNodeCandidate;
7. ParallelAligner (Layer 5) -> сопоставление параллельных узлов противоположных языков;
8. Gate 1: Canonical Quality;
9. Сохранение Canonical Layout JSON в S3 (version-scoped);
10. TableSemanticsProcessor (Layer 7 + Layer 6 SpanSplitter) -> ячеечная фильтрация таблиц;
11. MonolingualProjector (Layer 8) -> проекция составных узлов с учётом выравнивания;
12. Gate 2: Projection Quality;
13. CompatibilityBuilder (Layer 10) -> сборка обратно-совместимого макета;
14. Gate 3: Compatibility Quality;
15. Сохранение layout_primary.json в S3 (run-scoped).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from services.document_layout.compatibility_builder import CompatibilityBuilder
from services.document_layout.config import layout_config
from services.document_layout.docling_extractor import DoclingExtractor
from services.document_layout.language_classifier import LanguageClassifier
from services.document_layout.monolingual_projector import MonolingualProjector
from services.document_layout.page_region_segmenter import PageRegionSegmenter
from services.document_layout.parallel_alignment import ParallelAligner
from services.document_layout.pymupdf_enricher import PyMuPDFEnricher
from services.document_layout.quality import (
    validate_canonical_layout,
    validate_compatibility,
    validate_projection,
)
from services.document_layout.reading_order_reconstructor import ReadingOrderReconstructor
from services.document_layout.schemas import CanonicalLayout, CanonicalLayoutValidation
from services.document_layout.span_splitter import SpanSplitter
from services.document_layout.structural_node_builder import StructuralNodeBuilder
from services.document_layout.table_semantics import TableSemanticsProcessor
from storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


@dataclass(slots=True)
class QualityGateError(Exception):
    reason_code: str
    message: str
    details: dict[str, Any]


@dataclass(slots=True)
class PreparedLayoutResult:
    canonical_layout_ref: str
    layout_primary_ref: str
    detected_languages: list[str]
    source_pdf_sha256: str
    total_atoms: int
    projected_atoms: int


class DocumentLayoutService:
    def __init__(
        self,
        extractor: DoclingExtractor | None = None,
        enricher: PyMuPDFEnricher | None = None,
        region_segmenter: PageRegionSegmenter | None = None,
        reading_reconstructor: ReadingOrderReconstructor | None = None,
        classifier: LanguageClassifier | None = None,
        node_builder: StructuralNodeBuilder | None = None,
        aligner: ParallelAligner | None = None,
        splitter: SpanSplitter | None = None,
        table_processor: TableSemanticsProcessor | None = None,
        projector: MonolingualProjector | None = None,
        builder: CompatibilityBuilder | None = None,
        store: ArtifactStore | None = None,
    ):
        self.extractor = extractor or DoclingExtractor()
        self.enricher = enricher or PyMuPDFEnricher()
        self.region_segmenter = region_segmenter or PageRegionSegmenter()
        self.reading_reconstructor = reading_reconstructor or ReadingOrderReconstructor()
        self.classifier = classifier or LanguageClassifier()
        self.node_builder = node_builder or StructuralNodeBuilder()
        self.aligner = aligner or ParallelAligner()
        self.splitter = splitter or SpanSplitter()
        self.table_processor = table_processor or TableSemanticsProcessor(splitter=self.splitter)
        self.projector = projector or MonolingualProjector(splitter=self.splitter)
        self.builder = builder or CompatibilityBuilder(table_processor=self.table_processor)
        self.store = store or ArtifactStore()

    def prepare_document_layout(
        self,
        pdf_bytes: bytes,
        target_language: str,
        document_id: str,
        document_version_id: str,
        run_id: str,
        tenant_id: str,
        deal_id: str,
    ) -> PreparedLayoutResult:

        logger.info(
            "Starting pipeline v3 layered layout preparation",
            document_id=document_id,
            version_id=document_version_id,
            run_id=run_id,
            target_language=target_language,
        )

        # 1. Извлечение структуры из Docling
        atoms, tables, pages, sha256 = self.extractor.extract(
            pdf_bytes=pdf_bytes,
            document_id=document_id,
            document_version_id=document_version_id,
        )

        if not pages or not atoms:
            raise QualityGateError(
                reason_code="CANONICAL_EXTRACTION_EMPTY",
                message="Canonical extraction returned 0 pages or text atoms",
                details={"total_pages": len(pages), "total_atoms": len(atoms)},
            )

        # 2. Визуальное обогащение через PyMuPDF
        enriched_atoms = self.enricher.enrich(pdf_bytes, atoms)

        # 3. Layer 1 & 2: Геометрическая сегментация регионов + Поколоночный порядок чтения
        reordered_atoms: list[Any] = []
        all_regions: list[Any] = []

        for page in pages:
            page_atoms = [a for a in enriched_atoms if a.page == page.page_number]
            page_copy = page.model_copy(update={"atoms": page_atoms})

            regions = self.region_segmenter.segment_page(page_copy)
            all_regions.extend(regions)

            page_ordered_atoms = self.reading_reconstructor.reconstruct_page_reading_order(
                page_copy, regions
            )
            reordered_atoms.extend(page_ordered_atoms)

        # 4. Layer 3: Классификация языков атомов
        classified_atoms = self.classifier.classify_atoms(reordered_atoms)

        detected_langs = sorted(
            list(
                {
                    atom.language
                    for atom in classified_atoms
                    if atom.language not in ("shared", "mixed")
                }
            )
        )

        # 5. Layer 4: Построение составных узлов StructuralNodeCandidate
        node_candidates = []
        for page in pages:
            page_atoms = [a for a in classified_atoms if a.page == page.page_number]
            page_regions = [r for r in all_regions if r.page == page.page_number]
            page_nodes = self.node_builder.build_page_nodes(page_atoms, page_regions)
            node_candidates.extend(page_nodes)

        # 6. Layer 5: Выравнивание параллельных узлов противоположных языков
        alignment_result = self.aligner.align_nodes(node_candidates, target_language)

        # 7. Сборка модели CanonicalLayout
        lang_dist: dict[str, int] = {}
        marker_count = 0
        marker_only_count = 0
        for atom in classified_atoms:
            lang_dist[atom.language] = lang_dist.get(atom.language, 0) + 1
            if atom.marker:
                marker_count += 1
            if atom.is_marker_only:
                marker_only_count += 1

        validation_canonical = CanonicalLayoutValidation(
            total_text_atoms=len(classified_atoms),
            total_tables=len(tables),
            marker_count=marker_count,
            marker_only_count=marker_only_count,
            language_distribution=lang_dist,
        )

        for page in pages:
            page.atoms = [atom for atom in classified_atoms if atom.page == page.page_number]

        canonical_layout = CanonicalLayout(
            schema_version="canonical_layout_v1",
            document_id=document_id,
            document_version_id=document_version_id,
            source_pdf_sha256=sha256,
            page_count=len(pages),
            detected_languages=detected_langs,
            pages=pages,
            tables=tables,
            validation=validation_canonical,
        )

        # 8. Gate 1: Валидация Canonical Layout
        gate1 = validate_canonical_layout(canonical_layout)
        if not gate1.passed:
            raise QualityGateError(
                reason_code=gate1.reason_code or "CANONICAL_QUALITY_FAILED",
                message=gate1.message or "Canonical quality gate failed",
                details=gate1.details,
            )

        # 9. Сохранение Canonical Layout в S3
        canonical_path = ArtifactPath.canonical_layout(
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=document_id,
            document_version_id=document_version_id,
        )
        canonical_layout_ref = self.store.put_json(
            canonical_path, canonical_layout.model_dump()
        )

        # 10. Layer 8: Моноязычная проекция СОСТАВНЫХ УЗЛОВ с учётом выравнивания
        projection = self.projector.project_nodes(
            node_candidates, target_language, alignment_result=alignment_result
        )

        # 11. Gate 2: Валидация Projection
        gate2 = validate_projection(canonical_layout, projection, target_language)
        if not gate2.passed:
            raise QualityGateError(
                reason_code=gate2.reason_code or "PROJECTION_QUALITY_FAILED",
                message=gate2.message or "Projection quality gate failed",
                details=gate2.details,
            )

        # 12. Layer 10: Сборка обратно-совместимого макета
        compat_payload = self.builder.build_layout_primary(
            projection_result=projection,
            canonical_tables=tables,
            document_id=document_id,
            document_version_id=document_version_id,
            run_id=run_id,
            target_language=target_language,
            source_canonical_layout_ref=canonical_layout_ref,
        )

        # 13. Gate 3: Валидация Compatibility
        gate3 = validate_compatibility(compat_payload)
        if not gate3.passed:
            raise QualityGateError(
                reason_code=gate3.reason_code or "COMPATIBILITY_QUALITY_FAILED",
                message=gate3.message or "Compatibility quality gate failed",
                details=gate3.details,
            )

        # 14. Сохранение layout_primary в S3
        primary_path = ArtifactPath.run_layout_primary(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            document_id=document_id,
        )
        layout_primary_ref = self.store.put_json(primary_path, compat_payload)

        logger.info(
            "Document layout processing completed successfully (v3 layered final)",
            document_id=document_id,
            canonical_layout_ref=canonical_layout_ref,
            layout_primary_ref=layout_primary_ref,
            detected_languages=detected_langs,
        )

        return PreparedLayoutResult(
            canonical_layout_ref=canonical_layout_ref,
            layout_primary_ref=layout_primary_ref,
            detected_languages=detected_langs,
            source_pdf_sha256=sha256,
            total_atoms=len(classified_atoms),
            projected_atoms=projection.projected_atom_count,
        )
