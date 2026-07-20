# src/services/playbooks/publishing.py

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import PlaybookStatus
from db.models.playbook import PlaybookVersion
from db.repositories.playbook_repo import compute_source_payload_hash


class PlaybookPublishingError(Exception):
    pass


class PublishedVersionImmutableError(PlaybookPublishingError):
    code = "PUBLISHED_VERSION_IMMUTABLE"


class PlaybookPublishingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def validate(self, version: PlaybookVersion) -> dict:
        """
        Structural validation for playbook version.
        """
        errors = []
        warnings = []

        if not version.source_payload:
            errors.append("source_payload is missing")

        if not version.compiled_checks:
            errors.append("compiled_checks is missing")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    async def publish(self, version: PlaybookVersion) -> PlaybookVersion:
        if version.status == PlaybookStatus.PUBLISHED.value:
            raise PublishedVersionImmutableError(
                "Version already published"
            )

        report = await self.validate(version)
        if not report["valid"]:
            raise PlaybookPublishingError(
                f"Validation failed: {report['errors']}"
            )

        immutable_hash = self._compute_compiled_hash(
            version.compiled_checks
        )

        version.status = PlaybookStatus.PUBLISHED.value
        version.immutable_content_hash = immutable_hash
        version.validation_report = report
        version.published_at = datetime.now(timezone.utc)

        await self.session.flush()
        return version

    async def archive(self, version: PlaybookVersion) -> PlaybookVersion:
        if version.status != PlaybookStatus.PUBLISHED.value:
            raise PlaybookPublishingError(
                "Only published versions can be archived"
            )

        version.status = PlaybookStatus.ARCHIVED.value
        await self.session.flush()
        return version

    async def clone_to_draft(
        self,
        source_version: PlaybookVersion,
    ) -> PlaybookVersion:

        new_version = PlaybookVersion(
            playbook_id=source_version.playbook_id,
            name=f"{source_version.name} (draft)",
            semver=source_version.semver,
            model_config_id=source_version.model_config_id,
            compiled_checks=source_version.compiled_checks,
            source_payload=source_version.source_payload,
            source_payload_sha256=source_version.source_payload_sha256,
            status=PlaybookStatus.DRAFT.value,
            parent_version_id=source_version.id,
        )

        self.session.add(new_version)
        await self.session.flush()
        return new_version

    def _compute_compiled_hash(self, compiled: dict) -> str:
        canonical = json.dumps(
            compiled,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
    

    