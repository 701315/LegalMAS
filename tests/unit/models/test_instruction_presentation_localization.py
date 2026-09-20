"""
Unit tests for InstructionPresentationLocalization ORM model (Sprint 4.1).

Uses SQLAlchemy metadata inspection — no active DB connection required,
strictly testing schema constraints, indexes, and column nullability.
"""

from __future__ import annotations

import uuid
from sqlalchemy import Index
from db.models.instruction_presentation_localization import InstructionPresentationLocalization

class TestInstructionLocalizationTableStructure:
    """Verify columns, types, and database constraints via metadata."""

    def test_table_name(self) -> None:
        assert (
            InstructionPresentationLocalization.__tablename__
            == "instruction_presentation_localizations"
        )

    def test_has_all_expected_columns(self) -> None:
        """6 business columns + 3 inherited from Base = 9 total."""
        column_names = {
            c.name for c in InstructionPresentationLocalization.__table__.columns
        }
        expected = {
            # Inherited from Base
            "id",
            "created_at",
            "updated_at",
            # Table Business columns
            "tenant_id",
            "instruction_key",
            "locale",
            "label",
            "description",
            "is_active",
            "created_by",
        }
        assert expected.issubset(column_names), (
            f"Missing fields in metadata: {expected - column_names}"
        )

    def test_id_is_primary_key(self) -> None:
        assert (
            InstructionPresentationLocalization.__table__.columns["id"].primary_key
            is True
        )

    # ── Nullability checks ───────────────────────────────────────

    def test_tenant_id_is_nullable(self) -> None:
        """Platform-wide translations have tenant_id = NULL."""
        assert (
            InstructionPresentationLocalization.__table__.columns["tenant_id"].nullable
            is True
        )

    def test_instruction_key_not_nullable(self) -> None:
        assert (
            InstructionPresentationLocalization.__table__.columns[
                "instruction_key"
            ].nullable
            is False
        )

    def test_locale_not_nullable(self) -> None:
        assert (
            InstructionPresentationLocalization.__table__.columns["locale"].nullable
            is False
        )

    def test_label_not_nullable(self) -> None:
        assert (
            InstructionPresentationLocalization.__table__.columns["label"].nullable
            is False
        )

    def test_description_is_nullable(self) -> None:
        assert (
            InstructionPresentationLocalization.__table__.columns["description"].nullable
            is True
        )

    def test_is_active_not_nullable(self) -> None:
        assert (
            InstructionPresentationLocalization.__table__.columns["is_active"].nullable
            is False
        )

    def test_created_by_is_nullable(self) -> None:
        assert (
            InstructionPresentationLocalization.__table__.columns["created_by"].nullable
            is True
        )

    # ── Column constraints & Types ───────────────────────────────

    def test_instruction_key_length_constraint(self) -> None:
        col = InstructionPresentationLocalization.__table__.columns["instruction_key"]
        assert col.type.length == 200

    def test_locale_length_constraint(self) -> None:
        col = InstructionPresentationLocalization.__table__.columns["locale"]
        assert col.type.length == 10

    def test_label_length_constraint(self) -> None:
        col = InstructionPresentationLocalization.__table__.columns["label"]
        assert col.type.length == 500

    # ── Foreign Key constraints ─────────────────────────────────

    def test_tenant_id_fk_target(self) -> None:
        fkeys = InstructionPresentationLocalization.__table__.foreign_keys
        tenant_fk = next(fk for fk in fkeys if fk.parent.name == "tenant_id")
        assert tenant_fk.target_fullname == "tenants.id"
        assert tenant_fk.ondelete == "CASCADE"

    def test_created_by_fk_target(self) -> None:
        fkeys = InstructionPresentationLocalization.__table__.foreign_keys
        user_fk = next(fk for fk in fkeys if fk.parent.name == "created_by")
        assert user_fk.target_fullname == "users.id"
        assert user_fk.ondelete == "SET NULL"

    # ── Index naming & configurations ───────────────────────────

    def test_has_expected_indexes(self) -> None:
        """Verifies indexes are present with the exact specified naming schema."""
        table_indexes = {
            idx.name: idx for idx in InstructionPresentationLocalization.__table__.indexes
        }

        # Index 1: Lookup
        assert "idx_instruction_localization_lookup" in table_indexes
        lookup_idx = table_indexes["idx_instruction_localization_lookup"]
        assert [c.name for c in lookup_idx.expressions] == ["instruction_key", "locale"]
        assert lookup_idx.unique is False

        # Index 2: Partial Unique
        assert "uix_instruction_localization_unique_active" in table_indexes
        unique_idx = table_indexes["uix_instruction_localization_unique_active"]
        assert [c.name for c in unique_idx.expressions] == [
            "tenant_id",
            "instruction_key",
            "locale",
        ]
        assert unique_idx.unique is True
        assert "is_active = true" in str(unique_idx.dialect_options["postgresql"]["where"])


        