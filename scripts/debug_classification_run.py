# scripts/debug_classification_run.py
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Any

# Важно: никаких basicConfig в библиотечном коде.
# Настройка логирования только в entrypoint-скрипте.
# Если у вас уже есть project-level init logging, лучше вызвать его вместо basicConfig.


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # Точечно усиливаем нужные логгеры
    logging.getLogger("src.classifiers.stage8._content_fetcher").setLevel(logging.DEBUG)
    logging.getLogger("src.classifiers.stage8.hybrid_classifier").setLevel(logging.DEBUG)

    # Если у вас logger names без src., оставь и второй вариант:
    logging.getLogger("classifiers.stage8._content_fetcher").setLevel(logging.DEBUG)
    logging.getLogger("classifiers.stage8.hybrid_classifier").setLevel(logging.DEBUG)

    # По желанию — asyncio debug
    if verbose:
        logging.getLogger("asyncio").setLevel(logging.WARNING)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Production-like debug runner for document classification"
    )
    parser.add_argument("--doc-id", required=True, help="Document ID to classify")
    parser.add_argument(
        "--trace-id",
        required=False,
        default=None,
        help="Optional trace_id for correlation",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging",
    )
    parser.add_argument(
        "--asyncio-debug",
        action="store_true",
        help="Enable asyncio debug mode",
    )
    return parser


async def run_classification(doc_id: str, trace_id: str | None = None) -> None:
    # ============================================================
    # TODO: ПОДСТАВИТЬ РЕАЛЬНЫЕ IMPORTS И ENTRYPOINT ИЗ ТВОЕГО ПРОЕКТА
    # ============================================================
    #
    # Идея такая:
    # 1. поднять container/service-factory так же, как в проде;
    # 2. получить classifier service;
    # 3. вызвать тот же classify_document(...), который реально используется.
    #
    # Примерный КАРКАС:
    #
    # from app.container import build_container
    # container = build_container()
    # classifier = container.classifier_service()
    #
    # result = await classifier.classify_document(
    #     doc_id=doc_id,
    #     trace_id=trace_id,
    # )
    #
    # print_result(result)
    #
    # ============================================================

    # ======= НИЖЕ ВРЕМЕННЫЙ ПСЕВДО-КАРКАС, ЗАМЕНИ НА РЕАЛЬНЫЙ =======
    from src.classifiers.stage8.hybrid_classifier import HybridClassifier
    from engine.content.document_content_service import DocumentContentService

    content_service = DocumentContentService()
    classifier = HybridClassifier(content_service=content_service)

    result = await classifier.classify_document(
        doc_id=doc_id,
        trace_id=trace_id,
    )

    print_result(result)


def print_result(result: Any) -> None:
    print("\n" + "=" * 100)
    print("CLASSIFICATION RESULT")
    print("=" * 100)

    if result is None:
        print("result: None")
        return

    if isinstance(result, dict):
        print(f"final_type: {result.get('final_type')}")
        print(f"final_confidence: {result.get('final_confidence')}")
        print(f"decided_by: {result.get('decided_by')}")
        print(f"requires_manual_review: {result.get('requires_manual_review')}")
        if "classification_debug" in result:
            print("classification_debug: present")
        return

    for attr in ("final_type", "final_confidence", "decided_by", "requires_manual_review"):
        if hasattr(result, attr):
            print(f"{attr}: {getattr(result, attr)}")

    if hasattr(result, "classification_debug"):
        print("classification_debug: present")


async def amain() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    configure_logging(verbose=args.verbose)

    if args.asyncio_debug:
        loop = asyncio.get_running_loop()
        loop.set_debug(True)

    await run_classification(
        doc_id=args.doc_id,
        trace_id=args.trace_id,
    )


def main() -> None:
    asyncio.run(amain(), debug=False)


if __name__ == "__main__":
    main()

    