"""
B5 — DTO anchor fields (CellValueDTO / DrawerFieldDTO).
"""

from __future__ import annotations

from services.dd_grid_v1_builder import CellValueDTO, DrawerFieldDTO


def test_cell_value_dto_accepts_anchor_fields():
    cell = CellValueDTO(
        cell_state="defined",
        display_value="РФ",
        anchor_method="exact_span",
        anchor_confidence=1.0,
        anchor_stale=False,
        layout_element_ids=["ru:node:5:0001"],
    )
    assert cell.anchor_method == "exact_span"
    assert cell.anchor_confidence == 1.0
    assert cell.anchor_stale is False
    assert cell.layout_element_ids == ["ru:node:5:0001"]


def test_cell_value_dto_anchor_defaults_none():
    """Backward-compat: без явного populate поля = None/False/[]."""
    cell = CellValueDTO(cell_state="defined", display_value="—")
    assert cell.anchor_method is None
    assert cell.anchor_confidence is None
    assert cell.anchor_stale is False
    assert cell.layout_element_ids == []


def test_drawer_field_dto_accepts_anchor_fields():
    f = DrawerFieldDTO(
        column_id="c1",
        field_name="governing_law_value",
        label="Право",
        cell_state="defined",
        display_value="РФ",
        anchor_method="fuzzy_span",
        anchor_confidence=0.85,
        anchor_stale=True,
    )
    assert f.anchor_method == "fuzzy_span"
    assert f.anchor_confidence == 0.85
    assert f.anchor_stale is True


def test_drawer_field_dto_layout_element_ids_isolated():
    """field(default_factory=list) — два экземпляра не делят один список."""
    f1 = DrawerFieldDTO(
        column_id="c1", field_name="x", label="X", cell_state="defined", display_value="—",
    )
    f2 = DrawerFieldDTO(
        column_id="c2", field_name="y", label="Y", cell_state="defined", display_value="—",
    )
    f1.layout_element_ids.append("a")
    assert f2.layout_element_ids == []
