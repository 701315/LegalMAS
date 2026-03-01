from enum import Enum


class TriggerType(str, Enum):
    """Автоматически сгенерированный список триггеров из YAML trigger_definitions."""

    AGRICULTURAL_LAND_KEYWORDS = "agricultural_land_keywords"
    BORDER_ZONE_KEYWORDS = "border_zone_keywords"
    BUILDING_SALE = "building_sale"
    FOREIGN_BUYER_KEYWORDS = "foreign_buyer_keywords"
    INDIVIDUAL_PARTY = "individual_party"
    LAND_PLOT_SALE = "land_plot_sale"
    LEASE_RELATED = "lease_related"
    LEGAL_ENTITY_PARTY = "legal_entity_party"
    MCD_COMMON_PROPERTY_SALE = "mcd_common_property_sale"
    MORTGAGE_RELATED = "mortgage_related"
    RESIDENTIAL_PROPERTY = "residential_property"
    SHARE_IN_RIGHT_SALE = "share_in_right_sale"
