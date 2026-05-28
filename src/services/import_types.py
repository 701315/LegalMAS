# src/services/import_types.py

"""
Import Types — типизированные command/result контракты для import pipeline.

Назначение:
- Описывает входной контракт для запуска импорта (ImportBundleCommand).
- Описывает выходной контракт результата импорта (ImportBundleResult).
- Делает взаимодействие между worker layer и services layer явным и типобезопасным.

Почему это важно:
- Раньше import pipeline передавал длинный список аргументов между функциями
  (deal_id, tenant_id, source_path, idempotency_key, run_id).
- Это повышало риск ошибок при рефакторинге: можно было перепутать порядок аргументов,
  забыть передать новое поле или случайно протащить execution-context в persistence layer.
- Явные dataclass-контракты уменьшают этот риск и делают код понятнее.

Архитектурная роль:
- ImportBundleCommand — это входная команда на выполнение import use case.
- ImportBundleResult — это типизированный результат выполнения use case.
- Worker layer создаёт ImportBundleCommand из Celery payload.
- Use case принимает ImportBundleCommand и возвращает ImportBundleResult.
- Наружу, в Celery/result backend/API, ImportBundleResult сериализуется через to_dict().
- При чтении результата из idempotency storage ImportBundleResult восстанавливается через from_dict().

Для непрофессионального программиста:
- Command — это «запрос на действие», то есть что именно надо сделать.
- Result — это «ответ после выполнения», то есть что получилось в итоге.
- Такой подход помогает не передавать по коду хаотичный набор переменных,
  а использовать один понятный объект на входе и один понятный объект на выходе.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ImportBundleCommand:
    """
    Входной контракт для запуска import pipeline.

    Содержит все параметры, необходимые для выполнения импорта:
    - идентификатор сделки;
    - идентификатор tenant'а;
    - путь к исходному файлу или ZIP-архиву;
    - опциональный idempotency key;
    - опциональный run_id для audit trail и pipeline correlation.

    Почему frozen=True:
    - команда должна быть immutable после создания;
    - это снижает риск случайной мутации параметров по ходу выполнения use case;
    - use case должен воспринимать команду как фиксированный вход.

    Для непрофессионального программиста:
    - этот объект говорит системе: «импортируй вот этот файл/архив
      в вот эту сделку от имени вот этого tenant'а».
    - после создания команды её нельзя менять, чтобы поведение было предсказуемым.
    """

    deal_id: str
    tenant_id: str
    source_path: str
    idempotency_key: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ImportBundleResult:
    """
    Выходной контракт результата import pipeline.

    Содержит агрегированную информацию о том, чем закончился импорт:
    - какой bundle был создан;
    - какие документы успешно импортированы;
    - какие документы попали в quarantine;
    - сколько было импортов, дубликатов и пропусков;
    - был ли результат зафиксирован (committed);
    - было ли создано outbox-событие на language discovery.

    Этот объект используется:
    - внутри services layer как типизированный результат use case;
    - в worker layer для сериализации через to_dict();
    - в idempotency storage как JSON-подобный результат завершённой операции.

    Для непрофессионального программиста:
    - это «отчёт» о том, как прошёл импорт;
    - он показывает, сколько файлов реально загрузилось,
      сколько ушло в карантин и был ли запущен следующий этап пайплайна.
    """

    bundle_id: str
    document_ids: list[str]
    quarantined_ids: list[str]
    imported_count: int
    quarantine_count: int
    duplicate_count: int
    skipped_count: int
    committed: bool
    language_discovery_requested: bool

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать результат импорта в plain dict.

        Используется в местах, где нужен JSON-friendly формат:
        - возврат результата из Celery task;
        - сохранение результата в idempotency storage;
        - возможная передача наружу в API / result backend.

        Возвращает:
        - словарь со всеми полями ImportBundleResult.

        Для непрофессионального программиста:
        - dataclass удобен для работы в Python-коде;
        - но наружу чаще нужно вернуть обычный словарь;
        - эта функция как раз делает такой перевод.
        """
        return {
            "bundle_id": self.bundle_id,
            "document_ids": list(self.document_ids),
            "quarantined_ids": list(self.quarantined_ids),
            "imported_count": self.imported_count,
            "quarantine_count": self.quarantine_count,
            "duplicate_count": self.duplicate_count,
            "skipped_count": self.skipped_count,
            "committed": self.committed,
            "language_discovery_requested": self.language_discovery_requested,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImportBundleResult:
        """
        Восстановить ImportBundleResult из plain dict.

        Используется в местах, где result хранится или передаётся как словарь:
        - чтение результата из idempotency storage;
        - восстановление результата из JSON-подобного payload;
        - обратное преобразование после Celery/backend serialization.

        Параметры:
        - data: словарь с полями результата импорта.

        Возвращает:
        - экземпляр ImportBundleResult.

        Исключения:
        - KeyError если в словаре отсутствует обязательное поле;
        - TypeError / ValueError если значения нельзя привести к ожидаемому типу.

        Для непрофессионального программиста:
        - если результат раньше сохранили как обычный словарь,
          эта функция собирает из него обратно нормальный typed object;
        - это полезно, чтобы не писать вручную одно и то же преобразование
          в каждом месте кода.
        """
        return cls(
            bundle_id=str(data["bundle_id"]),
            document_ids=list(data["document_ids"]),
            quarantined_ids=list(data["quarantined_ids"]),
            imported_count=int(data["imported_count"]),
            quarantine_count=int(data["quarantine_count"]),
            duplicate_count=int(data["duplicate_count"]),
            skipped_count=int(data["skipped_count"]),
            committed=bool(data["committed"]),
            language_discovery_requested=bool(data["language_discovery_requested"]),
        )
