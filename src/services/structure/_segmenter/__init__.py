# src/services/structure/_segmenter/__init__.py

"""
Внутренний пакет детерминированной сегментации документов.

Постепенно выносит сфокусированные ответственности из публичного
фасада ``services.structure.segmenter``, сохраняя стабильный внешний API.

Модули:
- config          — числовые пороги и лимиты
- types           — dataclass-модели boundary layer
- patterns        — regex-семейства и pattern-helpers
- element_utils   — safe-accessors и element-type предикаты
- heuristics      — текстовые / контекстные эвристики boundary-позиции
- confidence      — маппинг score → label
- artifacts       — детекция повторяющихся page-артефактов / running headers
- candidates      — сбор и валидация boundary-кандидатов
- assembly        — сборка сегментов, scope, metadata propagation
- purity          — post-segmentation purity recovery (P1)
- toc_suppression — подавление ложных appendix-границ на TOC / catalog pages (P5)
"""
