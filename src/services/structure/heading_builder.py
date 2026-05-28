# src/services/structure/heading_builder.py

"""
Построение списка heading candidates из layout-элементов документа.
Публичный фасад.
"""

from __future__ import annotations
from typing import Any

from ._heading_builder._core import (
    build_heading_candidates, 
    filter_heading_sequence, 
    collect_scored_heading_candidates
)

__all__ = [
    "build_heading_candidates",
    "filter_heading_sequence",
    "collect_scored_heading_candidates",
]