"""normalize source in playbook_versions.compiled_checks

Revision ID: 9b4e4d1eae41
Revises: e65bbfe5dbff
Create Date: 2026-03-19 12:25:40.978373

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
import json


# revision identifiers, used by Alembic.
revision: str = '9b4e4d1eae41'
down_revision: Union[str, None] = 'e65bbfe5dbff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_source_value(value: str | None) -> str | None:
    """
    Привести старые значения source к новому контракту.

    Возвращает:
    - "GLOBAL_PLAYBOOK" / "DOCUMENT_TYPE" / "SYSTEM" для известных значений;
    - None, если значение не распознано (в этом случае не меняем его).
    """
    if value is None:
        # Пустое значение считаем глобальным плейбуком.
        return "GLOBAL_PLAYBOOK"

    v = str(value).strip()
    if not v:
        return "GLOBAL_PLAYBOOK"

    upper = v.upper()

    # Нормальные целевые значения — оставляем как есть.
    if upper in ("GLOBAL_PLAYBOOK", "DOCUMENT_TYPE", "SYSTEM"):
        return upper

    # Исторические варианты для глобального плейбука.
    if upper in ("GLOBAL", "GLOBAL_PLAYBOOKS", "GLOBAL_PLAYBOOK_V1", "GLOBAL_PLAYBOOK_V2"):
        return "GLOBAL_PLAYBOOK"

    # Исторические варианты для плейбуков по типу документа.
    if upper in ("DOCUMENT_TYPE_PLAYBOOK", "TYPE_PLAYBOOK", "DOC_TYPE_PLAYBOOK"):
        return "DOCUMENT_TYPE"

    # Исторические варианты для системных чеков.
    if upper in ("SYS", "SYSTEM_CHECK", "TECH", "TECHNICAL"):
        return "SYSTEM"

    # Неизвестное значение — не трогаем, пусть всплывёт отдельно.
    return None


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    playbook_versions = sa.table(
        "playbook_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("compiled_checks", postgresql.JSONB),
    )

    # Берём все версии, где compiled_checks не NULL.
    rows = session.execute(sa.select(playbook_versions.c.id,
                                     playbook_versions.c.compiled_checks)
                           .where(playbook_versions.c.compiled_checks.is_not(None))).all()

    updated = 0

    for row in rows:
        version_id = row.id
        compiled = row.compiled_checks

        if not isinstance(compiled, dict):
            continue

        checks = compiled.get("checks")
        if not isinstance(checks, list):
            continue

        changed = False
        for item in checks:
            if not isinstance(item, dict):
                continue
            old_source = item.get("source")
            new_source = _normalize_source_value(old_source)
            if new_source is None:
                # Нераспознанные значения оставляем как есть.
                continue
            if old_source != new_source:
                item["source"] = new_source
                changed = True

        if changed:
            updated += 1
            session.execute(
                sa.update(playbook_versions)
                .where(playbook_versions.c.id == version_id)
                .values(compiled_checks=compiled)
            )

    session.commit()

    print(f"normalize_playbook_compiled_checks_source: updated {updated} playbook_versions")


def downgrade() -> None:
    # Обратная миграция данных не нужна и не реализуется:
    # мы только нормализуем значения к контракту.
    pass
