# src/engine/playbook/retrieval_profiles.py

"""
retrieval_profiles.py — canonical routing rules для evidence bundle retrieval.

Для непрофессионального программиста:
- Когда детектор хочет проверить "есть ли governing_law в договоре?",
  ему нужно знать:
  * какие темы искать (required_topics),
  * какой минимальный citability приемлем,
  * сколько units достаточно.
- Этот файл содержит готовые RetrievalProfile для стандартных check-ов.
- Детектор выбирает профиль по имени и передаёт его EvidenceBundleBuilder.

Canonical profile families:
- governing_law:   применимое право
- jurisdiction:    подсудность / арбитраж
- liability:       ответственность и её ограничения
- payment:         платёжные условия
- warranty:        гарантии и заверения
- termination:     расторжение
- notice:          уведомления
- confidentiality: конфиденциальность
- definitions:     определения терминов
- title:           переход права собственности
"""

from __future__ import annotations

from engine.content.evidence_bundle_builder import RetrievalProfile
from services.structure.legal_unit_models import LegalUnitType

# ---------------------------------------------------------------------------
# Canonical profiles
# ---------------------------------------------------------------------------

GOVERNING_LAW_PROFILE = RetrievalProfile(
    profile_id="governing_law_check",
    query_topic="governing_law",
    required_topics=["governing_law", "choice_of_law"],
    supporting_topics=["jurisdiction", "dispute_resolution"],
    required_unit_types=[LegalUnitType.GOVERNING_LAW],
    min_citability="low",
    max_primary_units=5,
    max_supporting_units=3,
)

JURISDICTION_PROFILE = RetrievalProfile(
    profile_id="jurisdiction_check",
    query_topic="jurisdiction",
    required_topics=["jurisdiction", "arbitration"],
    supporting_topics=["governing_law", "dispute_resolution", "mediation"],
    required_unit_types=[LegalUnitType.JURISDICTION],
    min_citability="low",
    max_primary_units=5,
    max_supporting_units=3,
)

LIABILITY_CAP_PROFILE = RetrievalProfile(
    profile_id="liability_cap_check",
    query_topic="liability_cap",
    required_topics=["liability_cap", "liability_exclusion"],
    supporting_topics=["liability", "indemnification", "damages", "consequential_damages"],
    required_unit_types=[],
    min_citability="medium",
    max_primary_units=8,
    max_supporting_units=5,
)

PAYMENT_TERMS_PROFILE = RetrievalProfile(
    profile_id="payment_terms_check",
    query_topic="payment_terms",
    required_topics=["payment_terms", "purchase_price"],
    supporting_topics=["payment_schedule", "late_payment", "currency", "escrow", "deposit"],
    required_unit_types=[LegalUnitType.PAYMENT_TERM],
    min_citability="low",
    max_primary_units=10,
    max_supporting_units=5,
)

WARRANTIES_PROFILE = RetrievalProfile(
    profile_id="warranties_check",
    query_topic="warranties",
    required_topics=["warranties", "representations"],
    supporting_topics=[
        "seller_warranties",
        "buyer_warranties",
        "warranty_period",
        "warranty_cap",
        "warranty_basket",
        "warranty_breach",
    ],
    required_unit_types=[LegalUnitType.WARRANTY],
    min_citability="low",
    max_primary_units=15,
    max_supporting_units=5,
)

TERMINATION_PROFILE = RetrievalProfile(
    profile_id="termination_check",
    query_topic="termination",
    required_topics=["termination", "termination_rights"],
    supporting_topics=[
        "termination_notice",
        "termination_for_cause",
        "termination_consequences",
        "break_fee",
        "notice_period",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=10,
    max_supporting_units=5,
)

NOTICE_PROFILE = RetrievalProfile(
    profile_id="notice_check",
    query_topic="notices",
    required_topics=["notices"],
    supporting_topics=["notice_period", "notice_address"],
    required_unit_types=[LegalUnitType.NOTICE],
    min_citability="low",
    max_primary_units=5,
    max_supporting_units=3,
)

CONFIDENTIALITY_PROFILE = RetrievalProfile(
    profile_id="confidentiality_check",
    query_topic="confidentiality",
    required_topics=["confidentiality"],
    supporting_topics=["non_disclosure", "data_protection"],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=5,
    max_supporting_units=3,
)

DEFINITIONS_PROFILE = RetrievalProfile(
    profile_id="definitions_check",
    query_topic="definitions",
    required_topics=["definitions"],
    supporting_topics=["interpretation"],
    required_unit_types=[LegalUnitType.DEFINITION],
    min_citability="low",
    max_primary_units=20,
    max_supporting_units=3,
)

TITLE_TRANSFER_PROFILE = RetrievalProfile(
    profile_id="title_transfer_check",
    query_topic="title_transfer",
    required_topics=["title_transfer"],
    supporting_topics=[
        "title_warranty",
        "closing_conditions",
        "closing_date",
        "completion",
        "conditions_precedent",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=8,
    max_supporting_units=5,
)

FORCE_MAJEURE_PROFILE = RetrievalProfile(
    profile_id="force_majeure_check",
    query_topic="force_majeure",
    required_topics=["force_majeure"],
    supporting_topics=["termination", "liability_exclusion"],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=5,
    max_supporting_units=3,
)

NON_COMPETE_PROFILE = RetrievalProfile(
    profile_id="non_compete_check",
    query_topic="non_compete",
    required_topics=["non_compete"],
    supporting_topics=["non_solicitation", "confidentiality"],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=5,
    max_supporting_units=3,
)

INDEMNIFICATION_PROFILE = RetrievalProfile(
    profile_id="indemnification_check",
    query_topic="indemnification",
    required_topics=["indemnification"],
    supporting_topics=["damages", "liability", "warranty_cap"],
    required_unit_types=[],
    min_citability="medium",
    max_primary_units=8,
    max_supporting_units=5,
)

TAX_PROFILE = RetrievalProfile(
    profile_id="tax_check",
    query_topic="tax",
    required_topics=["tax"],
    supporting_topics=["vat", "stamp_duty", "purchase_price"],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=5,
    max_supporting_units=3,
)

ASSIGNMENT_PROFILE = RetrievalProfile(
    profile_id="assignment_check",
    query_topic="assignment",
    required_topics=["assignment"],
    supporting_topics=["third_party_rights"],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=5,
    max_supporting_units=3,
)


# ---------------------------------------------------------------------------
# Registry — canonical lookup по profile_id
# ---------------------------------------------------------------------------

# Все зарегистрированные профили.

PARTY_IDENTIFICATION_PROFILE = RetrievalProfile(
    profile_id="party_identification_check",
    query_topic="party_identification",
    required_topics=["preamble", "parties", "party_identification", "counterparty"],
    supporting_topics=[
        "definitions",
        "representations",
        "authority",
        "signatory",
        "corporate_approvals",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=5,
    max_supporting_units=3,
)

AUTHORITY_PROFILE = RetrievalProfile(
    profile_id="authority_check",
    query_topic="authority",
    required_topics=["authority"],
    supporting_topics=[
        "signatory",
        "corporate_approvals",
        "party_identification",
        "preamble",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=6,
    max_supporting_units=4,
)

CONSENT_PROFILE = RetrievalProfile(
    profile_id="consent_check",
    query_topic="consent",
    required_topics=["consent"],
    supporting_topics=[
        "authority",
        "corporate_approvals",
        "assignment",
        "change_of_control",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=6,
    max_supporting_units=4,
)

REGISTRATION_PROFILE = RetrievalProfile(
    profile_id="registration_check",
    query_topic="registration",
    required_topics=["registration"],
    supporting_topics=[
        "title_transfer",
        "party_identification",
        "authority",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=6,
    max_supporting_units=4,
)

TERM_AND_RENEWAL_PROFILE = RetrievalProfile(
    profile_id="term_and_renewal_check",
    query_topic="term",
    required_topics=["term", "renewal"],
    supporting_topics=[
        "notice_period",
        "termination_notice",
        "notices",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=8,
    max_supporting_units=4,
)

CHANGE_OF_CONTROL_PROFILE = RetrievalProfile(
    profile_id="change_of_control_check",
    query_topic="change_of_control",
    required_topics=["change_of_control"],
    supporting_topics=[
        "consent",
        "termination",
        "termination_rights",
        "authority",
        "corporate_approvals",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=6,
    max_supporting_units=4,
)

RENT_PROFILE = RetrievalProfile(
    profile_id="rent_check",
    query_topic="rent",
    required_topics=["rent"],
    supporting_topics=[
        "indexation",
        "utilities",
        "security_deposit",
        "payment_terms",
        "late_payment",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=8,
    max_supporting_units=5,
)

REPAIR_MAINTENANCE_PROFILE = RetrievalProfile(
    profile_id="repair_maintenance_check",
    query_topic="repair",
    required_topics=["repair", "maintenance"],
    supporting_topics=[
        "utilities",
        "insurance",
        "return_condition",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=8,
    max_supporting_units=4,
)

INTEREST_RATE_PROFILE = RetrievalProfile(
    profile_id="interest_rate_check",
    query_topic="interest_rate",
    required_topics=["interest_rate", "loan_amount"],
    supporting_topics=[
        "repayment_schedule",
        "payment_terms",
        "late_payment",
        "currency",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=8,
    max_supporting_units=4,
)

EVENT_OF_DEFAULT_PROFILE = RetrievalProfile(
    profile_id="event_of_default_check",
    query_topic="event_of_default",
    required_topics=["event_of_default", "cross_default", "acceleration"],
    supporting_topics=[
        "bankruptcy",
        "notices",
        "notice_period",
    ],
    required_unit_types=[],
    min_citability="medium",
    max_primary_units=8,
    max_supporting_units=5,
)

SECURITY_PROFILE = RetrievalProfile(
    profile_id="security_check",
    query_topic="pledge",
    required_topics=["pledge", "guarantee", "lien"],
    supporting_topics=[
        "event_of_default",
        "assignment",
        "liability",
    ],
    required_unit_types=[],
    min_citability="medium",
    max_primary_units=10,
    max_supporting_units=5,
)

ACCEPTANCE_PROFILE = RetrievalProfile(
    profile_id="acceptance_check",
    query_topic="acceptance",
    required_topics=["acceptance"],
    supporting_topics=[
        "scope_of_work",
        "technical_documentation",
        "completion_deadline",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=8,
    max_supporting_units=4,
)

LICENSE_SCOPE_PROFILE = RetrievalProfile(
    profile_id="license_scope_check",
    query_topic="license_scope",
    required_topics=["license_scope", "territory", "exclusivity"],
    supporting_topics=[
        "sublicensing",
        "royalty",
        "ip_ownership",
        "term",
        "renewal",
    ],
    required_unit_types=[],
    min_citability="low",
    max_primary_units=8,
    max_supporting_units=5,
)

FINANCIAL_COVENANT_PROFILE = RetrievalProfile(
    profile_id="financial_covenant_check",
    query_topic="financial_covenant",
    required_topics=["financial_covenant"],
    supporting_topics=[
        "event_of_default",
        "cross_default",
        "acceleration",
        "payment_terms",
    ],
    required_unit_types=[],
    min_citability="medium",
    max_primary_units=8,
    max_supporting_units=5,
)


# Используется для lookup по profile_id из YAML playbook конфигурации.
ALL_PROFILES: dict[str, RetrievalProfile] = {
    profile.profile_id: profile
    for profile in [
        GOVERNING_LAW_PROFILE,
        JURISDICTION_PROFILE,
        LIABILITY_CAP_PROFILE,
        PAYMENT_TERMS_PROFILE,
        WARRANTIES_PROFILE,
        TERMINATION_PROFILE,
        NOTICE_PROFILE,
        CONFIDENTIALITY_PROFILE,
        DEFINITIONS_PROFILE,
        TITLE_TRANSFER_PROFILE,
        FORCE_MAJEURE_PROFILE,
        NON_COMPETE_PROFILE,
        INDEMNIFICATION_PROFILE,
        TAX_PROFILE,
        ASSIGNMENT_PROFILE,
        PARTY_IDENTIFICATION_PROFILE,
        AUTHORITY_PROFILE,
        CONSENT_PROFILE,
        REGISTRATION_PROFILE,
        TERM_AND_RENEWAL_PROFILE,
        CHANGE_OF_CONTROL_PROFILE,
        RENT_PROFILE,
        REPAIR_MAINTENANCE_PROFILE,
        INTEREST_RATE_PROFILE,
        EVENT_OF_DEFAULT_PROFILE,
        SECURITY_PROFILE,
        ACCEPTANCE_PROFILE,
        LICENSE_SCOPE_PROFILE,
        FINANCIAL_COVENANT_PROFILE,
    ]
}


def get_profile(profile_id: str) -> RetrievalProfile | None:
    """
    Получить RetrievalProfile по profile_id.

    Для непрофессионального программиста:
    - Детектор вызывает get_profile("governing_law_check")
    - Получает готовый профиль и передаёт в EvidenceBundleBuilder.build()
    - Если профиль не найден — возвращает None (детектор должен обработать).
    """
    return ALL_PROFILES.get(profile_id)


def get_profiles_for_topics(topics: list[str]) -> list[RetrievalProfile]:
    """
    Найти все профили у которых required_topics пересекаются с заданными темами.

    Для непрофессионального программиста:
    - Используется когда детектор знает тему но не знает точный profile_id.
    - Пример: topics=["governing_law"] -> вернёт GOVERNING_LAW_PROFILE.
    """
    if not topics:
        return []

    topics_set = set(topics)
    matching: list[RetrievalProfile] = []

    for profile in ALL_PROFILES.values():
        profile_topics = set(profile.required_topics)
        if profile_topics & topics_set:
            matching.append(profile)

    return matching
