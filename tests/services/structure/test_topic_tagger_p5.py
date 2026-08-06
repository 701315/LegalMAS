"""Tests for P5 topic taxonomy evolution."""

from types import SimpleNamespace

from services.structure.legal_unit_models import LegalUnitType
from services.structure.topic_tagger import (
    CORE_TOPICS,
    EXTENDED_ONLY_TOPICS,
    EXTENDED_TOPICS,
    KNOWN_TOPICS,
    TopicTagger,
    _LEGACY_TOPICS,
    _P5_CORE_TOPICS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unit(unit_id: str, title: str, text: str, unit_type=LegalUnitType.UNKNOWN):
    return SimpleNamespace(
        unit_id=unit_id,
        unit_type=unit_type,
        title=title,
        own_text=text,
        topic_tags=[],
    )


# ---------------------------------------------------------------------------
# Taxonomy structure tests
# ---------------------------------------------------------------------------

class TestTaxonomyStructure:

    def test_known_topics_equals_core(self):
        assert KNOWN_TOPICS is CORE_TOPICS

    def test_core_contains_legacy(self):
        assert _LEGACY_TOPICS <= CORE_TOPICS

    def test_core_contains_p5(self):
        assert _P5_CORE_TOPICS <= CORE_TOPICS

    def test_extended_contains_core(self):
        assert CORE_TOPICS <= EXTENDED_TOPICS

    def test_extended_contains_extended_only(self):
        assert EXTENDED_ONLY_TOPICS <= EXTENDED_TOPICS

    def test_no_overlap_between_legacy_and_p5(self):
        overlap = _LEGACY_TOPICS & _P5_CORE_TOPICS
        assert overlap == frozenset(), f"Unexpected overlap: {overlap}"

    def test_no_overlap_between_core_and_extended_only(self):
        overlap = CORE_TOPICS & EXTENDED_ONLY_TOPICS
        assert overlap == frozenset(), f"Unexpected overlap: {overlap}"

    def test_retrieval_profile_topics_in_core(self):
        """Topics used by retrieval_profiles.py must be in CORE."""
        profile_topics = {
            "preamble", "party_identification", "counterparty",
            "authority", "signatory", "corporate_approvals",
        }
        missing = profile_topics - CORE_TOPICS
        assert missing == set(), f"Missing from CORE: {missing}"

    def test_key_domain_topics_in_core(self):
        """Spot-check key domain topics."""
        expected_core = {
            "rent", "interest_rate", "scope_of_work",
            "license_scope", "penalty", "insurance",
            "bankruptcy", "lien", "acceptance",
            "pledge", "guarantee", "trademark",
        }
        missing = expected_core - CORE_TOPICS
        assert missing == set(), f"Missing from CORE: {missing}"

    def test_employment_topics_in_extended(self):
        """Employment topics should be in EXTENDED but not CORE."""
        employment = {"salary", "working_hours", "leave", "probation", "bonus"}
        for t in employment:
            assert t in EXTENDED_TOPICS, f"{t} not in EXTENDED"
            assert t not in CORE_TOPICS, f"{t} should not be in CORE"

    def test_taxonomy_sizes(self):
        assert len(_LEGACY_TOPICS) == 72
        assert len(CORE_TOPICS) > 100
        assert len(EXTENDED_TOPICS) > len(CORE_TOPICS)


# ---------------------------------------------------------------------------
# Regex detection tests — lease
# ---------------------------------------------------------------------------

class TestLeaseTopicDetection:

    def test_rent_detected(self):
        unit = _unit("u1", "Арендная плата", "Арендная плата уплачивается ежемесячно.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "rent" in tags

    def test_security_deposit_detected(self):
        unit = _unit("u1", "Обеспечительный платёж", "Обеспечительный платеж составляет 500 000 руб.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "security_deposit" in tags

    def test_indexation_detected(self):
        unit = _unit("u1", "Индексация", "Индексация арендной платы производится ежегодно.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "indexation" in tags

    def test_utilities_detected(self):
        unit = _unit("u1", "", "Коммунальные услуги оплачивает арендатор.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "utilities" in tags

    def test_repair_detected(self):
        unit = _unit("u1", "Ремонт", "Капитальный ремонт осуществляет арендодатель.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "repair" in tags

    def test_subletting_detected(self):
        unit = _unit("u1", "Субаренда", "Субаренда допускается с согласия арендодателя.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "subletting" in tags


# ---------------------------------------------------------------------------
# Regex detection tests — finance
# ---------------------------------------------------------------------------

class TestFinanceTopicDetection:

    def test_interest_rate_detected(self):
        unit = _unit("u1", "Процентная ставка", "Процентная ставка составляет 12% годовых.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "interest_rate" in tags

    def test_event_of_default_detected(self):
        unit = _unit("u1", "", "Событие дефолта включает неисполнение обязательств.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "event_of_default" in tags

    def test_cross_default_detected(self):
        unit = _unit("u1", "", "Перекрёстный дефолт по иным кредитным договорам.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "cross_default" in tags

    def test_pledge_detected(self):
        unit = _unit("u1", "Залог", "Исполнение обеспечено залогом имущества.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "pledge" in tags

    def test_guarantee_detected(self):
        unit = _unit("u1", "", "Обязательства обеспечены поручительством третьего лица.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "guarantee" in tags


# ---------------------------------------------------------------------------
# Regex detection tests — works / construction
# ---------------------------------------------------------------------------

class TestWorksTopicDetection:

    def test_scope_of_work_detected(self):
        unit = _unit("u1", "Техническое задание", "Объём работ определяется техническим заданием.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "scope_of_work" in tags

    def test_acceptance_detected(self):
        unit = _unit("u1", "", "Приёмка осуществляется по акту сдачи-приёмки.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "acceptance" in tags

    def test_subcontracting_detected(self):
        unit = _unit("u1", "", "Подрядчик вправе привлекать субподрядчиков.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "subcontracting" in tags

    def test_design_documentation_detected(self):
        unit = _unit("u1", "", "Проектная документация передается заказчику.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "design_documentation" in tags


# ---------------------------------------------------------------------------
# Regex detection tests — IP / license
# ---------------------------------------------------------------------------

class TestIPTopicDetection:

    def test_trademark_detected(self):
        unit = _unit("u1", "Товарный знак", "Право на использование товарного знака.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "trademark" in tags

    def test_royalty_detected(self):
        unit = _unit("u1", "", "Размер роялти определяется ежеквартально.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "royalty" in tags

    def test_sublicensing_detected(self):
        unit = _unit("u1", "", "Выдача сублицензий допускается с согласия лицензиара.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "sublicensing" in tags

    def test_exclusivity_detected(self):
        unit = _unit("u1", "", "Лицензия является неисключительной лицензией.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "exclusivity" in tags


# ---------------------------------------------------------------------------
# Regex detection tests — universal / identity
# ---------------------------------------------------------------------------

class TestUniversalTopicDetection:

    def test_penalty_detected(self):
        unit = _unit("u1", "", "Неустойка составляет 0.1% за каждый день просрочки.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "penalty" in tags

    def test_insurance_detected(self):
        unit = _unit("u1", "", "Страхование имущества осуществляется арендатором.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "insurance" in tags

    def test_bankruptcy_detected(self):
        unit = _unit("u1", "", "В случае банкротства одной из сторон.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "bankruptcy" in tags

    def test_renewal_detected(self):
        unit = _unit("u1", "", "Договор автоматически продлевается на тот же срок.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "renewal" in tags

    def test_preamble_detected(self):
        unit = _unit("u1", "", "ООО Ромашка именуемое в дальнейшем Арендодатель")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "preamble" in tags

    def test_authority_detected(self):
        unit = _unit("u1", "", "действующего на основании Устава")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "authority" in tags

    def test_change_of_control_detected(self):
        unit = _unit("u1", "", "В случае смены контроля над стороной.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "change_of_control" in tags

    def test_lien_detected(self):
        unit = _unit("u1", "", "Исполнитель имеет право удержания имущества.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "lien" in tags


# ---------------------------------------------------------------------------
# Legacy topics still work
# ---------------------------------------------------------------------------

class TestLegacyTopicsStillWork:

    def test_governing_law_still_detected(self):
        unit = _unit("u1", "Применимое право", "Governing law is English law.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "governing_law" in tags

    def test_termination_still_detected(self):
        unit = _unit("u1", "Расторжение", "Расторжение допускается с уведомлением.")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "termination" in tags

    def test_confidentiality_still_detected(self):
        unit = _unit("u1", "Конфиденциальность", "")
        tags = set(TopicTagger().tag_unit(unit).topics)
        assert "confidentiality" in tags
