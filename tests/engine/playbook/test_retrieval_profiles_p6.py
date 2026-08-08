from engine.playbook.retrieval_profiles import ALL_PROFILES, get_profile
from services.structure.topic_tagger import EXTENDED_TOPICS


NEW_PROFILES = {
    "authority_check",
    "consent_check",
    "registration_check",
    "term_and_renewal_check",
    "change_of_control_check",
    "rent_check",
    "repair_maintenance_check",
    "interest_rate_check",
    "event_of_default_check",
    "security_check",
    "acceptance_check",
    "license_scope_check",
    "financial_covenant_check",
    "insurance_check",
    "subletting_check",
    "scope_of_work_check",
    "completion_deadline_check",
    "subcontracting_check",
    "ip_ownership_check",
    "royalty_check",
    "sublicensing_check",
    "repayment_schedule_check",
    "credit_facility_check",
    "dispute_resolution_check",
    "technical_documentation_check",
}


def test_new_profiles_registered():
    missing = NEW_PROFILES - set(ALL_PROFILES.keys())
    assert not missing, f"Missing profiles: {sorted(missing)}"


def test_new_profiles_resolve_via_get_profile():
    for profile_id in NEW_PROFILES:
        assert get_profile(profile_id) is not None


def test_all_profile_topics_are_in_extended_topics():
    for profile in ALL_PROFILES.values():
        topics = set(profile.required_topics) | set(profile.supporting_topics)
        missing = topics - EXTENDED_TOPICS
        assert not missing, f"{profile.profile_id} references unknown topics: {sorted(missing)}"


        