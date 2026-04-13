# scripts/dump_clause_tree.py
# scripts/dump_clause_tree.py
# cd ~/projects/LegalMAS
# PYTHONPATH=./src python scripts/dump_clause_tree.py


import json

from core.config import settings
from storage.artifact_store import ArtifactStore

REF = "s3://mas-artifacts/tenants/2f7be05a-1e0d-49f2-accc-875639e29ad9/deals/2f7be05a-1e0d-49f2-accc-875639e29ad9/structures/2cd6747e-262c-44aa-8953-6f0101287e80/clause_tree.json"

def main():
    store = ArtifactStore(app_settings=settings)
    payload = store.get_json(REF)
    print(json.dumps(payload, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()


    