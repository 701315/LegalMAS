"""
Canonical Anchor Contract for DD check results.

Публичный контракт между detector (B3), persistence (B4), API (B5).
См. docs/PLAN_DETECTION_AND_ANCHORS.md, раздел 2.1.
"""

from core.anchors.models import CheckAnchor, CheckAnchorMethod
from core.anchors.selection import method_strength, select_primary_anchor

__all__ = [
    "CheckAnchor",
    "CheckAnchorMethod",
    "method_strength",
    "select_primary_anchor",
]

