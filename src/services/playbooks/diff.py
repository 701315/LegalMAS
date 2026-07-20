# src/services/playbooks/diff.py

from typing import Any

from db.models.playbook import PlaybookVersion


class PlaybookDiffError(Exception):
    pass


class PlaybookVersionDiffService:
    """
    Diff двух PlaybookVersion по source_payload.
    """

    def diff(
        self,
        base: PlaybookVersion,
        other: PlaybookVersion,
    ) -> list[dict[str, Any]]:

        if not base.source_payload or not other.source_payload:
            raise PlaybookDiffError(
                "Cannot diff legacy versions without source_payload"
            )

        base_source = base.source_payload
        other_source = other.source_payload

        fields = set(base_source.keys()) | set(other_source.keys())

        changes: list[dict[str, Any]] = []

        for field in sorted(fields):
            old_value = base_source.get(field)
            new_value = other_source.get(field)

            if old_value != new_value:
                changes.append(
                    {
                        "field": field,
                        "old": old_value,
                        "new": new_value,
                    }
                )

        return changes



