"""Trigger detector: использует Stage 7 relations/families."""


from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository

logger = get_logger(__name__)


class TriggerDetector:
    """
    Определяет applicable_triggers документа на основе:
    - семей документов (Stage 7 relations/families, RunnerRepository)
    - (в будущем) keyword-based / rule-based логики по тексту
    """

    def __init__(self, uow) -> None:
        # uow: твой UnitOfWork с async Session
        self.uow = uow
        self.repo = RunnerRepository(uow.session)

    async def detect_triggers(self, doc) -> list[str]:
        """
        Определить список триггеров для документа.

        Args:
            doc: ORM Document (из uow.documents).

        Returns:
            Отсортированный список уникальных строк-триггеров.
        """
        triggers: list[str] = []

        # 1. Триггеры по семейным связям (relations/families)
        family = await self.repo.get_document_family(doc.id) or []
        for member in family:
            # В RunnerRepository и YAMLRegistry используется поле doc_type
            doc_type = getattr(member, "doc_type", "") or ""
            if doc_type in ("MORTGAGE_AGREEMENT", "PLEDGE"):
                triggers.append("mortgage_related")
                break

        # 2. TODO: keyword-based триггеры по тексту/классификации
        # text = getattr(doc, "text", "") or ""
        # if "change of control" in text.lower():
        #     triggers.append("change_of_control_risk")

        unique = sorted(set(triggers))
        logger.debug("Triggers detected", doc_id=str(doc.id), triggers=unique)
        return unique
