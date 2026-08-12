import type {
  CoverageRow,
  RealEstateObjectAggregate,
  RealEstateObjectDetail,
  RealEstateObjectType,
} from "./types";

export const OBJECT_TYPE_LABELS: Record<RealEstateObjectType, string> = {
  land: "Земельный участок",
  building: "Здание",
  premises: "Помещение",
  construction: "Сооружение",
  unfinished: "Объект незавершённого строительства",
  unknown: "Неопределённый объект",
};

export const OBJECT_TYPE_SHORT_LABELS: Record<RealEstateObjectType, string> = {
  land: "Земля",
  building: "Здание",
  premises: "Помещение",
  construction: "Сооружение",
  unfinished: "Незавершёнка",
  unknown: "Unknown",
};

const REGISTRY_SOURCE_BY_MARKET: Record<RealEstateObjectAggregate["market"], string> = {
  RU: "ЕГРН",
  UAE: "Local land registry",
  EU: "National property registry",
};

const OWNERSHIP_STATUS_LABELS: Record<RealEstateObjectAggregate["ownership_status"], string> = {
  registered: "Право подтверждено",
  review: "Требуется верификация",
  not_confirmed: "Не подтверждено",
};

export const COVERAGE_ROWS: CoverageRow[] = [
  {
    jurisdiction: "Россия",
    registrySources: "ЕГРН, публичная кадастровая карта",
    whatChecked: "Право, кадастровый номер, площадь, обременения",
    remarks: "Основной сценарий для RU real estate due diligence",
  },
  {
    jurisdiction: "UAE",
    registrySources: "Dubai Land Department / emirate land registries",
    whatChecked: "Title, ownership, plot/building registration",
    remarks: "По эмирату требуется отдельный локальный источник",
  },
  {
    jurisdiction: "Европа",
    registrySources: "Национальные land / property registries",
    whatChecked: "Ownership, encumbrances, title data",
    remarks: "Источник зависит от страны и локального регистра",
  },
  {
    jurisdiction: "Внутренние базы компании",
    registrySources: "Asset register, lease register, legal archive",
    whatChecked: "Внутренний статус актива, исторические документы, usage",
    remarks: "Используется для cross-check с внешними регистрами",
  },
];

const BASE_OBJECTS: RealEstateObjectAggregate[] = [
  {
    id: "1",
    address: "Москва, ул. Лесная, д. 12, стр. 3",
    cadastral_number: "77:01:0004012:1456",
    object_type: "building",
    risk: "medium",
    document_count: 6,
    area_sqm: 12450,
    encumbrance: true,
    first_mentioned_at: "SPA § 2.1",
    region: "Москва",
    market: "RU",
    ownership_status: "registered",
    usage_type: "office",
  },
  {
    id: "2",
    address: "Московская область, Химки, Логистический проезд, 8",
    cadastral_number: "50:10:0010203:884",
    object_type: "building",
    risk: "low",
    document_count: 4,
    area_sqm: 28700,
    encumbrance: false,
    first_mentioned_at: "Disclosure Letter § 4",
    region: "Московская область",
    market: "RU",
    ownership_status: "registered",
    usage_type: "warehouse",
  },
  {
    id: "3",
    address: "Санкт-Петербург, Пулковское шоссе, участок 17",
    cadastral_number: "78:14:0007689:31",
    object_type: "land",
    risk: "high",
    document_count: 5,
    area_sqm: 45200,
    encumbrance: true,
    first_mentioned_at: "Asset Schedule #3",
    region: "Санкт-Петербург",
    market: "RU",
    ownership_status: "review",
    usage_type: "land_plot",
  },
  {
    id: "4",
    address: "Казань, ул. Техническая, 25",
    cadastral_number: "16:50:090201:442",
    object_type: "premises",
    risk: "low",
    document_count: 3,
    area_sqm: 3180,
    encumbrance: false,
    first_mentioned_at: "Lease Memo",
    region: "Татарстан",
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
    address: "Варшава, ul. Prosta 18",
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
    address: "Екатеринбург, ул. Промышленная, 41",
    cadastral_number: "66:41:0203004:778",
    object_type: "construction",
    risk: "high",
    document_count: 5,
    area_sqm: 16800,
    encumbrance: true,
    first_mentioned_at: "Capex Addendum",
    region: "Свердловская область",
    market: "RU",
    ownership_status: "review",
    usage_type: "industrial",
  },
  {
    id: "8",
    address: "Новосибирск, ул. Станционная, 59",
    cadastral_number: "54:35:101235:64",
    object_type: "building",
    risk: "low",
    document_count: 4,
    area_sqm: 9800,
    encumbrance: false,
    first_mentioned_at: "Property Register",
    region: "Новосибирская область",
    market: "RU",
    ownership_status: "registered",
    usage_type: "warehouse",
  },
];

const EXTRA_OBJECTS: RealEstateObjectAggregate[] = Array.from({ length: 20 }).map((_, index) => {
  const regions = [
    "Москва",
    "Московская область",
    "Санкт-Петербург",
    "Татарстан",
    "Краснодарский край",
    "Свердловская область",
    "Самарская область",
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
      "Офисное здание, выявленное в основном пакете документов сделки; присутствуют признаки залога и требуется сопоставление с регистрационными записями.",
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
      registrySource: "ЕГРН",
      ownershipStatus: "Право зарегистрировано",
      ownerName: "ООО «Демо Недвижимость»",
      cadastralNumber: "77:01:0004012:1456",
      objectTypeLabel: "Здание",
      areaLabel: "12 450 кв. м",
      addressLabel: "Москва, ул. Лесная, д. 12, стр. 3",
    },
    encumbrances: {
      hasEncumbrances: "yes",
      mortgage: "yes",
      arrest: "no",
      easement: "review",
      notes: [
        "В документах сделки присутствует ипотечный документ.",
        "Требуется проверить объём обеспеченного обязательства и актуальный статус записи.",
        "По сервитуту требуется ручная верификация по реестровой выписке.",
      ],
    },
    legalChecks: {
      titleChain: "review",
      registryMatch: "ok",
      zoning: "review",
      notes: [
        "Цепочка титула требует проверки по историческим документам.",
        "Параметры объекта по площади и адресу в целом совпадают с раскрытием.",
      ],
    },
    mapContext: {
      region: "Москва",
      district: "ЦАО",
      geoNote: "Актив находится в деловом районе, используется как офисный объект.",
    },
  },
  "2": {
    id: "2",
    shortDescription:
      "Складской объект с понятным профилем использования и без явных признаков зарегистрированных ограничений в demo-сценарии.",
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
      registrySource: "ЕГРН",
      ownershipStatus: "Право зарегистрировано",
      ownerName: "ООО «Логистика Парк»",
      cadastralNumber: "50:10:0010203:884",
      objectTypeLabel: "Здание",
      areaLabel: "28 700 кв. м",
      addressLabel: "Московская область, Химки, Логистический проезд, 8",
    },
    encumbrances: {
      hasEncumbrances: "no",
      mortgage: "no",
      arrest: "no",
      easement: "no",
      notes: [
        "В раскрытии сделки не выявлены явные указания на ограничения права.",
        "Для production-проверки требуется подтверждение по реестровой выписке.",
      ],
    },
    legalChecks: {
      titleChain: "ok",
      registryMatch: "ok",
      zoning: "ok",
      notes: [
        "Основные атрибуты объекта согласуются между disclosure и реестровым контуром.",
      ],
    },
    mapContext: {
      region: "Московская область",
      district: "Химки",
      geoNote: "Объект относится к логистической инфраструктуре компании.",
    },
  },
  "3": {
    id: "3",
    shortDescription:
      "Земельный участок с повышенным уровнем риска: требуется отдельная проверка ограничений права и полноты правоустанавливающих документов.",
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
      registrySource: "ЕГРН",
      ownershipStatus: "Требуется верификация",
      ownerName: "АО «Северный Девелопмент»",
      cadastralNumber: "78:14:0007689:31",
      objectTypeLabel: "Земельный участок",
      areaLabel: "45 200 кв. м",
      addressLabel: "Санкт-Петербург, Пулковское шоссе, участок 17",
    },
    encumbrances: {
      hasEncumbrances: "review",
      mortgage: "review",
      arrest: "no",
      easement: "yes",
      notes: [
        "Есть признаки ограничений использования участка.",
        "Требуется проверить сервитуты и допустимое использование по градостроительному контуру.",
      ],
    },
    legalChecks: {
      titleChain: "review",
      registryMatch: "review",
      zoning: "issue",
      notes: [
        "По категории и разрешённому использованию нужен отдельный юридический анализ.",
        "В описании объекта есть риск неполного совпадения с реестровой записью.",
      ],
    },
    mapContext: {
      region: "Санкт-Петербург",
      district: "Московский район",
      geoNote: "Участок связан с развитием производственной площадки.",
    },
  },
};

const generateFallbackDetail = (
  object: RealEstateObjectAggregate
): RealEstateObjectDetail => ({
  id: object.id,
  shortDescription:
    "Демонстрационная карточка объекта недвижимости. В production-режиме здесь будет собираться описание из документов сделки, реестровых данных и внутренних баз компании.",
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
    areaLabel: object.area_sqm ? `${object.area_sqm.toLocaleString("ru-RU")} кв. м` : "—",
    addressLabel: object.address ?? "—",
  },
  encumbrances: {
    hasEncumbrances:
      object.encumbrance === true ? "yes" : object.encumbrance === false ? "no" : "review",
    mortgage: object.encumbrance === true ? "review" : "no",
    arrest: "no",
    easement: object.object_type === "land" ? "review" : "no",
    notes: [
      "Карточка сформирована из demo-данных для проверки split-view и внутреннего скролла.",
      "В боевом режиме здесь будут результаты реестровой проверки и анализ ограничений права.",
    ],
  },
  legalChecks: {
    titleChain: object.risk === "high" ? "review" : "ok",
    registryMatch: object.ownership_status === "registered" ? "ok" : "review",
    zoning:
      object.object_type === "land" || object.object_type === "unfinished" ? "review" : "ok",
    notes: [
      "Требуется сопоставление данных disclosure с внешним registry source и внутренним реестром активов.",
    ],
  },
  mapContext: {
    region: object.region,
    district: object.region,
    geoNote:
      "Демо-геоконтекст. В production-режиме может использоваться карта, кластеризация и сверка по адресным данным.",
  },
});

export const DEMO_DETAILS: Record<string, RealEstateObjectDetail> = DEMO_OBJECTS.reduce(
  (acc, item) => {
    acc[item.id] = BASE_DETAILS[item.id] ?? generateFallbackDetail(item);
    return acc;
  },
  {} as Record<string, RealEstateObjectDetail>
);


