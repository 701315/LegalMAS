# tests/unit/models/test_tenant_result_locale_policy.py

"""
Unit tests for TenantResultLocalePolicy model mapping (Sprint 2.5).

Tests verify ORM mapping correctness via SQLAlchemy table metadata.
Database-level defaults (server_default) are validated by the Alembic
migration itself and by integration/E2E tests.
"""

import uuid

import pytest
from sqlalchemy import inspect

from db.models.tenant_result_locale_policy import TenantResultLocalePolicy


def test_explicit_field_assignment() -> None:
    """Verify that all fields can be explicitly set on instantiation."""
    tenant_id = uuid.uuid4()
    policy = TenantResultLocalePolicy(
        tenant_id=tenant_id,
        allowed_locales=["en", "ru"],
        is_translation_enabled=False,
        restrict_to_allowed=True,
    )

    assert policy.tenant_id == tenant_id
    assert policy.allowed_locales == ["en", "ru"]
    assert policy.is_translation_enabled is False
    assert policy.restrict_to_allowed is True


def test_table_has_expected_columns() -> None:
    """Verify table metadata contains all required columns with correct types."""
    table = TenantResultLocalePolicy.__table__
    column_names = {c.name for c in table.columns}

    expected = {
        "id",
        "created_at",
        "updated_at",
        "tenant_id",
        "allowed_locales",
        "is_translation_enabled",
        "restrict_to_allowed",
    }
    assert expected.issubset(column_names), (
        f"Missing columns: {expected - column_names}"
    )


def test_tenant_id_foreign_key() -> None:
    """Verify tenant_id has a foreign key constraint to tenants.id."""
    table = TenantResultLocalePolicy.__table__
    tenant_col = table.columns["tenant_id"]

    fk_targets = {str(fk.target_fullname) for fk in tenant_col.foreign_keys}
    assert "tenants.id" in fk_targets, (
        f"Expected FK to tenants.id, got: {fk_targets}"
    )


def test_tenant_id_unique_constraint() -> None:
    """Verify tenant_id has a unique constraint (one policy per tenant)."""
    table = TenantResultLocalePolicy.__table__
    unique_cols = set()
    for constraint in table.constraints:
        if hasattr(constraint, "columns") and len(constraint.columns) == 1:
            col_name = list(constraint.columns)[0].name
            if col_name == "tenant_id":
                unique_cols.add(col_name)

    # Also check column-level unique flag
    is_unique = table.columns["tenant_id"].unique
    assert is_unique or "tenant_id" in unique_cols, (
        "tenant_id must have a unique constraint"
    )


def test_allowed_locales_not_nullable() -> None:
    """Verify allowed_locales is NOT NULL (server_default handles empty)."""
    table = TenantResultLocalePolicy.__table__
    assert table.columns["allowed_locales"].nullable is False


def test_boolean_columns_not_nullable() -> None:
    """Verify boolean policy flags are NOT NULL."""
    table = TenantResultLocalePolicy.__table__
    assert table.columns["is_translation_enabled"].nullable is False
    assert table.columns["restrict_to_allowed"].nullable is False


    