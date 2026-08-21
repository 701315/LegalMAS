"""
Document Layout Service (Phase 7).

Единый координатор и оркестратор извлечения макета:
1. Загрузка PDF;
2. DoclingExtractor -> семантические атомы;
3. PyMuPDFEnricher -> визуальные стили;
4. LanguageClassifier -> языковая разметка;
5. Gate 1: Canonical Quality;
6. Спишется Canonical Layout JSON в S3 (version-scoped);
7. MonolingualProjector -> проекция на целевой язык;
8. Gate 2: Projection Quality;
9. Compatibility Builder -> сборка макета;
10. Gate 3: Compatibility Quality;
11. Спишется layout_primary.json в S3 (run-scoped).
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
from services.document_layout.pymupdf_enricher import PyMuPDFEnricher
from services.document_layout.quality import (
    validate_canonical_layout,
    validate_compatibility,
    validate_projection,
)
from services.document_layout.schemas import CanonicalLayout, CanonicalLayoutValidation
from storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


@dataclass(slots=True)
class QualityGateError(Exception):
    """Исключение при провале любого гейта качества."""

    reason_code: str
    message: str
    details: dict[str, Any]


@dataclass(slots=True)
class PreparedLayoutResult:
    """Результат успешной оркестрации извлечения макета."""

    canonical_layout_ref: str
    layout_primary_ref: str
    detected_languages: list[str]
    source_pdf_sha256: str
    total_atoms: int
    projected_atoms: int


class DocumentLayoutService:
    """
    Оркестратор извлечения и проекции макета документа (v2).
    """

    def __init__(
        self,
        extractor: DoclingExtractor | None = None,
        enricher: PyMuPDFEnricher | None = None,
        classifier: LanguageClassifier | None = None,
        projector: MonolingualProjector | None = None,
        builder: CompatibilityBuilder | None = None,
        store: ArtifactStore | None = None,
    ):
        self.extractor = extractor or DoclingExtractor()
        self.enricher = enricher or PyMuPDFEnricher()
        self.classifier = classifier or LanguageClassifier()
        self.projector = projector or MonolingualProjector()
        self.builder = builder or CompatibilityBuilder()
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
        """
        Полный цикл обработки документа.
        Выбрасывает QualityGateError при провале проверок качества.
        """
        logger.info(
            "Starting pipeline v2 layout preparation for document",
            document_id=document_id,
            version_id=document_version_id,
            run_id=run_id,
            target_language=target_language,
        )

        # 1. Извлечение структуры из Docling (Фаза 1)
        atoms, tables, pages, sha256 = self.extractor.extract(
            pdf_bytes=pdf_bytes,
            document_id=document_id,
            document_version_id=document_version_id,
        )

        # Fail-fast пред-гейт: если извлечено 0 страниц или 0 атомов
        if not pages or not atoms:
            raise QualityGateError(
                reason_code="CANONICAL_EXTRACTION_EMPTY",
                message="Canonical extraction returned 0 pages or text atoms",
                details={"total_pages": len(pages), "total_atoms": len(atoms)},
            )

        # 2. Визуальное обогащение через PyMuPDF (Фаза 2)
        enriched_atoms = self.enricher.enrich(pdf_bytes, atoms)

        # 3. Классификация языков атомов (Фаза 3)
        classified_atoms = self.classifier.classify_atoms(enriched_atoms)

        # Сбор уникальных авторитетных языков
        detected_langs = sorted(
            list(
                {
                    atom.language
                    for atom in classified_atoms
                    if atom.language not in ("shared", "mixed")
                }
            )
        )

        # 4. Сборка модели CanonicalLayout
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

        # 5. Рубеж качества 1: Валидация Canonical Layout (Фаза 6)
        gate1 = validate_canonical_layout(canonical_layout)
        if not gate1.passed:
            logger.error("Quality Gate 1 (Canonical) failed!", details=gate1.details)
            raise QualityGateError(
                reason_code=gate1.reason_code or "CANONICAL_QUALITY_FAILED",
                message=gate1.message or "Canonical quality gate failed",
                details=gate1.details,
            )

        # 6. Сохранение Canonical Layout в S3 (version-scoped, immutable)
        canonical_path = ArtifactPath.canonical_layout(
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=document_id,
            document_version_id=document_version_id,
        )
        canonical_layout_ref = self.store.put_json(
            canonical_path, canonical_layout.model_dump()
        )

        # 7. Моноязычная проекция (Фаза 4)
        projection = self.projector.project(classified_atoms, target_language)

        # 8. Рубеж качества 2: Валидация Projection (Фаза 6)
        gate2 = validate_projection(canonical_layout, projection, target_language)
        if not gate2.passed:
            logger.error("Quality Gate 2 (Projection) failed!", details=gate2.details)
            raise QualityGateError(
                reason_code=gate2.reason_code or "PROJECTION_QUALITY_FAILED",
                message=gate2.message or "Projection quality gate failed",
                details=gate2.details,
            )

        # 9. Сборка обратно-совместимого макета (Фаза 5)
        compat_payload = self.builder.build_layout_primary(
            projection_result=projection,
            canonical_tables=tables,
            document_id=document_id,
            document_version_id=document_version_id,
            run_id=run_id,
            target_language=target_language,
            source_canonical_layout_ref=canonical_layout_ref,
        )

        # 10. Рубеж качества 3: Валидация Compatibility (Фаза 6)
        gate3 = validate_compatibility(compat_payload)
        if not gate3.passed:
            logger.error("Quality Gate 3 (Compatibility) failed!", details=gate3.details)
            raise QualityGateError(
                reason_code=gate3.reason_code or "COMPATIBILITY_QUALITY_FAILED",
                message=gate3.message or "Compatibility quality gate failed",
                details=gate3.details,
            )

        # 11. Сохранение layout_primary в S3 (run-scoped, isolated)
        primary_path = ArtifactPath.run_layout_primary(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            document_id=document_id,
        )
        layout_primary_ref = self.store.put_json(primary_path, compat_payload)

        logger.info(
            "Document layout processing completed successfully",
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
