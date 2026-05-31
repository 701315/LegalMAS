"""
Phase 12.1.7 — Offline Benchmark package.

Содержит:
- fixtures/clauses_gold.json  — curated evaluation set с gold labels
- test_phase12_1_7_benchmark.py — pytest тесты (mock) + standalone runner

Запуск unit части (mock LLM, без живого LLM):
    pytest tests/benchmark/test_phase12_1_7_benchmark.py -m "not llm_integration"

Запуск полного benchmark с живым LLM:
    pytest tests/benchmark/test_phase12_1_7_benchmark.py -m llm_integration -v
"""

