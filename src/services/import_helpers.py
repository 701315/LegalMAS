# src/services/import_helpers.py

"""
Import Helpers — набор stateless utility-функций для import pipeline.

Назначение:
- Безопасная распаковка ZIP-архивов с защитой от path traversal / Zip Slip.
- Вычисление SHA-256 хэшей файлов для дедупликации.
- Построение dedup-ключей для outbox events.
- Определение MIME content-type по типу файла.

Почему вынесено в отдельный модуль:
- Эти функции stateless и не зависят от Celery task context.
- Могут использоваться как в use-case, так и в тестах без импорта worker layer.
- Разделение concerns: worker = transport adapter, use-case = orchestration,
  helpers = pure utility functions.

Архитектурные правила:
- Функции этого модуля НЕ должны работать с БД напрямую.
- Функции НЕ должны зависеть от Celery или async execution context.
- Функции принимают только простые типы (str, Path, list) и возвращают простые типы.
- Исключения выбрасываются как PermanentError для консистентности error handling.

Использование:
- из ImportBundleUseCase для ZIP-распаковки, SHA-256 и dedup keys;
- из тестов для изоляции логики распаковки и валидации путей;
- из любых других services, которым нужна обработка файлов без DB-зависимости.

Для непрофессионального программиста:
- compute_sha256 вычисляет уникальный отпечаток файла для проверки дубликатов;
- _extract_zip_safe безопасно распаковывает ZIP без риска «выхода» файлов наружу;
- _validate_zip_member_path проверяет, что путь внутри ZIP не содержит хакерских трюков;
- _build_language_discovery_outbox_dedup_key делает уникальный ключ для outbox события;
- _get_content_type переводит тип файла в формат, понятный браузеру и HTTP.
"""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from core.exceptions import PermanentError
from core.logging import get_logger
from ops.metrics import get_metrics

logger = get_logger(__name__)


def compute_sha256(filepath: str) -> str:
    """
    Посчитать SHA-256 хэш файла для дедупликации.

    Параметры:
    - filepath: абсолютный путь к файлу на диске.

    Возвращает:
    - строка с SHA-256 хэшем в hex-формате (64 символа).

    Для непрофессионального программиста:
    - SHA-256 — это уникальный цифровой отпечаток файла;
    - если два файла имеют одинаковый SHA-256, они идентичны побайтово;
    - используется для проверки дубликатов: если хэш уже есть в БД, файл пропускается.
    """
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _extract_zip_safe(zip_path: str, tmp_dir: str) -> list[tuple[str, str]]:
    """
    Безопасно распаковать ZIP и вернуть список (folder_path, filepath).

    Защита от атак:
    - запрещаем absolute paths внутри ZIP;
    - запрещаем '..' traversal (попытка выйти за пределы tmp_dir);
    - игнорируем directory entries;
    - нормализуем POSIX path внутри ZIP для кроссплатформенности;
    - не используем extractall() — распаковываем файл за файлом с проверкой.

    Параметры:
    - zip_path: путь к ZIP-архиву на диске;
    - tmp_dir: временная директория, куда распаковывать файлы.

    Возвращает:
    - список кортежей (folder_path, filepath), где:
      - folder_path — относительный путь папки внутри ZIP (для folder_path в Document);
      - filepath — абсолютный путь распакованного файла на диске.

    Исключения:
    - PermanentError если ZIP повреждён или содержит небезопасные пути.

    Для непрофессионального программиста:
    - ZIP может содержать файлы, которые пытаются «убежать» за пределы безопасной папки;
    - эта функция проверяет каждый файл внутри ZIP перед распаковкой;
    - если находит подозрительный путь — выбрасывает ошибку и не распаковывает вообще.
    """
    metrics = get_metrics()
    file_list: list[tuple[str, str]] = []

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue

                archive_name = member.filename
                safe_rel_path = _validate_zip_member_path(archive_name)
                destination = Path(tmp_dir) / safe_rel_path

                destination.parent.mkdir(parents=True, exist_ok=True)

                with zf.open(member, "r") as src, open(destination, "wb") as dst:
                    shutil.copyfileobj(src, dst)

                folder_path = str(safe_rel_path.parent).replace("\\", "/")
                if folder_path == ".":
                    folder_path = ""

                file_list.append((folder_path, str(destination)))
    except zipfile.BadZipFile:
        metrics.import_fail.labels(reason="bad_zip").inc()
        raise PermanentError(
            "Invalid or corrupted ZIP file",
            details={"source_path": zip_path},
        )

    logger.info(
        "ZIP extracted safely",
        extra={"total_files": len(file_list), "tmp_dir": tmp_dir},
    )
    return file_list


def _validate_zip_member_path(member_name: str) -> Path:
    """
    Провалидировать путь файла внутри ZIP и вернуть безопасный относительный Path.

    Запрещаем:
    - пустые имена;
    - абсолютные пути (начинаются с / или C:\\);
    - traversal через '..' (попытка выйти за пределы распаковки);
    - Windows drive paths (например, C:\\some\\file);
    - нормализованные пути, которые после разрешения уходят вверх.

    Параметры:
    - member_name: имя файла внутри ZIP (может быть с папками, например "docs/contract.pdf").

    Возвращает:
    - безопасный относительный Path, готовый для распаковки.

    Исключения:
    - PermanentError если путь небезопасен.

    Для непрофессионального программиста:
    - ZIP-файл может содержать хитрые пути вроде "../../etc/passwd";
    - если такой путь распаковать, можно перезаписать системные файлы;
    - эта функция проверяет каждый путь и блокирует опасные варианты.
    """
    normalized = member_name.replace("\\", "/").strip()

    if not normalized:
        raise PermanentError(
            "Invalid ZIP entry: empty path",
            details={"zip_member": member_name},
        )

    pure_path = PurePosixPath(normalized)

    if pure_path.is_absolute():
        raise PermanentError(
            "Invalid ZIP entry: absolute paths are not allowed",
            details={"zip_member": member_name},
        )

    if pure_path.parts and ":" in pure_path.parts[0]:
        raise PermanentError(
            "Invalid ZIP entry: drive paths are not allowed",
            details={"zip_member": member_name},
        )

    if any(part in ("..", "") for part in pure_path.parts):
        raise PermanentError(
            "Invalid ZIP entry: path traversal detected",
            details={"zip_member": member_name},
        )

    safe_path = Path(*pure_path.parts)

    if str(safe_path).startswith(".."):
        raise PermanentError(
            "Invalid ZIP entry: unsafe normalized path",
            details={"zip_member": member_name},
        )

    return safe_path


def _build_language_discovery_outbox_dedup_key(
    *,
    deal_id: str,
    bundle_id: str,
    document_ids: list[str],
) -> str:
    """
    Построить стабильный dedup key для outbox-события запуска language discovery.

    Смысл:
    - один import bundle должен создавать ровно одно outbox событие для discovery;
    - relay/dispatcher может использовать dedup_key для защиты от повторной публикации;
    - даже если импорт повторяется (например, retry), ключ будет тот же;
    - если набор документов другой — ключ тоже будет другой.

    Параметры:
    - deal_id: идентификатор сделки;
    - bundle_id: идентификатор bundle (операции импорта);
    - document_ids: список ID документов, для которых нужен language discovery.

    Возвращает:
    - SHA-256 хэш в hex-формате, уникальный для этого набора параметров.

    Для непрофессионального программиста:
    - функция делает уникальный ключ на основе сделки, bundle и списка документов;
    - если эти три параметра одинаковые — ключ будет одинаковый;
    - это защищает от дублирования задач: если ключ уже был — новую задачу не создавать.
    """
    normalized_doc_ids = sorted(set(document_ids))
    payload = f"{deal_id}:{bundle_id}:{','.join(normalized_doc_ids)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_content_type(filetype: str) -> str:
    """
    Преобразовать внутренний тип файла в стандартный MIME content-type.

    Параметры:
    - filetype: строка типа "pdf", "docx", "xlsx", "image" и т.п.

    Возвращает:
    - MIME-тип для HTTP/MinIO storage (например, "application/pdf").

    Для непрофессионального программиста:
    - MIME-тип говорит браузеру и серверу, какого рода файл это такой;
    - например, "application/pdf" значит "это PDF-документ";
    - функция переводит наши внутренние короткие названия типов в стандартные MIME.
    """
    content_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "image": "image/png",
    }
    return content_types.get(filetype, "application/octet-stream")
