"""Read-only audit: layout → parse_raw_heading → normalized uid → level.

Показывает по каждому потенциально heading-подобному элементу sanitized layout:
- elem_i, element_id, scope, type, element_type
- text (первые 160 символов)
- parse_raw_heading(text) → (raw_uid, title) | None
- normalized_uid
- strict_numeric?
- level_from_uid (если применимо)
- preamble zone

Не изменяет никаких артефактов. Не участвует в pipeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# --- настройте путь к локально скачанному sanitized layout JSON ---
LAYOUT_JSON_PATH = Path(sys.argv[1])

# импорт из проекта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from services.structure.heading_patterns import parse_raw_heading  # noqa: E402
from services.structure._hierarchy_builder._utils import (  # noqa: E402
    _is_strict_numeric_uid,
    _normalize_uid,
    level_from_uid,
)


def _load_layout(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ("elements", "layout_elements", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
    if isinstance(data, list):
        return data
    raise SystemExit(f"Cannot locate elements list in {path}")


def _short(text: str, n: int = 160) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def main() -> None:
    elements = _load_layout(LAYOUT_JSON_PATH)
    print(f"loaded elements: {len(elements)}")
    print(
        f"{'i':>5}  {'scope':<16}  {'type':<20}  {'element_type':<24}  "
        f"{'zone':<10}  {'raw_uid':<10}  {'strict':<6}  {'level':<5}  text"
    )
    print("-" * 200)

    for i, el in enumerate(elements):
        text = str(el.get("text") or "").strip()
        if not text:
            continue

        # heuristика: показываем только строки, которые ХОТЬ КАК-ТО похожи на heading
        # (начинаются с цифры/буквы + пробел/точка/скобка, ИЛИ уже размечены как heading-ish)
        raw_type = str(el.get("type") or "").lower()
        el_type = str(el.get("element_type") or "").lower()
        heading_ish = (
            raw_type == "heading"
            or "heading" in el_type
            or (len(text) < 300 and text[0:1].isdigit())
        )
        if not heading_ish:
            continue

        parsed = parse_raw_heading(text)
        if parsed is None:
            raw_uid_disp = "-"
            strict = "-"
            level_disp = "-"
        else:
            raw_uid_raw, _title = parsed
            norm = _normalize_uid(raw_uid_raw)
            raw_uid_disp = norm
            is_strict = _is_strict_numeric_uid(norm)
            strict = "yes" if is_strict else "no"
            level_disp = str(level_from_uid(norm)) if is_strict else "-"

        scope = str(el.get("scope") or (el.get("metadata") or {}).get("scope") or "")
        zone = str(el.get("_preamble_zone") or "")

        print(
            f"{i:>5}  {scope:<16}  {raw_type:<20}  {el_type:<24}  "
            f"{zone:<10}  {raw_uid_disp:<10}  {strict:<6}  {level_disp:<5}  {_short(text)}"
        )


if __name__ == "__main__":
    main()


    