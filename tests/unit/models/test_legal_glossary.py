"""
Unit tests for LegalGlossary ORM model (Sprint 3.1).

Uses SQLAlchemy metadata inspection — no async_session fixture required
(project pattern 3.10).
"""

from __future__ import annotations

from db.models.legal_glossary import LegalGlossary


# ── Table structure ──────────────────────────────────────────────


class TestLegalGlossaryTableStructure:
    """Verify columns, types, and constraints via __table__ metadata."""

    def test_table_name(self) -> None:
        assert LegalGlossary.__tablename__ == "legal_glossaries"

    def test_has_all_expected_columns(self) -> None:
        """9 business columns + 3 inherited from Base = 12 total."""
        column_names = {c.name for c in LegalGlossary.__table__.columns}
        expected = {
            # From Base
            "id",
            "created_at",
            "updated_at",
            # Business columns
            "tenant_id",
            "source_locale",
            "target_locale",
            "source_term",
            "target_term",
            "term_category",
            "context_note",
            "is_active",
            "created_by",
        }
        assert expected.issubset(column_names), (
            f"Missing columns: {expected - column_names}"
        )

    def test_id_is_primary_key(self) -> None:
        assert LegalGlossary.__table__.columns["id"].primary_key is True

    # ── Nullability ──────────────────────────────────────────────

    def test_tenant_id_is_nullable(self) -> None:
        """Platform-wide glossary entries have tenant_id = NULL."""
        assert LegalGlossary.__table__.columns["tenant_id"].nullable is True

    def test_source_locale_not_nullable(self) -> None:
        assert LegalGlossary.__table__.columns["source_locale"].nullable is False

    def test_target_locale_not_nullable(self) -> None:
        assert LegalGlossary.__table__.columns["target_locale"].nullable is False

    def test_source_term_not_nullable(self) -> None:
        assert LegalGlossary.__table__.columns["source_term"].nullable is False

    def test_target_term_not_nullable(self) -> None:
        assert LegalGlossary.__table__.columns["target_term"].nullable is False

    def test_is_active_not_nullable(self) -> None:
        assert LegalGlossary.__table__.columns["is_active"].nullable is False

    def test_term_category_nullable(self) -> None:
        assert LegalGlossary.__table__.columns["term_category"].nullable is True

    def test_context_note_nullable(self) -> None:
        assert LegalGlossary.__table__.columns["context_note"].nullable is True

    def test_created_by_nullable(self) -> None:
        assert LegalGlossary.__table__.columns["created_by"].nullable is True

    # ── Foreign keys ─────────────────────────────────────────────

    def test_tenant_id_fk_targets_tenants(self) -> None:
        col = LegalGlossary.__table__.columns["tenant_id"]
        fk_targets = {str(fk.target_fullname) for fk in col.foreign_keys}
        assert "tenants.id" in fk_targets

    def test_tenant_id_fk_cascade_delete(self) -> None:
        """Tenant deletion cascades — tenant glossary must not leak to platform."""
        col = LegalGlossary.__table__.columns["tenant_id"]
        fk = next(iter(col.foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_created_by_fk_targets_users(self) -> None:
        col = LegalGlossary.__table__.columns["created_by"]
        fk_targets = {str(fk.target_fullname) for fk in col.foreign_keys}
        assert "users.id" in fk_targets

    def test_created_by_fk_set_null_on_delete(self) -> None:
        """Glossary survives user deletion — authorship is audit info only."""
        col = LegalGlossary.__table__.columns["created_by"]
        fk = next(iter(col.foreign_keys))
        assert fk.ondelete == "SET NULL"


# ── Indexes ──────────────────────────────────────────────────────


class TestLegalGlossaryIndexes:
    """Verify index definitions match project naming conventions."""

    def _get_index_by_name(self, name: str):
        for idx in LegalGlossary.__table__.indexes:
            if idx.name == name:
                return idx
        return None

    def test_locale_pair_index_exists(self) -> None:
        idx = self._get_index_by_name("idx_legal_glossary_locale_pair")
        assert idx is not None

    def test_locale_pair_index_columns(self) -> None:
        idx = self._get_index_by_name("idx_legal_glossary_locale_pair")
        assert [c.name for c in idx.columns] == ["source_locale", "target_locale"]
        assert idx.unique is False

    def test_partial_unique_index_exists(self) -> None:
        idx = self._get_index_by_name("uix_legal_glossary_active_term")
        assert idx is not None

    def test_partial_unique_index_columns(self) -> None:
        idx = self._get_index_by_name("uix_legal_glossary_active_term")
        assert [c.name for c in idx.columns] == [
            "tenant_id",
            "source_locale",
            "target_locale",
            "source_term",
        ]

    def test_partial_unique_index_is_unique(self) -> None:
        idx = self._get_index_by_name("uix_legal_glossary_active_term")
        assert idx.unique is True

    def test_partial_unique_index_has_where_clause(self) -> None:
        idx = self._get_index_by_name("uix_legal_glossary_active_term")
        # postgresql_where is stored as a TextClause
        assert idx.dialect_options.get("postgresql", {}).get("where") is not None


# ── Invariant checks ─────────────────────────────────────────────


class TestLegalGlossaryInvariants:
    """Ensure the model does not violate project invariants."""

    def test_invariant_6_no_per_locale_columns(self) -> None:
        """Invariant #6: no display_text_en, name_ru, etc."""
        column_names = {c.name for c in LegalGlossary.__table__.columns}
        violations = [
            n
            for n in column_names
            if any(
                n.endswith(f"_{loc}")
                for loc in ("en", "ru", "de", "fr", "es", "zh", "ja")
            )
        ]
        assert not violations, f"Invariant #6 violation: {violations}"

    def test_model_registered_in_init(self) -> None:
        """Model must be importable from src.db.models (pattern 3.9)."""
        from db.models import LegalGlossary as Imported

        assert Imported is LegalGlossary
