# src/api/endpoints/deals/router.py

from fastapi import APIRouter

from .classification_investigation import router as classification_investigation_router
from .crud import router as crud_router
from .documents import router as documents_router
from .runs import router as runs_router
from .settings import router as settings_router
from .history import router as history_router
from .debug import router as debug_router

router = APIRouter(prefix="/deals", tags=["deals"])

router.include_router(crud_router)
router.include_router(classification_investigation_router)
router.include_router(documents_router)
router.include_router(runs_router)
router.include_router(settings_router)
router.include_router(history_router)
router.include_router(debug_router)