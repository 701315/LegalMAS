#!/usr/bin/env python3
"""READ-ONLY. Профили: живые / частичные / мёртвые."""
import sys
sys.path.insert(0, "src")

from services.structure.topic_tagger import KNOWN_TOPICS
from engine.playbook.retrieval_profiles import ALL_PROFILES

profiles = ALL_PROFILES  # dict[str, RetrievalProfile]

works: list[str] = []
partial: list[tuple[str, list[str], list[str]]] = []
dead: list[tuple[str, list[str]]] = []

for pid, p in sorted(profiles.items()):
    all_topics = list(p.required_topics or []) + list(p.supporting_topics or [])
    if not all_topics:
        works.append(pid)  # пустой список → не использует boost, формально работает как fallback
        continue
    dead_topics = [t for t in all_topics if t not in KNOWN_TOPICS]
    live_topics = [t for t in all_topics if t in KNOWN_TOPICS]
    if not dead_topics:
        works.append(pid)
    elif live_topics:
        partial.append((pid, live_topics, dead_topics))
    else:
        dead.append((pid, dead_topics))

print(f"\n{'='*100}")
print(f"🟢 ПОЛНОСТЬЮ ЖИВЫЕ ({len(works)}) — все topics в KNOWN_TOPICS")
print(f"{'='*100}")
for pid in works:
    print(f"  ✅ {pid}")

print(f"\n{'='*100}")
print(f"🟡 ЧАСТИЧНО МЁРТВЫЕ ({len(partial)}) — есть и живые, и мёртвые topics")
print(f"{'='*100}")
for pid, live, dead_t in partial:
    print(f"\n  ⚠️  {pid}")
    print(f"       живые: {live}")
    print(f"       мёртвые: {dead_t}")

print(f"\n{'='*100}")
print(f"🔴 ПОЛНОСТЬЮ МЁРТВЫЕ ({len(dead)}) — все topics вне KNOWN_TOPICS")
print(f"{'='*100}")
for pid, dead_t in dead:
    print(f"\n  ❌ {pid}")
    print(f"       все topics мёртвые: {dead_t}")

print(f"\n{'='*100}")
print(f"ИТОГ: живых {len(works)}, частичных {len(partial)}, мёртвых {len(dead)} из {len(profiles)}")

