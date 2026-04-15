import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from services.structure.pipeline import build_structure


def main() -> None:
    document_id = "29ec9981-add5-46fe-aefb-2d3460d84639"

    layout_path = Path("layout_29ec.json")
    data = json.loads(layout_path.read_text(encoding="utf-8"))
    elements = data.get("elements")
    if not isinstance(elements, list):
        raise RuntimeError(f"Unexpected layout format, elements={type(elements)}")

    clausetree = build_structure(document_id=document_id, elements=elements)

    as_dict = clausetree.to_dict()

    # пишем сразу в файл, минуя stdout с логами
    out_path = Path("clausetree_local_29ec.json")
    out_path.write_text(json.dumps(as_dict, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
