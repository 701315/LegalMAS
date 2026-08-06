# src/services/structure/topic_tagger.py

"""
TopicTagger — rule-based маркировка LegalUnit темами.

Для непрофессионального программиста:
- После того как LegalUnitBuilder создал список LegalUnit,
  каждый unit знает свой тип (DEFINITION, OBLIGATION и т.д.),
  но не знает свою "тему" — о чём конкретно эта норма.
- TopicTagger добавляет topic_tags: например ["definitions", "purchase_price",
  "title_transfer", "governing_law"].
- Это нужно чтобы retrieval мог искать не по тексту,
  а по теме: "найди все нормы про purchase_price".

Архитектурная роль:
- Вызывается после LegalUnitBuilder.
- Работает только с LegalUnit объектами — не знает про БД, MinIO, LLM.
- Rule-based baseline: regex паттерны по title + text.
- В будущем может быть заменён LLM-based tagger без изменения интерфейса.

Canonical topic taxonomy (v2):
- CORE_TOPICS: stable regex-backed topics (rule-based detection).
- EXTENDED_TOPICS: CORE + LLM-only topics (enrichment whitelist).
- KNOWN_TOPICS: backward-compatible alias for CORE_TOPICS.
Темы сгруппированы по категориям. Каждый unit может иметь несколько тем.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from services.structure.legal_unit_models import LegalUnit, LegalUnitType

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Topic taxonomy v2
# ---------------------------------------------------------------------------

# Legacy v1 topics — stable base, не трогаем.
_LEGACY_TOPICS: frozenset[str] = frozenset(
    {
        # Определения и интерпретация
        "definitions",
        "interpretation",
        # Цена и платежи
        "purchase_price",
        "payment_terms",
        "payment_schedule",
        "late_payment",
        "currency",
        "escrow",
        "deposit",
        "fee",
        # Переход права собственности и актив
        "title_transfer",
        "title_warranty",
        "asset_description",
        "closing_conditions",
        "closing_date",
        "completion",
        # Гарантии и заверения
        "warranties",
        "representations",
        "seller_warranties",
        "buyer_warranties",
        "warranty_breach",
        "warranty_period",
        "warranty_cap",
        "warranty_basket",
        # Ответственность
        "liability",
        "liability_cap",
        "liability_exclusion",
        "indemnification",
        "damages",
        "consequential_damages",
        "force_majeure",
        # Конфиденциальность
        "confidentiality",
        "non_disclosure",
        "data_protection",
        # Конкуренция
        "non_compete",
        "non_solicitation",
        # Расторжение
        "termination",
        "termination_rights",
        "termination_notice",
        "termination_for_cause",
        "termination_consequences",
        "break_fee",
        # Уведомления и процедуры
        "notices",
        "notice_period",
        "notice_address",
        "dispute_resolution",
        "arbitration",
        "mediation",
        "expert_determination",
        # Применимое право и юрисдикция
        "governing_law",
        "jurisdiction",
        "choice_of_law",
        # Стандартные (boilerplate) нормы
        "entire_agreement",
        "amendment",
        "waiver",
        "severability",
        "assignment",
        "third_party_rights",
        "counterparts",
        "language",
        # Приложения и документы
        "appendix_reference",
        "schedule_reference",
        "exhibit_reference",
        "document_list",
        # Стороны и структура сделки
        "parties",
        "transaction_structure",
        "conditions_precedent",
        "representations_conditions",
        "regulatory_approval",
        "tax",
        "vat",
        "stamp_duty",
    }
)


# New CORE topics — regex-backed, added in P5.
_P5_CORE_TOPICS: frozenset[str] = frozenset(
    {
        # Identity / authority / party block
        "preamble",
        "party_identification",
        "counterparty",
        "authority",
        "signatory",
        "corporate_approvals",
        # Universal contract mechanics
        "consent",
        "change_of_control",
        "term",
        "renewal",
        "registration",
        "penalty",
        "insurance",
        "bankruptcy",
        # Lease / use
        "rent",
        "security_deposit",
        "indexation",
        "utilities",
        "maintenance",
        "repair",
        "subletting",
        "return_condition",
        "permitted_use",
        # Finance / security
        "interest_rate",
        "loan_amount",
        "repayment_schedule",
        "event_of_default",
        "acceleration",
        "cross_default",
        "pledge",
        "guarantee",
        "financial_covenant",
        "credit_facility",
        "lien",
        # Works / construction / design
        "scope_of_work",
        "completion_deadline",
        "acceptance",
        "technical_documentation",
        "subcontracting",
        "design_documentation",
        # Insurance / transport
        "insured_event",
        "insurance_premium",
        "coverage_limit",
        # IP / licensing
        "license_scope",
        "royalty",
        "ip_assignment",
        "territory",
        "exclusivity",
        "sublicensing",
        "ip_ownership",
        "know_how",
        "patent",
        "trademark",
    }
)

CORE_TOPICS: frozenset[str] = _LEGACY_TOPICS | _P5_CORE_TOPICS


# LLM-only expansion: valid semantic targets for enrichment policy,
# but regex baseline is intentionally deferred.
EXTENDED_ONLY_TOPICS: frozenset[str] = frozenset(
    {
        # Finance nuance
        "security_interest",
        "collateral",
        # Services nuance
        "service_scope",
        "service_levels",
        "sla",
        "delivery",
        # Insurance nuance
        "coverage_exclusions",
        "cargo_risk",
        # Works nuance
        "change_order",
        # IP nuance
        "use_restrictions",
        "copyright",
        # Employment
        "remuneration",
        "salary",
        "working_hours",
        "leave",
        "probation",
        "benefits",
        "disciplinary",
        "termination_employment",
        "overtime",
        "bonus",
        # Transport / logistics
        "dangerous_goods",
        # Intermediary
        "subagency",
        "requalification_risk",
        # Regulatory / compliance
        "sanctions",
        "anti_corruption",
        "aml_kyc",
        "export_control",
        "cybersecurity",
    }
)

EXTENDED_TOPICS: frozenset[str] = CORE_TOPICS | EXTENDED_ONLY_TOPICS

# Backward-compatible alias.
# Старый импорт KNOWN_TOPICS остаётся валидным и указывает на stable core.
KNOWN_TOPICS: frozenset[str] = CORE_TOPICS


# ---------------------------------------------------------------------------
# Паттерны для topic detection
# ---------------------------------------------------------------------------

# Структура: список кортежей (topic_name, regex_pattern)
# Порядок важен: более специфичные паттерны идут раньше.
# Каждый unit может получить несколько тем.
_TOPIC_PATTERNS: list[tuple[str, re.Pattern]] = [
    # ── Определения ──────────────────────────────────────────────────────────
    (
        "definitions",
        re.compile(
            r"\b(definitions?|defined terms?|means|shall mean|"
            r"определени[яей]|термины|означает|толкование)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "interpretation",
        re.compile(
            r"\b(interpretation|construction|понимани[еяй]|применение договора)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Identity / authority / universal mechanics ─────────────────────────
    (
        "preamble",
        re.compile(
            r"\b(hereinafter|collectively referred to as|"
            r"именуем[а-я]* в дальнейшем|совместно именуем[а-я]*|"
            r"заключили настоящий договор)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "party_identification",
        re.compile(
            r"\b(INN|TIN|OGRN|KPP|tax id|company number|registered office|"
            r"ИНН|ОГРН|КПП|местонахождени[ея]|реквизиты сторон)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "authority",
        re.compile(
            r"\b(acting by virtue of|duly authorized|power of attorney|"
            r"board resolution|действующ[а-я]* на основании|"
            r"по доверенности|уполномочен[а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "counterparty",
        re.compile(
            r"\b(counterparty|контрагент)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "signatory",
        re.compile(
            r"\b(signatory|authorized signatory|подписант|подписывающ[а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "corporate_approvals",
        re.compile(
            r"\b(corporate approvals?|board approval|shareholder approval|"
            r"major transaction|interested[- ]party transaction|"
            r"крупн[а-я]+\s+сделк|сделк[а-я]+\s+с\s+заинтересованност|"
            r"одобрени[ея]\s+(общего собрания|совета директоров))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "consent",
        re.compile(
            r"\b(prior written consent|approval of the other party|"
            r"с письменного согласия|"
            r"с предварительного письменного согласия)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "change_of_control",
        re.compile(
            r"\b(change of control|control change|"
            r"смен[аы]\s+контроля|приобретени[ея]\s+контроля|"
            r"изменени[ея]\s+состава\s+участников)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "term",
        re.compile(
            r"\b(term of (this )?agreement|duration of (this )?agreement|"
            r"effective date|effective until|"
            r"срок действия|вступает в силу|действует до)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "renewal",
        re.compile(
            r"\b(renewal|extension of term|prolongation|auto[- ]?renewal|"
            r"automatically renewed|"
            r"пролонгац[а-я]*|продлени[ея][а-я]*\s+срока|"
            r"автоматическ[а-я]*\s+пролонгац[а-я]*|"
            r"автоматическ[а-я]*\s+продлени[ея][а-я]*|"
            r"автоматическ[а-я]*\s+продлева[а-я]*|"
            r"возобновлени[ея][а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "registration",
        re.compile(
            r"\b(state registration|registration with|"
            r"государственн[а-я]+\s+регистрац|регистрация\s+договора|"
            r"росреестр|зарегистрирован)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "penalty",
        re.compile(
            r"\b(penalty|liquidated damages|"
            r"неустойк[аи]|пен[яи]|штраф|за каждый день просрочки)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "insurance",
        re.compile(
            r"\b(insurance|insure|insurance policy|"
            r"страховани[ея]|страхов[а-я]+\s+полис|застраховать)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "bankruptcy",
        re.compile(
            r"\b(bankruptcy|insolvency|winding[- ]up|"
            r"банкротств[а-я]*|несостоятельност[ьи]|ликвидаци[яи])\b",
            re.IGNORECASE,
        ),
    ),
    # ── Стороны и сделка ─────────────────────────────────────────────────────
    (
        "parties",
        re.compile(
            r"\b(parties|party|seller|buyer|purchaser|vendor|"
            r"стороны|продавец|покупатель|сторона)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "conditions_precedent",
        re.compile(
            r"\b(conditions? precedent|CP[s]?|"
            r"предварительные условия|условия вступления в силу)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "regulatory_approval",
        re.compile(
            r"\b(regulatory approval|antitrust|competition authority|clearance|"
            r"регуляторное одобрение|антимонопольн|ФАС|одобрение регулятора)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Цена и платежи ───────────────────────────────────────────────────────
    (
        "purchase_price",
        re.compile(
            r"\b(purchase price|consideration|total price|aggregate price|"
            r"цена покупки|цена приобретения|общая цена|стоимость сделки)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "payment_terms",
        re.compile(
            r"\b(payment terms?|method of payment|manner of payment|"
            r"порядок оплаты|условия оплаты|способ оплаты)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "payment_schedule",
        re.compile(
            r"\b(payment schedule|instalment|installment|tranche|"
            r"график платежей|транш|рассрочка)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "late_payment",
        re.compile(
            r"\b(late payment|default interest|interest on late payment|penalty interest|"
            r"просрочка платежа|неустойка за просрочку|пени)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "currency",
        re.compile(
            r"\b(currency|exchange rate|fx|forex|"
            r"валюта|курс обмена|обменный курс)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "escrow",
        re.compile(
            r"\b(escrow|retention|holdback|"
            r"эскроу|удержание|резервирование)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "deposit",
        re.compile(
            r"\b(deposit|advance payment|prepayment|down payment|"
            r"задаток|аванс|предоплата)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fee",
        re.compile(
            r"\b(fee[s]?|remuneration|commission|"
            r"вознаграждение|комиссия|гонорар)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Lease / use ─────────────────────────────────────────────────────────
    (
        "rent",
        re.compile(
            r"\b(rent|rental fee|lease payment|"
            r"арендн[а-я]+\s+плат[аы]|плата за аренду)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "security_deposit",
        re.compile(
            r"\b(security deposit|deposit security|"
            r"обеспечительн[а-я]+\s+плат[её]ж|гарантийн[а-я]+\s+депозит)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "indexation",
        re.compile(
            r"\b(indexation|indexed rent|CPI adjustment|"
            r"индексаци[яи]|индексация\s+арендной\s+платы|"
            r"пересмотр\s+арендной\s+платы)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "utilities",
        re.compile(
            r"\b(utilities|utility charges|"
            r"коммунальн[а-я]+\s+услуг[а-я]*|"
            r"электроэнерги[а-я]*|водоснабжени[а-я]*|отоплени[а-я]*|"
            r"эксплуатационн[а-я]+\s+расход[а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "maintenance",
        re.compile(
            r"\b(maintenance|servicing|technical maintenance|"
            r"техническ[а-я]+\s+обслуживани[ея]|"
            r"эксплуатационн[а-я]+\s+обслуживани[ея])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "repair",
        re.compile(
            r"\b(repair|capital repair|current repair|"
            r"ремонт|капитальн[а-я]+\s+ремонт|текущ[а-я]+\s+ремонт)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "subletting",
        re.compile(
            r"\b(sublease|subletting|subrent|"
            r"субаренд[аы]|передач[аи]\s+в\s+пользование\s+третьим)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "return_condition",
        re.compile(
            r"\b(return condition|handback condition|"
            r"состояни[ея]\s+при\s+возврате|возврат\s+имущества|"
            r"возврат\s+объекта)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "permitted_use",
        re.compile(
            r"\b(permitted use|use of premises|intended use|"
            r"целевое\s+назначение|назначение\s+помещения|"
            r"использовани[ея]\s+объекта)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Finance / security ──────────────────────────────────────────────────
    (
        "interest_rate",
        re.compile(
            r"\b(interest rate|rate of interest|"
            r"процентн[а-я]+\s+ставк[а-я]*|процент[а-я]*\s+за\s+пользование)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "loan_amount",
        re.compile(
            r"\b(loan amount|principal amount|facility amount|commitment amount|"
            r"сумм[аы]\s+(займа|кредита)|размер\s+кредита)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "repayment_schedule",
        re.compile(
            r"\b(repayment schedule|amortization schedule|"
            r"график\s+погашения|график\s+возврата|"
            r"погашени[ея]\s+задолженности)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "event_of_default",
        re.compile(
            r"\b(event of default|default event|default notice|"
            r"событи[ея]\s+дефолта|случа[йи]\s+неисполнени[яи])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "acceleration",
        re.compile(
            r"\b(acceleration|immediately due and payable|"
            r"досрочн[а-я]+\s+возврат|требовать\s+досрочного\s+возврата|"
            r"досрочн[а-я]+\s+истребовани)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cross_default",
        re.compile(
            r"\b(cross[-\s]?default|cross[-\s]?acceleration|"
            r"перекр[её]стн[а-я]+\s+дефолт|кросс[-\s]?дефолт)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "pledge",
        re.compile(
            r"\b(pledge|pledgor|pledgee|"
            r"залог[а-я]*|залогодатель|залогодержатель)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "guarantee",
        re.compile(
            r"\b(guarantor|surety(ship)?|bank guarantee|"
            r"банковск[а-я]+\s+гарант|поручительств[а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "financial_covenant",
        re.compile(
            r"\b(financial covenants?|maintenance covenants?|incurrence covenants?|"
            r"leverage ratio|net debt[/\s]*EBITDA|DSCR|interest coverage|"
            r"restricted payments?|финансов[а-я]+\s+ковенант|"
            r"коэффициент\s+левериджа|покрыти[ея]\s+процент)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "credit_facility",
        re.compile(
            r"\b(credit facility|facility agreement|revolving facility|term facility|"
            r"кредитн[а-я]+\s+лини[яи]|лимит\s+(задолженности|выдачи)|транш)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "lien",
        re.compile(
            r"\b(lien|right of retention|"
            r"право\s+удержания|удержание\s+(вещи|груза|имущества))\b",
            re.IGNORECASE,
        ),
    ),
    # ── Переход права собственности ──────────────────────────────────────────
    (
        "title_transfer",
        re.compile(
            r"\b(title|transfer of title|transfer of ownership|transfer of shares|"
            r"переход права собственности|переход доли|передача акций|передача имущества)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "title_warranty",
        re.compile(
            r"\b(title warranty|free from encumbrances?|unencumbered|clean title|"
            r"гарантия права собственности|свободен от обременений|без обременений)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "closing_conditions",
        re.compile(
            r"\b(conditions? (to )?closing|condition[s]? precedent|"
            r"CP[s]?|satisfaction of conditions?|"
            r"условия (закрытия|завершения)|предварительные условия)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "closing_date",
        re.compile(
            r"\b(closing date|completion date|settlement date|"
            r"дата закрытия|дата завершения|дата расчёта)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "completion",
        re.compile(
            r"\b(completion|closing|settlement|signing|"
            r"закрытие сделки|завершение сделки|подписание)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Works / construction / design ───────────────────────────────────────
    (
        "scope_of_work",
        re.compile(
            r"\b(scope of work|statement of work|"
            r"объ[её]м\s+работ|состав\s+работ|перечень\s+работ|"
            r"техническое\s+задание|задание\s+на\s+проектирование)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "completion_deadline",
        re.compile(
            r"\b(completion deadline|deadline for completion|"
            r"срок\s+выполнения|срок\s+завершения|"
            r"окончани[ея]\s+работ|не\s+позднее)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "acceptance",
        re.compile(
            r"\b(acceptance|acceptance certificate|take[- ]over certificate|"
            r"при[её]мк[аи]|акт\s+сдачи[- ]при[её]мки|"
            r"акт\s+выполненных\s+работ|акт\s+оказанных\s+услуг)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "technical_documentation",
        re.compile(
            r"\b(technical documentation|working documentation|"
            r"техническ[а-я]+\s+документац|рабоч[а-я]+\s+документац|"
            r"техническ[иео]+\s+услови[яй])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "subcontracting",
        re.compile(
            r"\b(subcontract(ing|or)?|"
            r"субподряд[а-я]*|субподрядчик[а-я]*|привлечение\s+третьих\s+лиц)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "design_documentation",
        re.compile(
            r"\b(design documentation|project documentation|engineering surveys?|"
            r"проектн[а-я]+\s+документац[а-я]*|инженерн[а-я]+\s+изыскани[а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Insurance / transport ───────────────────────────────────────────────
    (
        "insured_event",
        re.compile(
            r"\b(insured event|insured loss|"
            r"страхов[а-я]+\s+случа[йя])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "insurance_premium",
        re.compile(
            r"\b(insurance premium|premium payable|"
            r"страхов[а-я]+\s+преми[яи])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "coverage_limit",
        re.compile(
            r"\b(coverage limit|policy limit|sum insured|"
            r"страхов[а-я]+\s+сумм[аы]|лимит\s+покрытия)\b",
            re.IGNORECASE,
        ),
    ),
    # ── IP / licensing ──────────────────────────────────────────────────────
    (
        "license_scope",
        re.compile(
            r"\b(license scope|licensed rights|scope of license|"
            r"способы\s+использования|объ[её]м\s+лицензии|"
            r"право\s+на\s+использование)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "royalty",
        re.compile(
            r"\b(royalt(y|ies)|running royalty|"
            r"роялти|лицензионн[а-я]+\s+вознаграждени[а-я]*|"
            r"паушальн[а-я]+\s+плат[её]ж[а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ip_assignment",
        re.compile(
            r"\b(IP assignment|assignment of intellectual property|"
            r"отчуждени[ея]\s+исключительн[а-я]+\s+прав|"
            r"передач[аеи]\s+исключительн[а-я]+\s+прав)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "territory",
        re.compile(
            r"\b(territorial scope|"
            r"территори[яи]\s+использования|на\s+территории)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "exclusivity",
        re.compile(
            r"\b(exclusive license|non[- ]exclusive license|sole license|"
            r"исключительн[а-я]+\s+лицензи[а-я]*|неисключительн[а-я]+\s+лицензи[а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "sublicensing",
        re.compile(
            r"\b(sublicen[sc](e|ing)|"
            r"сублиценз[а-я]*|выдач[а-я]*\s+сублиценз[а-я]*|"
            r"право\s+выдавать\s+сублиценз[а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ip_ownership",
        re.compile(
            r"\b(ip ownership|ownership of intellectual property|rightsholder|"
            r"правообладател[ья]|исключительн[а-я]+\s+прав[а-я]*\s+принадлеж[а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "know_how",
        re.compile(
            r"\b(know[- ]how|trade secret|"
            r"ноу[- ]хау|секрет\s+производства)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "patent",
        re.compile(
            r"\b(patent[а-я]*|патент[а-я]*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "trademark",
        re.compile(
            r"\b(trademark|trade mark|"
            r"товарн[а-я]+\s+знак[а-я]*|знак\s+обслуживания)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Гарантии и заверения ─────────────────────────────────────────────────
    (
        "warranties",
        re.compile(
            r"\b(warrant(y|ies)|гарантии?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "representations",
        re.compile(
            r"\b(representation[s]?|represent[s]?|"
            r"заверени[яей]|подтверждени[яей])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "seller_warranties",
        re.compile(
            r"\b(seller('s)? warrant(y|ies)|vendor('s)? warrant(y|ies)|"
            r"гарантии продавца|заверения продавца)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "buyer_warranties",
        re.compile(
            r"\b(buyer('s)? warrant(y|ies)|purchaser('s)? warrant(y|ies)|"
            r"гарантии покупателя|заверения покупателя)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "warranty_period",
        re.compile(
            r"\b(warranty period|limitation period|time limit|"
            r"срок гарантии|срок исковой давности|гарантийный срок)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "warranty_cap",
        re.compile(
            r"\b(warranty cap|maximum liability|aggregate liability|"
            r"предельная ответственность|максимальная ответственность|кэп по гарантиям)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "warranty_basket",
        re.compile(
            r"\b(basket|de minimis|threshold|"
            r"порог|минимальная сумма претензии|франшиза)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Ответственность ──────────────────────────────────────────────────────
    (
        "liability",
        re.compile(
            r"\b(liabilit(y|ies)|responsible|responsibility|"
            r"ответственность|несёт ответственность)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "liability_cap",
        re.compile(
            r"\b(liability cap|cap on liability|maximum liability|"
            r"предел ответственности|максимальная ответственность|кэп)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "liability_exclusion",
        re.compile(
            r"\b(exclud(e|es|ing) liability|no liability|shall not be liable|"
            r"limitation of liability|"
            r"освобождени[еяй] от ответственности|не несёт ответственности)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "indemnification",
        re.compile(
            r"\b(indemnif(y|ies|ication)|hold harmless|"
            r"возмещение ущерба|компенсация убытков|возместить)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "damages",
        re.compile(
            r"\b(damages?|compensation|reimbursement|"
            r"убытки|возмещение|ущерб)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "consequential_damages",
        re.compile(
            r"\b(consequential|indirect|special|punitive|"
            r"косвенные убытки|упущенная выгода|штрафные убытки)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "force_majeure",
        re.compile(
            r"\b(force majeure|act of god|circumstances? beyond|"
            r"форс-мажор|непреодолимая сила|чрезвычайные обстоятельства)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Конфиденциальность ───────────────────────────────────────────────────
    (
        "confidentiality",
        re.compile(
            r"\b(confidential(ity)?|secret|proprietary information|"
            r"конфиденциальност[ьи]|коммерческая тайна|секретн)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "non_disclosure",
        re.compile(
            r"\b(non.?disclosure|NDA|shall not disclose|"
            r"неразглашение|не вправе раскрывать|запрет разглашения)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "data_protection",
        re.compile(
            r"\b(data protection|personal data|GDPR|privacy|"
            r"персональные данные|защита данных|обработка данных)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Конкуренция ──────────────────────────────────────────────────────────
    (
        "non_compete",
        re.compile(
            r"\b(non.?compete|non.?competition|competitive activity|"
            r"запрет конкуренции|не конкурировать|конкурирующая деятельность)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "non_solicitation",
        re.compile(
            r"\b(non.?solicitation|not solicit|"
            r"запрет переманивания|не переманивать сотрудников)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Расторжение ──────────────────────────────────────────────────────────
    (
        "termination",
        re.compile(
            r"\b(terminat(e|ion)|rescind|rescission|"
            r"расторжени[еяй]|прекращени[еяй] договора|отказ от договора)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "termination_rights",
        re.compile(
            r"\b(right to terminat[e]?|entitled to terminat[e]?|"
            r"право расторжени[яей]|вправе расторгнуть)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "termination_notice",
        re.compile(
            r"\b(termination notice|notice of termination|"
            r"уведомление о расторжении|извещение о прекращении)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "termination_for_cause",
        re.compile(
            r"\b(terminat[e]? for (cause|breach|default|material breach)|"
            r"расторжение по вине|расторжение в связи с нарушением)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "termination_consequences",
        re.compile(
            r"\b(consequences? of termination|effect[s]? of termination|"
            r"последстви[яей] расторжения|прекращение обязательств)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "break_fee",
        re.compile(
            r"\b(break fee|termination fee|break.up fee|reverse break fee|"
            r"компенсация при расторжении|штраф за выход)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Уведомления ──────────────────────────────────────────────────────────
    (
        "notices",
        re.compile(
            r"\b(notice[s]?|notification|communication[s]?|"
            r"уведомлени[яей]|извещени[яей]|сообщени[яей])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "notice_period",
        re.compile(
            r"\b(notice period|within \d+ (days?|business days?)|"
            r"срок уведомления|в течение \d+ (дн|рабочих дней))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "notice_address",
        re.compile(
            r"\b(notice address|address for notices?|"
            r"адрес для уведомлений|реквизиты для уведомлений)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Разрешение споров ────────────────────────────────────────────────────
    (
        "dispute_resolution",
        re.compile(
            r"\b(dispute resolution|dispute[s]?|controversies?|"
            r"разрешение споров|урегулирование разногласий)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "arbitration",
        re.compile(
            r"\b(arbitration|arbitral|ICC|LCIA|AAA|SCC|HKIAC|VIAC|"
            r"арбитраж|третейский суд|МКАС|МАС)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "mediation",
        re.compile(
            r"\b(mediation|mediator|"
            r"медиация|медиатор|примирительная процедура)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Применимое право ─────────────────────────────────────────────────────
    (
        "governing_law",
        re.compile(
            r"\b(governing law|applicable law|choice of law|"
            r"применимое право|право[,\s]которое|выбор права)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "jurisdiction",
        re.compile(
            r"\b(jurisdiction|competent court|courts? of|forum|venue|"
            r"подсудность|компетентный суд|суд по месту)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Boilerplate ──────────────────────────────────────────────────────────
    (
        "entire_agreement",
        re.compile(
            r"\b(entire agreement|whole agreement|supersedes?|"
            r"весь договор|полное соглашение|отменяет предыдущие)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "amendment",
        re.compile(
            r"\b(amend(ment)?|modif(y|ication)|variation[s]?|"
            r"изменени[еяй]|дополнени[еяй]|поправк[аи])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "waiver",
        re.compile(
            r"\b(waiver|waive[s]?|shall not constitute a waiver|"
            r"отказ от права|не является отказом)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "severability",
        re.compile(
            r"\b(severabilit(y|ies)|severable|invalid provision|"
            r"делимость|недействительное положение|сохранение силы)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "assignment",
        re.compile(
            r"\b(assign(ment)?|transfer of rights?|novation|"
            r"уступка|передача прав|новация)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "counterparts",
        re.compile(
            r"\b(counterpart[s]?|duplicate original[s]?|"
            r"экземпляр[ы]?|копии договора|подписан в \d+ экземплярах)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "language",
        re.compile(
            r"\b(language|translation|official version|"
            r"язык договора|официальный текст|перевод)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Приложения ───────────────────────────────────────────────────────────
    (
        "appendix_reference",
        re.compile(
            r"\b(appendix|annex|exhibit|schedule|attachment|"
            r"приложени[еяй]|перечень|список)\b",
            re.IGNORECASE,
        ),
    ),
    # ── Налоги ───────────────────────────────────────────────────────────────
    (
        "tax",
        re.compile(
            r"\b(tax(es)?|fiscal|taxation|"
            r"нало[г]|налогообложение|фискальн)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "vat",
        re.compile(
            r"\b(VAT|value added tax|НДС|налог на добавленную стоимость)\b",
            re.IGNORECASE,
        ),
    ),
]


# ---------------------------------------------------------------------------
# TopicTagger
# ---------------------------------------------------------------------------


@dataclass
class TopicTagResult:
    """
    Результат маркировки одного LegalUnit темами.

    unit_id:    effective_uid LegalUnit
    topics:     список тем в порядке confidence (наиболее релевантные первыми)
    match_count: сколько паттернов сработало
    """

    unit_id: str
    topics: list[str]
    match_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "topics": self.topics,
            "match_count": self.match_count,
        }


class TopicTagger:
    """
    Rule-based маркировщик тем для LegalUnit.

    Использование:
        tagger = TopicTagger()
        units = tagger.tag_units(units)  # in-place добавляет topic_tags
        results = tagger.tag_units_with_results(units)  # returns TopicTagResult

    Принципы:
    - Один unit может иметь несколько тем.
    - Темы проверяются по title (сильный сигнал) и по own_text (слабый сигнал).
    - Дубликаты тем не добавляются.
    - Темы из unit_type добавляются как structural prior (без regex проверки).
    """

    def __init__(self) -> None:
        # Маппинг LegalUnitType -> guaranteed topic tags
        # Эти темы добавляются без regex если unit_type уже определён
        self._type_to_topics: dict[LegalUnitType, list[str]] = {
            LegalUnitType.DEFINITION: ["definitions"],
            LegalUnitType.OBLIGATION: [],  # слишком широкое — не добавляем автоматически
            LegalUnitType.WARRANTY: ["warranties"],
            LegalUnitType.PAYMENT_TERM: ["payment_terms"],
            LegalUnitType.NOTICE: ["notices"],
            LegalUnitType.GOVERNING_LAW: ["governing_law"],
            LegalUnitType.JURISDICTION: ["jurisdiction"],
            LegalUnitType.APPENDIX_REFERENCE: ["appendix_reference"],
            LegalUnitType.CONFIDENTIALITY: ["confidentiality"],
            LegalUnitType.INDEMNIFICATION: ["indemnification"],
            LegalUnitType.DISPUTE_RESOLUTION: ["dispute_resolution"],
            LegalUnitType.TERMINATION_PROVISION: ["termination"],
            LegalUnitType.LIABILITY_PROVISION: ["liability"],
            LegalUnitType.GENERAL_PROVISION: [],
            LegalUnitType.UNKNOWN: [],
        }

    def tag_unit(self, unit: LegalUnit) -> TopicTagResult:
        """
        Определить темы для одного LegalUnit.

        Алгоритм:
        1. Добавляем guaranteed topics из unit_type (structural prior).
        2. Проверяем паттерны по title (вес x2 — более надёжный сигнал).
        3. Проверяем паттерны по первым 600 символам own_text.
        4. Дедуплицируем и сортируем по количеству совпадений.
        """
        topics_found: dict[str, int] = {}  # topic -> score

        # Шаг 1: structural prior из unit_type
        guaranteed = self._type_to_topics.get(unit.unit_type, [])
        for topic in guaranteed:
            topics_found[topic] = topics_found.get(topic, 0) + 10  # высокий вес

        # Шаг 2: проверяем title (вес 2)
        title = unit.title or ""
        for topic, pattern in _TOPIC_PATTERNS:
            if pattern.search(title):
                topics_found[topic] = topics_found.get(topic, 0) + 2

        # Шаг 3: проверяем own_text (вес 1)
        text_sample = (unit.own_text or "")[:600]
        if text_sample:
            for topic, pattern in _TOPIC_PATTERNS:
                if pattern.search(text_sample):
                    topics_found[topic] = topics_found.get(topic, 0) + 1

        # Сортируем по score (убывание), затем по имени (для determinism)
        sorted_topics = sorted(
            topics_found.items(),
            key=lambda x: (-x[1], x[0]),
        )
        final_topics = [topic for topic, score in sorted_topics if score > 0]

        return TopicTagResult(
            unit_id=unit.unit_id,
            topics=final_topics,
            match_count=len(final_topics),
        )

    def tag_units(self, units: list[LegalUnit]) -> list[LegalUnit]:
        """
        Добавить topic_tags ко всем LegalUnit in-place.

        Возвращает тот же список (для удобства chaining).
        """
        tagged_count = 0
        total_topics = 0

        for unit in units:
            result = self.tag_unit(unit)
            unit.topic_tags = result.topics
            if result.topics:
                tagged_count += 1
            total_topics += result.match_count

        logger.info(
            "TopicTagger: units tagged",
            extra={
                "total_units": len(units),
                "tagged_with_topics": tagged_count,
                "total_topic_assignments": total_topics,
                "avg_topics_per_unit": round(total_topics / max(len(units), 1), 2),
            },
        )

        return units

    def tag_units_with_results(
        self,
        units: list[LegalUnit],
    ) -> list[TopicTagResult]:
        """
        Определить темы и вернуть список TopicTagResult (без изменения units).

        Используется для diagnostics и тестирования.
        """
        return [self.tag_unit(unit) for unit in units]
