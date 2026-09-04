// =============================================================
// src/pages/tabs/real-estate/constants.ts
// =============================================================

import type {
  CoverageRow,
  RealEstateObjectAggregate,
  RealEstateObjectDetail,
  RealEstateObjectType,
} from "./types";

export const OBJECT_TYPE_LABELS: Record<RealEstateObjectType, string> = {
  land: "Land Plot",
  building: "Building",
  premises: "Premises",
  construction: "Construction",
  unfinished: "Unfinished Construction",
  unknown: "Unknown Object",
};

export const OBJECT_TYPE_SHORT_LABELS: Record<RealEstateObjectType, string> = {
  land: "Land",
  building: "Building",
  premises: "Premises",
  construction: "Construction",
  unfinished: "Unfinished",
  unknown: "Unknown",
};

const REGISTRY_SOURCE_BY_MARKET: Record<RealEstateObjectAggregate["market"], string> = {
  RU: "EGRN",
  UAE: "Local land registry",
  EU: "National property registry",
};

const OWNERSHIP_STATUS_LABELS: Record<RealEstateObjectAggregate["ownership_status"], string> = {
  registered: "Title confirmed",
  review: "Verification required",
  not_confirmed: "Not confirmed",
};

export const COVERAGE_ROWS: CoverageRow[] = [
  {
    jurisdiction: "Russia",
    registrySources: "EGRN, public cadastral map",
    whatChecked: "Title, cadastral number, area, encumbrances",
    remarks: "Main scenario for RU real estate due diligence",
  },
  {
    jurisdiction: "UAE",
    registrySources: "Dubai Land Department / emirate land registries",
    whatChecked: "Title, ownership, plot/building registration",
    remarks: "Individual local source required per emirate",
  },
  {
    jurisdiction: "Europe",
    registrySources: "National land / property registries",
    whatChecked: "Ownership, encumbrances, title data",
    remarks: "Source depends on country and local registry",
  },
  {
    jurisdiction: "Internal company databases",
    registrySources: "Asset register, lease register, legal archive",
    whatChecked: "Internal asset status, historical documents, usage",
    remarks: "Used for cross-check with external registries",
  },
];

const BASE_OBJECTS: RealEstateObjectAggregate[] = [
  {
    id: "1",
    address: "Moscow, Lesnaya st., 12, bld. 3",
    cadastral_number: "77:01:0004012:1456",
    object_type: "building",
    risk: "medium",
    document_count: 6,
    area_sqm: 12450,
    encumbrance: true,
    first_mentioned_at: "SPA § 2.1",
    region: "Moscow",
    market: "RU",
    ownership_status: "registered",
    usage_type: "office",
  },
  {
    id: "2",
    address: "Moscow Region, Khimki, Logisticheskiy pr., 8",
    cadastral_number: "50:10:0010203:884",
    object_type: "building",
    risk: "low",
    document_count: 4,
    area_sqm: 28700,
    encumbrance: false,
    first_mentioned_at: "Disclosure Letter § 4",
    region: "Moscow Region",
    market: "RU",
    ownership_status: "registered",
    usage_type: "warehouse",
  },
  {
    id: "3",
    address: "Saint Petersburg, Pulkovskoye hwy., plot 17",
    cadastral_number: "78:14:0007689:31",
    object_type: "land",
    risk: "high",
    document_count: 5,
    area_sqm: 45200,
    encumbrance: true,
    first_mentioned_at: "Asset Schedule #3",
    region: "Saint Petersburg",
    market: "RU",
    ownership_status: "review",
    usage_type: "land_plot",
  },
  {
    id: "4",
    address: "Kazan, Tekhnicheskaya st., 25",
    cadastral_number: "16:50:090201:442",
    object_type: "premises",
    risk: "low",
    document_count: 3,
    area_sqm: 3180,
    encumbrance: false,
    first_mentioned_at: "Lease Memo",
    region: "Tatarstan",
    market: "RU",
    ownership_status: "registered",
    usage_type: "industrial",
  },
  {
    id: "5",
    address: "Dubai Industrial City, Plot A-114",
    cadastral_number: "DLD-IC-22119",
    object_type: "land",
    risk: "medium",
    document_count: 4,
    area_sqm: 19100,
    encumbrance: null,
    first_mentioned_at: "Regional Asset Note",
    region: "Dubai",
    market: "UAE",
    ownership_status: "review",
    usage_type: "land_plot",
  },
  {
    id: "6",
    address: "Warsaw, ul. Prosta 18",
    cadastral_number: "PL-WA-77821",
    object_type: "premises",
    risk: "medium",
    document_count: 2,
    area_sqm: 2140,
    encumbrance: false,
    first_mentioned_at: "Subsidiary Property Note",
    region: "Warsaw",
    market: "EU",
    ownership_status: "review",
    usage_type: "office",
  },
  {
    id: "7",
    address: "Yekaterinburg, Promyshlennaya st., 41",
    cadastral_number: "66:41:0203004:778",
    object_type: "construction",
    risk: "high",
    document_count: 5,
    area_sqm: 16800,
    encumbrance: true,
    first_mentioned_at: "Capex Addendum",
    region: "Sverdlovsk Region",
    market: "RU",
    ownership_status: "review",
    usage_type: "industrial",
  },
  {
    id: "8",
    address: "Novosibirsk, Stantsionnaya st., 59",
    cadastral_number: "54:35:101235:64",
    object_type: "building",
    risk: "low",
    document_count: 4,
    area_sqm: 9800,
    encumbrance: false,
    first_mentioned_at: "Property Register",
    region: "Novosibirsk Region",
    market: "RU",
    ownership_status: "registered",
    usage_type: "warehouse",
  },
];

const EXTRA_OBJECTS: RealEstateObjectAggregate[] = Array.from({ length: 20 }).map((_, index) => {
  const regions = [
    "Moscow",
    "Moscow Region",
    "Saint Petersburg",
    "Tatarstan",
    "Krasnodar Krai",
    "Sverdlovsk Region",
    "Samara Region",
    "Dubai",
    "Abu Dhabi",
    "Warsaw",
  ];
  const objectTypes: RealEstateObjectType[] = [
    "land",
    "building",
    "premises",
    "construction",
    "unfinished",
  ];
  const usageTypes: RealEstateObjectAggregate["usage_type"][] = [
    "office",
    "warehouse",
    "land_plot",
    "industrial",
    "retail",
    "mixed",
  ];

  const id = String(index + 9);
  const region = regions[index % regions.length];
  const object_type = objectTypes[index % objectTypes.length];
  const area = 1200 + index * 850;
  const hasEncumbrance = index % 4 === 0 ? true : index % 5 === 0 ? null : false;

  return {
    id,
    address: `${region}, Demo Property ${id}`,
    cadastral_number: `DEMO-RE-${id}`,
    object_type,
    risk: hasEncumbrance === true ? "high" : index % 3 === 0 ? "medium" : "low",
    document_count: 2 + (index % 5),
    area_sqm: area,
    encumbrance: hasEncumbrance,
    first_mentioned_at: "Demo Asset Register",
    region,
    market:
      region === "Dubai" || region === "Abu Dhabi"
        ? "UAE"
        : region === "Warsaw"
          ? "EU"
          : "RU",
    ownership_status:
      index % 6 === 0 ? "review" : index % 11 === 0 ? "not_confirmed" : "registered",
    usage_type: usageTypes[index % usageTypes.length],
  };
});

export const DEMO_OBJECTS: RealEstateObjectAggregate[] = [...BASE_OBJECTS, ...EXTRA_OBJECTS];

const BASE_DETAILS: Record<string, RealEstateObjectDetail> = {
  "1": {
    id: "1",
    shortDescription:
      "Office building identified in the main deal document package; pledge indicators present, cross-check with registry records required.",
    documents: [
      {
        id: "d-1",
        title: "SPA",
        documentType: "Transaction agreement",
        section: "§ 2.1 / Property perimeter",
        mentionRole: "Core asset",
      },
      {
        id: "d-2",
        title: "Disclosure Letter",
        documentType: "Disclosure",
        section: "Real estate schedule",
        mentionRole: "Disclosed encumbered asset",
      },
      {
        id: "d-3",
        title: "Mortgage Agreement",
        documentType: "Security document",
        section: "Object description",
        mentionRole: "Pledged property",
      },
    ],
    registry: {
      registrySource: "EGRN",
      ownershipStatus: "Title registered",
      ownerName: "Demo Real Estate LLC",
      cadastralNumber: "77:01:0004012:1456",
      objectTypeLabel: "Building",
      areaLabel: "12,450 sq. m",
      addressLabel: "Moscow, Lesnaya st., 12, bld. 3",
    },
    encumbrances: {
      hasEncumbrances: "yes",
      mortgage: "yes",
      arrest: "no",
      easement: "review",
      notes: [
        "Mortgage document present in the deal files.",
        "Verification of secured obligation volume and active record status required.",
        "Manual verification via registry extract required for easement.",
      ],
    },
    legalChecks: {
      titleChain: "review",
      registryMatch: "ok",
      zoning: "review",
      notes: [
        "Chain of title requires verification via historical documents.",
        "Object parameters regarding area and address generally match disclosure.",
      ],
    },
    mapContext: {
      region: "Moscow",
      district: "CAD",
      geoNote: "Asset is located in a business district, used as an office building.",
    },
  },
  "2": {
    id: "2",
    shortDescription:
      "Warehouse property with clear usage profile and no obvious registered encumbrances in the demo scenario.",
    documents: [
      {
        id: "d-4",
        title: "Asset Schedule",
        documentType: "Annex",
        section: "Warehouse assets",
        mentionRole: "Owned asset",
      },
      {
        id: "d-5",
        title: "Operational Memo",
        documentType: "Internal memo",
        section: "Logistics footprint",
        mentionRole: "Distribution center",
      },
    ],
    registry: {
      registrySource: "EGRN",
      ownershipStatus: "Title registered",
      ownerName: "Logistics Park LLC",
      cadastralNumber: "50:10:0010203:884",
      objectTypeLabel: "Building",
      areaLabel: "28,700 sq. m",
      addressLabel: "Moscow Region, Khimki, Logisticheskiy pr., 8",
    },
    encumbrances: {
      hasEncumbrances: "no",
      mortgage: "no",
      arrest: "no",
      easement: "no",
      notes: [
        "No explicit indications of title restrictions found in deal disclosure.",
        "Production check requires confirmation via registry extract.",
      ],
    },
    legalChecks: {
      titleChain: "ok",
      registryMatch: "ok",
      zoning: "ok",
      notes: [
        "Key object attributes align between disclosure and registry records.",
      ],
    },
    mapContext: {
      region: "Moscow Region",
      district: "Khimki",
      geoNote: "Property is part of the company's logistics infrastructure.",
    },
  },
  "3": {
    id: "3",
    shortDescription:
      "Land plot with elevated risk profile: separate check of title restrictions and title document completeness required.",
    documents: [
      {
        id: "d-6",
        title: "Asset Schedule #3",
        documentType: "Asset annex",
        section: "Land plots",
        mentionRole: "Land asset",
      },
      {
        id: "d-7",
        title: "Encumbrance Note",
        documentType: "Legal note",
        section: "Registry remarks",
        mentionRole: "Potentially encumbered plot",
      },
    ],
    registry: {
      registrySource: "EGRN",
      ownershipStatus: "Verification required",
      ownerName: "Northern Development OJSC",
      cadastralNumber: "78:14:0007689:31",
      objectTypeLabel: "Land Plot",
      areaLabel: "45,200 sq. m",
      addressLabel: "Saint Petersburg, Pulkovskoye hwy., plot 17",
    },
    encumbrances: {
      hasEncumbrances: "review",
      mortgage: "review",
      arrest: "no",
      easement: "yes",
      notes: [
        "Indicators of land usage restrictions present.",
        "Easements and permitted land use zoning require verification.",
      ],
    },
    legalChecks: {
      titleChain: "review",
      registryMatch: "review",
      zoning: "issue",
      notes: [
        "Category and permitted land use require separate legal analysis.",
        "Risk of minor mismatch between object description and registry entry.",
      ],
    },
    mapContext: {
      region: "Saint Petersburg",
      district: "Moskovsky District",
      geoNote: "Plot is associated with industrial site development.",
    },
  },
};

const generateFallbackDetail = (
  object: RealEstateObjectAggregate
): RealEstateObjectDetail => ({
  id: object.id,
  shortDescription:
    "Demonstration real estate object card. In production mode, this section collects data from deal documents, registry records, and internal databases.",
  documents: [
    {
      id: `doc-${object.id}-1`,
      title: "Asset Register",
      documentType: "Internal register",
      section: "Property list",
      mentionRole: "Identified object",
    },
    {
      id: `doc-${object.id}-2`,
      title: "Disclosure Note",
      documentType: "Disclosure",
      section: "Property references",
      mentionRole: "Referenced asset",
    },
  ],
  registry: {
    registrySource: REGISTRY_SOURCE_BY_MARKET[object.market],
    ownershipStatus: OWNERSHIP_STATUS_LABELS[object.ownership_status],
    ownerName: "Demo Property Owner",
    cadastralNumber: object.cadastral_number ?? "—",
    objectTypeLabel: OBJECT_TYPE_LABELS[object.object_type],
    areaLabel: object.area_sqm ? `${object.area_sqm.toLocaleString("en-US")} sq. m` : "—",
    addressLabel: object.address ?? "—",
  },
  encumbrances: {
    hasEncumbrances:
      object.encumbrance === true ? "yes" : object.encumbrance === false ? "no" : "review",
    mortgage: object.encumbrance === true ? "review" : "no",
    arrest: "no",
    easement: object.object_type === "land" ? "review" : "no",
    notes: [
      "Card generated from demo data to verify split-view and internal scrolling.",
      "In production, registry verification results and title restriction analysis will appear here.",
    ],
  },
  legalChecks: {
    titleChain: object.risk === "high" ? "review" : "ok",
    registryMatch: object.ownership_status === "registered" ? "ok" : "review",
    zoning:
      object.object_type === "land" || object.object_type === "unfinished" ? "review" : "ok",
    notes: [
      "Cross-checking disclosure data with external registry sources and internal asset register required.",
    ],
  },
  mapContext: {
    region: object.region,
    district: object.region,
    geoNote:
      "Demo geo-context. Production mode can utilize mapping, clustering, and address verification.",
  },
});

export const DEMO_DETAILS: Record<string, RealEstateObjectDetail> = DEMO_OBJECTS.reduce(
  (acc, item) => {
    acc[item.id] = BASE_DETAILS[item.id] ?? generateFallbackDetail(item);
    return acc;
  },
  {} as Record<string, RealEstateObjectDetail>
);


