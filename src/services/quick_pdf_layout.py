# src/services/quick_pdf_layout.py

"""
Quick PDF Layout Service.
Used for lightweight PDF page layout visualization in the UI.
"""

from __future__ import annotations

from typing import Any
import pymupdf as fitz


def extract_quick_layout(pdf_bytes: bytes) -> dict[str, Any]:
    """Extract lightweight page layout elements for UI visualization."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    elements = []
    page_count = len(doc)

    for p_idx, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            elements.append({
                "element_id": f"atom:{p_idx:06d}",
                "page": p_idx + 1,
                "text": text.strip(),
                "type": "text",
            })
    doc.close()

    return {
        "page_count": page_count,
        "elements": elements,
    }
