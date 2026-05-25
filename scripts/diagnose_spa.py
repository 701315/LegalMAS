import json
import urllib.request
import os

# ===== НАСТРОЙКИ MinIO =====
# Замените на реальные данные (узнайте у администратора/в .env файле)
MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin123"
MINIO_BUCKET = "mas-artifacts"

def get_json_from_minio(key):
    """Скачивает JSON из MinIO через S3 API"""
    import boto3
    from botocore.client import Config
    
    s3 = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )
    
    response = s3.get_object(Bucket=MINIO_BUCKET, Key=key)
    return json.loads(response['Body'].read().decode('utf-8'))

def get_json_from_file(path):
    """Читает локальный JSON"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_tree(data):
    print("=" * 70)
    print("SEGMENT CLAUSE TREE АНАЛИЗ")
    print("=" * 70)
    
    print(f"\nschema_version: {data.get('schema_version')}")
    print(f"document_id: {data.get('document_id')}")
    print(f"structure_confidence: {data.get('structure_confidence')}")
    print(f"degraded: {data.get('degraded')}")
    
    root = data.get("root", [])
    print(f"\nRoot nodes: {len(root)}")
    
    has_nested = any(node.get("children") for node in root)
    print(f"Есть вложенность: {has_nested}")
    
    # Подсчет
    total_leafs = 0
    problem_nodes = []
    
    def analyze_node(node, depth=0):
        nonlocal total_leafs
        uid = node.get("clause_uid", "N/A")
        title = node.get("title") or "NULL"
        level = node.get("level", "N/A")
        children = node.get("children", [])
        eids = node.get("own_element_ids", []) or node.get("element_ids", [])
        
        indent = "  " * depth
        children_str = f", children={len(children)}" if children else ""
        
        if not children:
            total_leafs += 1
            marker = ""
            if len(eids) > 10:
                marker = " ⚠️ МНОГО element_ids!"
                problem_nodes.append((uid, title, len(eids)))
            print(f"{indent}- [{uid}] {title[:50]} (level={level}, eids={len(eids)}){marker}")
        else:
            print(f"{indent}- [{uid}] {title[:50]} (level={level}{children_str})")
            for child in children[:20]:  # ограничим вывод
                analyze_node(child, depth + 1)
            if len(children) > 20:
                print(f"{indent}  ... и ещё {len(children)-20} children")
    
    print(f"\n{'='*70}")
    print("ДЕРЕВО:")
    print(f"{'='*70}")
    
    for node in root[:20]:
        analyze_node(node)
    
    if len(root) > 20:
        print(f"\n... и ещё {len(root)-20} root-узлов")
    
    print(f"\n{'='*70}")
    print(f"ИТОГО leaf-узлов: {total_leafs}")
    print(f"{'='*70}")
    
    if problem_nodes:
        print(f"\n❌ ПРОБЛЕМНЫЕ УЗЛЫ (leaf с >10 element_ids):")
        for uid, title, count in problem_nodes:
            print(f"   uid={uid}, title={title[:50]}, element_ids={count}")

def analyze_chunks(data):
    print(f"\n{'='*70}")
    print("SEGMENT CHUNKS АНАЛИЗ")
    print(f"{'='*70}")
    
    print(f"\nschema_version: {data.get('schema_version')}")
    print(f"scope: {data.get('scope')}")
    print(f"degraded: {data.get('degraded')}")
    
    coverage = data.get("coverage", {})
    print(f"\nCoverage:")
    for k, v in coverage.items():
        print(f"  {k}: {v}")
    
    chunks_data = data.get("chunks", {})
    for level in ["section", "clause", "subclause"]:
        items = chunks_data.get(level, [])
        print(f"\n📊 {level.upper()}: {len(items)} чанков")
        for i, ch in enumerate(items[:3]):
            text = ch.get("text", "")[:100].replace("\n", " ")
            meta = ch.get("metadata", {})
            print(f"  [{i}] id={ch.get('id')}, clause_uid={meta.get('clause_uid')}, "
                  f"tokens={meta.get('token_count')}")
            print(f"      text: {text}...")

def main():
    # Пути к файлам в MinIO (без s3:// и bucket)
    tree_key = "tenants/732e8f91-3548-4385-a685-583827476e83/deals/732e8f91-3548-4385-a685-583827476e83/structures/f6a91df8-b5e7-4696-bfbe-b4293dc350fa/segment_c902e8a8.json"
    chunks_key = "tenants/00000000-0000-0000-0000-000000000000/deals/732e8f91-3548-4385-a685-583827476e83/structures/f6a91df8-b5e7-4696-bfbe-b4293dc350fa/chunks_c902e8a8.json"
    
    # Попробуем сначала локальные файлы (если уже скачаны через mc)
    if os.path.exists("segment_clause_tree.json"):
        print("📁 Читаем локальный segment_clause_tree.json")
        tree = get_json_from_file("segment_clause_tree.json")
    else:
        print("☁️  Скачиваем из MinIO...")
        tree = get_json_from_minio(tree_key)
        with open("segment_clause_tree.json", "w", encoding="utf-8") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        print("✅ Сохранено: segment_clause_tree.json")
    
    analyze_tree(tree)
    
    if os.path.exists("segment_chunks.json"):
        print("\n📁 Читаем локальный segment_chunks.json")
        chunks = get_json_from_file("segment_chunks.json")
    else:
        print("\n☁️  Скачиваем chunks из MinIO...")
        chunks = get_json_from_minio(chunks_key)
        with open("segment_chunks.json", "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        print("✅ Сохранено: segment_chunks.json")
    
    analyze_chunks(chunks)

if __name__ == "__main__":
    main()

