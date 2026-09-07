"""
Glossary resolver to merge platform-wide and tenant-specific terms (Sprint 3.2).
"""

from __future__ import annotations

import uuid

from db.repositories.legal_glossary_repo import LegalGlossaryRepository


class GlossaryResolver:
    """
    Resolves legal glossary terms into a single flat key-value dictionary.

    Ensures that client-specific mappings (tenant_id NOT NULL) explicitly
    override general platform mappings (tenant_id IS NULL).
    """

    def __init__(self, repo: LegalGlossaryRepository):
        self.repo = repo

    async def resolve_terms(
        self,
        tenant_id: uuid.UUID | None,
        source_locale: str,
        target_locale: str,
    ) -> dict[str, str]:
        """
        Resolve active terms into a unified mapping: source_term -> target_term.

        Overriding algorithm:
        1. Query the database for both platform and tenant active terms.
        2. Partition them into platform_terms dict and tenant_terms dict.
        3. Merge: `resolved = {**platform_terms, **tenant_terms}`.
           Tenant-specific rules naturally overwrite platform rules on exact match.
        """
        terms = await self.repo.get_active_terms(
            tenant_id=tenant_id,
            source_locale=source_locale,
            target_locale=target_locale,
        )

        platform_terms: dict[str, str] = {}
        tenant_terms: dict[str, str] = {}

        for term in terms:
            # Double-guard: ensure we don't process inactive records
            if not term.is_active:
                continue

            if term.tenant_id is None:
                platform_terms[term.source_term] = term.target_term
            elif tenant_id is not None and term.tenant_id == tenant_id:
                tenant_terms[term.source_term] = term.target_term

        # Merge ensures tenant overrides platform on key conflict
        resolved = {**platform_terms, **tenant_terms}
        return resolved
