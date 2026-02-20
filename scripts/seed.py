"""
Seed script — creates test data for development.
Run: python -m scripts.seed
"""

import asyncio
import uuid
import sys
import os

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import settings
from src.core.constants import (
    DealStatus,
    DocumentStatus,
    PIIMode,
    PlaybookStatus,
)
from src.core.logging import setup_logging, get_logger
from src.db.session import get_session
from src.db.repositories import (
    DealRepository,
    DocumentRepository,
    DocumentVersionRepository,
    PlaybookRepository,
)

logger = get_logger(__name__)

# Fixed UUIDs for predictable test data
TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

TEST_DOCUMENTS = [
    {"filename": "SPA_v3.pdf", "folder_path": "01. Key Agreements", "doc_type": "SPA"},
    {"filename": "NDA_Buyer.pdf", "folder_path": "02. NDAs", "doc_type": "NDA"},
    {"filename": "Employment_CEO.pdf", "folder_path": "03. Employment", "doc_type": "Employment"},
    {"filename": "Lease_Office.pdf", "folder_path": "04. Real Estate", "doc_type": "RealEstate"},
    {"filename": "License_FSB.pdf", "folder_path": "05. Licenses", "doc_type": "License"},
]

SAMPLE_CHECKS = {
    "checks": [
        {
            "id": "coc_001",
            "name": "Change of Control Clause",
            "doc_types": ["SPA", "SHA", "Loan"],
            "severity": "critical",
            "detector": {"type": "hybrid"},
        },
        {
            "id": "consent_001",
            "name": "Consent Required",
            "doc_types": ["SPA", "SHA"],
            "severity": "high",
            "detector": {"type": "hybrid"},
        },
        {
            "id": "governing_law_001",
            "name": "Governing Law",
            "doc_types": ["SPA", "NDA", "Employment"],
            "severity": "medium",
            "detector": {"type": "rules"},
        },
    ]
}


async def seed():
    """Create test data in the database."""
    setup_logging()
    logger.info("Starting seed...")

    async with get_session() as session:
        playbook_repo = PlaybookRepository(session)
        deal_repo = DealRepository(session)
        doc_repo = DocumentRepository(session)
        doc_ver_repo = DocumentVersionRepository(session)

        # 1. Create ModelConfig
        logger.info("Creating ModelConfig...")
        model_config = await playbook_repo.create_model_config(
            name="default-v1",
            embeddings_primary="intfloat/multilingual-e5-large",
            embeddings_fallback="cointegrated/LaBSE",
            retrieval_config={"candidate_n": 50, "llm_context_k": 5},
            scoring_config={"dense_weight": 0.6, "sparse_weight": 0.3, "metadata_boost": 0.1},
        )
        logger.info("ModelConfig created", id=str(model_config.id))

        # 2. Create PlaybookVersion (default)
        logger.info("Creating PlaybookVersion...")
        playbook = await playbook_repo.create_version(
            name="M&A_RU",
            semver="1.0.0",
            model_config_id=model_config.id,
            git_commit="seed000000",
            compiled_checks=SAMPLE_CHECKS,
            status=PlaybookStatus.DEFAULT.value,
        )
        logger.info("PlaybookVersion created", id=str(playbook.id), semver=playbook.semver)

        # 3. Create Deal
        logger.info("Creating Deal...")
        deal = await deal_repo.create(
            tenant_id=TENANT_ID,
            name="Test SPA Deal — Alpha Retail Acquisition",
            deal_type="SPA",
            jurisdiction="RU",
            languages=["RU", "EN"],
            pii_mode=PIIMode.LOCAL_ONLY.value,
            profile="full",
            playbook_version_id=playbook.id,
        )
        logger.info("Deal created", id=str(deal.id), name=deal.name)

        # 4. Create Bundle
        from src.db.models.bundle import Bundle
        bundle = Bundle(
            deal_id=deal.id,
            source_type="local",
            status="completed",
            file_count=len(TEST_DOCUMENTS),
        )
        session.add(bundle)
        await session.flush()
        logger.info("Bundle created", id=str(bundle.id))

        # 5. Create Documents + DocumentVersions
        for doc_info in TEST_DOCUMENTS:
            doc = await doc_repo.create(
                deal_id=deal.id,
                bundle_id=bundle.id,
                filename=doc_info["filename"],
                folder_path=doc_info["folder_path"],
                sha256_file=f"fakehash_{doc_info['filename']}",
                status=DocumentStatus.PENDING.value,
            )
            # Set doc_type (normally done by classifier)
            await doc_repo.update_status(
                doc.id,
                status=DocumentStatus.PENDING.value,
                doc_type=doc_info["doc_type"],
            )

            # Create initial DocumentVersion (no refs yet)
            await doc_ver_repo.create(
                document_id=doc.id,
                version_num=1,
            )
            logger.info(
                "Document created",
                id=str(doc.id),
                filename=doc_info["filename"],
                doc_type=doc_info["doc_type"],
            )

    logger.info("Seed completed successfully!")
    logger.info(f"  Tenant ID:  {TENANT_ID}")
    logger.info(f"  Deal ID:    {deal.id}")
    logger.info(f"  Playbook:   {playbook.id} (M&A_RU v1.0.0)")
    logger.info(f"  Documents:  {len(TEST_DOCUMENTS)}")


if __name__ == "__main__":
    asyncio.run(seed())
