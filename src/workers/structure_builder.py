"""
Structure Builder — simplified version for vertical slice.

Builds clause tree from numbered headings (regex-based).
Populates element.clause_uid in textlayoutraw artifact.

NOTE: Output format is compatible with production ClauseTree
from src/services/structure_models.py (Stage 6).

clause_tree_ref is stored on DocumentVersion and is read by:
  - Classifier Worker (this stage): NOT used in L1
  - Runner (Stage 8): used to cite evidence by clause_uid
  - Structure Builder production (Stage 6): replaces this implementation
"""

import re
import uuid

from src.core.constants import DocumentStatus
from src.core.logging import get_logger
from src.queue.async_helpers import get_worker_session, run_async
from src.queue.base_task import MASBaseTask
from src.queue.celery_app import celery_app
from src.storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)

CLAUSE_PATTERNS = [
    (re.compile(r"^(\d{1,2})\.\s+(.+)"), 1),
    (re.compile(r"^(\d{1,2}\.\d{1,2})\.?\s+(.+)"), 2),
    (re.compile(r"^(\d{1,2}\.\d{1,2}\.\d{1,2})\.?\s+(.+)"), 3),
]


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_structure",
    track_job=False,
    queue="default",
)
def build_structure(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str = None,
) -> dict:
    logger.info("Starting structure building", document_id=document_id)
    store = ArtifactStore()
    raw_path = ArtifactPath.layout_raw(tenant_id, deal_id, document_id)
    text_layout_raw = store.get_json(raw_path)
    elements = text_layout_raw["elements"]

    root_children = []
    current_stack = []

    # Build clause tree and populate clause_uid on elements
    element_clause_map = {}  # element_id → clause_uid

    for element in elements:
        text = element.get("text", "").strip()
        elem_id = element.get("element_id")
        if not text:
            continue

        matched = False
        for pattern, level in CLAUSE_PATTERNS:
            m = pattern.match(text)
            if m:
                clause_uid = m.group(1)
                title = m.group(2).strip() if m.group(2) else text
                node = {
                    "clause_uid": clause_uid,
                    "title": title[:200],
                    "full_text": text,
                    "level": level,
                    "element_ids": [elem_id],
                    "start_page": element.get("page", 1),
                    "end_page": element.get("page", 1),
                    "children": [],
                }
                _insert_into_tree(root_children, current_stack, node, level)
                element_clause_map[elem_id] = clause_uid
                matched = True
                break

        if not matched and current_stack:
            current_node = current_stack[-1][1]
            current_node["element_ids"].append(elem_id)
            current_node["end_page"] = max(current_node["end_page"], element.get("page", 1))
            current_node["full_text"] += " " + text
            element_clause_map[elem_id] = current_node["clause_uid"]

    # Write clause_uid back into elements
    updated_elements = []
    for element in elements:
        eid = element.get("element_id")
        clause_uid = element_clause_map.get(eid)
        updated_elements.append({**element, "clause_uid": clause_uid})

    # Update textlayoutraw with populated clause_uid
    updated_layout = {**text_layout_raw, "elements": updated_elements}
    store.put_json(raw_path, updated_layout)

    total_elements = len(elements)
    covered_elements = len(element_clause_map)
    coverage = covered_elements / total_elements if total_elements else 0.0
    confidence = "HIGH" if coverage >= 0.8 else "MEDIUM" if coverage >= 0.6 else "LOW"

    clause_tree = {
        "document_version_id": document_version_id,
        "root": {"children": root_children},
        "references_index": {},
        "quality": {
            "coverage": round(coverage, 3),
            "confidence": confidence,
            "total_elements": total_elements,
            "covered_elements": covered_elements,
            "is_degraded": confidence == "LOW",
        },
    }

    tree_path = ArtifactPath.clause_tree(tenant_id, deal_id, document_id)
    tree_ref = store.put_json(tree_path, clause_tree)

    run_async(_update_structure_result(document_version_id, document_id, tree_ref))

    total_clauses = _count_clauses(root_children)
    logger.info(
        "Structure building complete",
        document_id=document_id,
        clauses=total_clauses,
        coverage=coverage,
        confidence=confidence,
    )

    from src.workers.classifier import classify_document_task

    classify_document_task.delay(
        document_id=document_id,
        document_version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    return {
        "document_id": document_id,
        "clauses": total_clauses,
        "coverage": coverage,
        "confidence": confidence,
    }


def _insert_into_tree(root_children, stack, node, level):
    while stack and stack[-1][0] >= level:
        stack.pop()
    if stack:
        stack[-1][1]["children"].append(node)
    else:
        root_children.append(node)
    stack.append((level, node))


def _count_clauses(nodes):
    count = len(nodes)
    for node in nodes:
        count += _count_clauses(node.get("children", []))
    return count


async def _update_structure_result(
    document_version_id: str, document_id: str, tree_ref: str
) -> None:
    from src.db.repositories import DocumentRepository, DocumentVersionRepository

    async with get_worker_session() as session:
        ver_repo = DocumentVersionRepository(session)
        doc_repo = DocumentRepository(session)
        await ver_repo.update_refs(uuid.UUID(document_version_id), clause_tree_ref=tree_ref)
        await doc_repo.update_status(uuid.UUID(document_id), DocumentStatus.STRUCTURED.value)
