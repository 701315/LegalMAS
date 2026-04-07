# src/api/endpoints/documents/router.py

"""
Aggregate router for document endpoints.
"""

from fastapi import APIRouter

from .detail import router as detail_router
from .exports import router as exports_router
from .extracted_values import router as extracted_values_router
from .family import router as family_router
from .moderation import router as moderation_router
from .pdf_urls import router as pdf_urls_router
from .reclassify import router as reclassify_router
from .structure import router as structure_router

router = APIRouter(prefix="/documents", tags=["documents"])

router.include_router(detail_router)
router.include_router(exports_router)
router.include_router(extracted_values_router)
router.include_router(family_router)
router.include_router(moderation_router)
router.include_router(pdf_urls_router)
router.include_router(reclassify_router)
router.include_router(structure_router)