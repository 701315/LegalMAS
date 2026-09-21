from __future__ import annotations

from db.models.check_result_anchor import CheckResultAnchor
from db.models.result import CheckResult


def test_table_name() -> None:
    assert CheckResultAnchor.__tablename__ == "check_result_anchors"


def test_columns_present() -> None:
    cols = {c.name for c in CheckResultAnchor.__table__.columns}
    expected = {
        "id", "created_at", "updated_at", "check_result_id",
        "clause_uid", "clause_ref", "quoted_text",
        "span_start", "span_end", "source_content_hash",
        "page", "layout_element_ids", "bbox_union", "segment_id",
        "anchor_method", "anchor_confidence",
        "anchor_validation_passed", "anchor_diagnostics", "is_primary",
    }
    assert expected.issubset(cols)


def test_fk_cascades_from_check_results() -> None:
    fks = list(CheckResultAnchor.__table__.foreign_keys)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.column.table.name == "check_results"
    assert fk.ondelete == "CASCADE"


def test_primary_flag_not_nullable() -> None:
    col = CheckResultAnchor.__table__.c.is_primary
    assert col.nullable is False


def test_unique_partial_index_declared() -> None:
    names = {idx.name for idx in CheckResultAnchor.__table__.indexes}
    assert "uq_cra_one_primary" in names


def test_check_result_has_primary_anchor_columns() -> None:
    cols = {c.name for c in CheckResult.__table__.columns}
    assert {"primary_anchor_id", "primary_anchor_method",
            "primary_anchor_confidence", "anchor_stale"}.issubset(cols)

            