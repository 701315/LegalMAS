import asyncio
from src.classifiers.hybrid_classifier import HybridClassifier
from src.classifiers.rule_based import RuleBasedClassifier
from src.classifiers.keyword_analyzer import KeywordAnalyzer
from src.classifiers.semantic_matcher import SemanticMatcher

async def run_smoke():
    reg_path = "playbooks/document_types"
    print("--- 1. Initializing Hybrid Classifier ---")
    hc = HybridClassifier(
        rule_based=RuleBasedClassifier(reg_path),
        keyword_analyzer=KeywordAnalyzer(reg_path),
        semantic_matcher=SemanticMatcher(registry_path=reg_path)
    )

    print("\n--- 2. Running Real Estate Classification Test ---")
    test_text = """
    ДОГОВОР КУПЛИ-ПРОДАЖИ НЕДВИЖИМОСТИ
    Продавец обязуется передать в собственность Покупателя квартиру.
    Кадастровый номер: 77:01:0001001:1234.
    Объект недвижимости находится в ипотеке.
    """
    
    res = await hc.classify(
        text=test_text,
        text_sanitized=test_text,
        filename="contract_draft_1.pdf",
        folder_path="01. Real Estate"
    )

    print(f"RESULT DOCTYPE: {res.doctype}")
    print(f"CONFIDENCE: {res.confidence}")
    print(f"LANGUAGE: {res.language}")
    print(f"JURISDICTION: {res.jurisdiction}")
    print(f"TRIGGERS: {res.applicable_triggers}")
    print(f"LEVELS TRIED: {res.details['levels_tried']}")

if __name__ == "__main__":
    asyncio.run(run_smoke())