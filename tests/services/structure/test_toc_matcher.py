from services.structure.toc_matcher import attach_toc_matches


class DummyHeading:
    def __init__(self, uid, title, page=1):
        self.uid = uid
        self.raw_uid = uid
        self.title = title
        self.page = page


class DummyTOCEntry:
    def __init__(self, uid, title, page_hint):
        self.uid = uid
        self.title = title
        self.page_hint = page_hint
        self.match_type = None
        self.match_score = None
        self.matched_heading_uid = None
        self.matched_heading_title = None
        self.toc_missing_in_body = False


def test_attach_toc_matches_exact():
    toc_entries = [DummyTOCEntry("1", "Definitions", 3)]
    headings = [DummyHeading("1", "Definitions", 4)]

    matched = attach_toc_matches(toc_entries, headings)

    assert matched[0].match_type == "exact"
    assert matched[0].toc_missing_in_body is False


def test_attach_toc_matches_fuzzy_ocr_tolerant():
    toc_entries = [DummyTOCEntry("2", "Representations and Warranties", 10)]
    headings = [DummyHeading("2", "Representati0ns and Warranties", 10)]

    matched = attach_toc_matches(toc_entries, headings)

    assert matched[0].match_type in {"exact", "fuzzy"}
    assert matched[0].toc_missing_in_body is False


    