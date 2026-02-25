"""
Language Detector — simple Cyrillic ratio check.
Full langdetect-based detection in Stage 6.
"""


class LanguageDetector:
    """
    Detect document language by Cyrillic character ratio.

    Threshold: >= 20% Cyrillic → Russian.
    """

    def detect(self, text: str) -> str:
        """
        Returns 'ru' if text is predominantly Cyrillic, else 'en'.
        """
        if not text:
            return "ru"
        cyrillic = sum(1 for ch in text if "\u0400" <= ch <= "\u04ff")
        ratio = cyrillic / max(len(text), 1)
        return "ru" if ratio >= 0.20 else "en"
