import json
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]

# Поставь актуальные пути:
CLAUSE_TREE_PATH = ROOT / "clause_tree.json"
# Если хочешь сразу смотреть и layout — укажи файл:
LAYOUT_PATH: Optional[Path] = None  # например: ROOT / "layout_primary.json"


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def flatten_clauses(nodes: List[Dict[str, Any]], parent_uid: str = "") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for node in nodes:
        uid = node.get("clause_uid")
        title = node.get("title")
        level = node.get("level")
        start_page = node.get("start_page")
        end_page = node.get("end_page")
        element_ids = node.get("element_ids", []) or []
        children = node.get("children", []) or []

        out.append(
            {
                "clause_uid": uid,
                "parent_uid": parent_uid or None,
                "level": level,
                "title": title,
                "start_page": start_page,
                "end_page": end_page,
                "element_ids": element_ids,
            }
        )

        out.extend(flatten_clauses(children, parent_uid=uid))

    return out


def build_element_index(layout: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    layout['elements'] ожидается в формате, который тебе уже приходил из extract_worker:
    [{ "elementid": "e123", "text": "...", "page": 1, ... }, ...]
    """
    index: Dict[str, Dict[str, Any]] = {}
    elements = layout.get("elements") or []
    for el in elements:
        el_id = el.get("elementid") or el.get("element_id")
        if not el_id:
            continue
        index[str(el_id)] = el
    return index


def text_for_element(el: Dict[str, Any]) -> str:
    t = el.get("text") or ""
    t = str(t).replace("\n", " ").strip()
    if len(t) > 120:
        t = t[:117] + "..."
    return t


def main() -> None:
    if not CLAUSE_TREE_PATH.exists():
        raise SystemExit(f"clause_tree not found at {CLAUSE_TREE_PATH}")

    tree = load_json(CLAUSE_TREE_PATH)
    root_nodes = tree.get("root") or []
    flat = flatten_clauses(root_nodes)

    layout_index: Dict[str, Dict[str, Any]] = {}
    if LAYOUT_PATH is not None:
        if not LAYOUT_PATH.exists():
            raise SystemExit(f"layout not found at {LAYOUT_PATH}")
        layout = load_json(LAYOUT_PATH)
        layout_index = build_element_index(layout)

    # 1. Общая сводка по дереву
    print("=== CLAUSE TREE OVERVIEW ===")
    print(f"document_id: {tree.get('document_id')}")
    print(f"structure_confidence: {tree.get('structure_confidence')}")
    print(f"degraded: {tree.get('degraded')}")
    print(f"total nodes: {len(flat)}")
    print()

    # 2. Все корневые (level=1) с детьми
    print("=== TOP-LEVEL CLAUSES (level=1) ===")
    by_uid = {c["clause_uid"]: c for c in flat}
    for node in flat:
        if node["level"] != 1:
            continue
        uid = node["clause_uid"]
        children = [c for c in flat if c["parent_uid"] == uid]
        print(f"{uid}: {node['title']}")
        print(f"  pages: {node['start_page']}-{node['end_page']}, children: {len(children)}")
        print(f"  element_ids: {len(node['element_ids'])}")
        print()

    # 3. Конкретно интересующие узлы
    focus_uids = ["2", "2.2", "3.1", "3.2"]
    print("=== FOCUS CLAUSES ===")
    for uid in focus_uids:
        node = by_uid.get(uid)
        if not node:
            print(f"{uid}: NOT FOUND")
            continue
        print(f"{uid}: {node['title']}")
        print(f"  level: {node['level']}, pages: {node['start_page']}-{node['end_page']}")
        print(f"  element_ids ({len(node['element_ids'])}): {node['element_ids']}")
        print()
        if layout_index:
            print("  Elements text:")
            for el_id in node["element_ids"]:
                el = layout_index.get(el_id)
                if not el:
                    print(f"    {el_id}: <missing in layout>")
                    continue
                print(
                    f"    {el_id} [page {el.get('page')}]: "
                    f"{text_for_element(el)}"
                )
            print()

    # 4. Быстрый sanity-check по coverage: сколько уникальных element_ids участвует
    all_ids = set()
    for n in flat:
        all_ids.update(n["element_ids"])
    print("=== COVERAGE ===")
    print(f"unique element_ids in clause_tree: {len(all_ids)}")
    if layout_index:
        covered = len([eid for eid in all_ids if eid in layout_index])
        print(f"present in layout: {covered}, missing: {len(all_ids) - covered}")
    print()


if __name__ == "__main__":
    main()

    