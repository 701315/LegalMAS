"""
Abstraction over MinIO/S3 for storing and retrieving artifacts.

All pipeline artifacts (PDFs, JSON layouts, results) are stored here.
Components exchange S3 URIs (references), not raw files.
"""

import io
import json
from datetime import timedelta
from urllib.parse import quote
from typing import Any

from minio import Minio
from minio.error import S3Error

from core.config import Settings, settings
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger

from .exports import ExportSuffix, build_export_filename

logger = get_logger(__name__)


class ArtifactPath:
    """
    Builds S3 paths according to the specification:
    /tenants/{tenant_id}/deals/{deal_id}/...
    """

    @staticmethod
    def original(tenant_id: str, deal_id: str, document_id: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/originals/{document_id}"

    @staticmethod
    def converted_pdf(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Путь к PDF-версии документа, сконвертированной из офисного формата
        (DOCX, DOC и т.п.).

        Используется в convert_worker, когда исходный файл не PDF:
        - original_ref хранит ссылку на DOCX-оригинал,
        - converted_pdf_ref хранит ссылку на этот PDF.

        Пример пути:
        tenants/abc/deals/xyz/originals/{document_id}_converted.pdf
        """
        return f"tenants/{tenant_id}/deals/{deal_id}/originals/{document_id}_converted.pdf"

    @staticmethod
    def primary_source(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Одноязычный исходный файл (source) под выбранный основной язык сделки.

        Формируется на основе original/converted_pdf на стадии
        build_primary_language_source и далее используется extract_worker.
        """
        return f"tenants/{tenant_id}/deals/{deal_id}/originals/{document_id}_primary.pdf"


    @staticmethod
    def primary_source_language_metadata(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Sidecar metadata для primary_source PDF.

        Содержит language_pipeline и language_filter metadata, созданные на
        стадии build_primary_language_source. Нужен для восстановления этих
        полей после границы PDF → extract, где layout строится заново из PDF.
        """
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/originals/"
            f"{document_id}_primary_language_metadata.json"
        )

    @staticmethod
    def layout_raw(tenant_id: str, deal_id: str, document_id: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/layouts/{document_id}/raw.json"

    @staticmethod
    def layout_sanitized(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Legacy path for pre-primary sanitized layout.

        Do not use in the active pipeline.
        Kept temporarily only for backward compatibility / migration.
        """
        return f"tenants/{tenant_id}/deals/{deal_id}/layouts/{document_id}/sanitized.json"

    @staticmethod
    def clause_tree(
        tenant_id: str,
        deal_id: str,
        document_id: str,
        document_version_id: str,
    ) -> str:
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/versions/{document_version_id}/clause_tree.json"
        )

    @staticmethod
    def file_graph(
        tenant_id: str,
        deal_id: str,
        document_id: str,
        document_version_id: str,
    ) -> str:
        """
        Путь к файловому графу (FileGraph) для КОНКРЕТНОЙ версии документа.

        Version-scoped path делает persisted structure artifacts immutable
        snapshot-ами DocumentVersion.
        """
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/versions/{document_version_id}/file_graph.json"
        )

    @staticmethod
    def segment_clause_tree(
        tenant_id: str,
        deal_id: str,
        document_id: str,
        document_version_id: str,
        segment_id: str,
    ) -> str:
        """
        Путь к ClauseTree одного логического сегмента для КОНКРЕТНОЙ версии документа.
        """
        short_id = segment_id[:8]
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/versions/{document_version_id}/segment_{short_id}.json"
        )


    @staticmethod
    def chunk_plan(
        tenant_id: str,
        deal_id: str,
        document_id: str,
        document_version_id: str,
    ) -> str:
        """
        Путь к chunk_plan артефакту для КОНКРЕТНОЙ версии документа.
        """
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/versions/{document_version_id}/chunk_plan.json"
        )


    @staticmethod
    def chunks(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Legacy путь к snapshot'у чанков для документа (CHUNKS v1).

        Важно:
        - Этот путь используется только старым кодом, который ожидает один
          chunks.json на весь файл и не знает про логические сегменты.
        - Новая архитектура CHUNKS v2 НЕ должна писать сюда данные.
          Вместо этого:
            * per-segment чанки пишутся в segment_chunks(...),
            * file-level manifest чанков — в chunks_manifest_v2(...).

        Схема пути (v1):
        tenants/{tenant_id}/deals/{deal_id}/structures/{document_id}/chunks.json
        """
        return f"tenants/{tenant_id}/deals/{deal_id}/structures/{document_id}/chunks.json"

    @staticmethod
    def chunks_manifest_v2(
        tenant_id: str,
        deal_id: str,
        document_id: str,
    ) -> str:
        """
        Путь к file-level манифесту чанков (CHUNKS v2).

        Для непрофессионального программиста:
        - Это один JSON-файл, который описывает ВЕСЬ набор чанков по файлу,
          но сам текст чанков лежит в отдельных файлах по сегментам.
        - В манифесте:
            * список сегментов,
            * для каждого сегмента ссылка на segment_chunks(...),
            * summary-метаданные (сколько чанков, какой primary-сегмент и т.п.).
        - Downstream (retrieval, checks, LLM) должен начинать чтение именно
          с этого файла, а не с legacy chunks.json.

        Пример пути:
        tenants/{tenant_id}/deals/{deal_id}/structures/{document_id}/chunks_manifest_v2.json
        """
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/chunks_manifest_v2.json"
        )

    @staticmethod
    def segment_chunks(
        tenant_id: str,
        deal_id: str,
        document_id: str,
        segment_id: str,
    ) -> str:
        """
        Путь к чанкам одного логического сегмента.

        Для непрофессионального программиста:
        В новом (v2) режиме чанки строятся отдельно для каждого сегмента,
        а не для всего файла целиком. Это значит что чанки договора и чанки
        приложения хранятся в разных файлах и никогда не смешиваются.

        chunks.json (legacy) — всегда указывает на чанки primary-сегмента,
        чтобы старый код (CheckRunner v1) продолжал работать без изменений.

        Пример пути (segment_id = "550e8400-e29b-41d4-a716-446655440000"):
        tenants/abc/deals/xyz/structures/{document_id}/chunks_550e8400.json

        Аргументы:
        - tenant_id:   ID тенанта
        - deal_id:     ID сделки
        - document_id: ID физического файла
        - segment_id:  полный UUID сегмента (make_segment_id из models.py)
        """
        short_id = segment_id[:8]
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/chunks_{short_id}.json"
        )

    @staticmethod
    def check_results(tenant_id: str, deal_id: str, run_id: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/results/{run_id}/check_results.jsonl"

    @staticmethod
    def evidence(tenant_id: str, deal_id: str, run_id: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/results/{run_id}/evidence.jsonl"

    @staticmethod
    def risk_summary(tenant_id: str, deal_id: str, run_id: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/results/{run_id}/risk_summary.json"

    @staticmethod
    def export(tenant_id: str, deal_id: str, export_id: str, filename: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/exports/{export_id}/{filename}"

    @staticmethod
    def pii_mapping(tenant_id: str, deal_id: str, document_id: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/pii/{document_id}/mapping.enc"

    @staticmethod
    def embeddings(tenant_id: str, deal_id: str, document_id: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/embeddings/{document_id}.npy"

    @staticmethod
    def document_type_registry() -> str:
        return "playbooks/document_types/registry.yaml"

    @staticmethod
    def document_type_config(doc_type_code: str) -> str:
        return f"playbooks/document_types/{doc_type_code}.yaml"

    @staticmethod
    def playbook_config(playbook_name: str, version: str) -> str:
        return f"playbooks/{playbook_name}/{version}/config.yaml"

    @staticmethod
    def layout_primary(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Одноязычный layout под выбранный основной язык сделки
        (Deal.primary_language).

        Формируется на основе layout_raw фильтрацией по языку.
        Используется всеми downstream-стадиями (PII, структура, LLM и т.п.).
        """
        return f"tenants/{tenant_id}/deals/{deal_id}/layouts/{document_id}/primary.json"

    @staticmethod
    def layout_primary_sanitized(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Одноязычный layout после PII-санитизации.

        Структура аналогична layout_primary, но все PII-токены уже заменены.
        """
        return f"tenants/{tenant_id}/deals/{deal_id}/layouts/{document_id}/primary_sanitized.json"


    @staticmethod
    def filter_decisions(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Путь к filter_decisions JSON — audit trail языковой фильтрации.

        Содержит решение по каждому элементу layout:
        какой язык был определён, какое решение принято (retained/excluded/flagged),
        по какой причине.

        Используется для:
        - отладки language filtering;
        - аудита качества фильтрации;
        - canonical path (Фаза 3): хранится рядом с layout_primary.

        Пример пути:
        tenants/abc/deals/xyz/layouts/{document_id}/filter_decisions.json
        """
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/layouts/"
            f"{document_id}/filter_decisions.json"
        )

    @staticmethod
    def legal_units_v1(
        tenant_id: str,
        deal_id: str,
        document_id: str,
        segment_id: str,
    ) -> str:
        """
        Путь к semantic layer legal units для одного логического сегмента
        (Этап 5).

        Для непрофессионального программиста:
        - Это новый артефакт, появляющийся после стадии CHUNKS.
        - Один файл на каждый сегмент (аналогично segment_chunks).
        - Содержит LegalUnitsSnapshot — список юридических единиц с типами,
          citability metrics и cross-references.
        - Downstream (retrieval, detectors) читают именно этот файл,
          а не raw chunk текст.

        Пример пути (segment_id = "550e8400-e29b-41d4-a716-446655440000"):
        tenants/abc/deals/xyz/structures/{document_id}/legal_units_550e8400.json
        """
        short_id = segment_id[:8]
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/legal_units_{short_id}.json"
        )


    @staticmethod
    def legal_units_enrichment_v1(
        tenant_id: str,
        deal_id: str,
        document_id: str,
        segment_id: str,
    ) -> str:
        """
        Путь к Phase 12 enrichment sidecar для одного логического сегмента.

        Для непрофессионального программиста:
        - Это LLM-enrichment artifact, хранится РЯДОМ с legal_units_{short_id}.json.
        - НЕ заменяет baseline legal units — это sidecar (дополнение).
        - Downstream применяет project_enriched_units() чтобы получить
        effective units = baseline + enrichment overrides.
        - Если файл отсутствует (старый документ / enrichment отключён)
        — baseline используется без изменений.

        Пример пути (segment_id = "550e8400-e29b-41d4-a716-446655440000"):
        tenants/abc/deals/xyz/structures/{document_id}/legal_units_enrichment_550e8400.json
        """
        short_id = segment_id[:8]
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/legal_units_enrichment_{short_id}.json"
        )


    @staticmethod
    def artifact_manifest(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Путь к document-level manifest канонических артефактов.

        Для непрофессионального программиста:
        - Это единая точка входа в structure/retrieval artifacts документа.
        - Файл не заменяет DocumentVersion / DocumentSegment как источник истины,
          а дублирует их refs в удобном JSON-виде для downstream, debugging и export.
        - Внутри могут лежать ссылки на:
            * file_graph.json
            * clause_tree.json
            * segment_*.json
            * chunks_manifest_v2.json
            * future cross_ref_graph.json
            * future confidence_map.json

        Пример пути:
        tenants/abc/deals/xyz/structures/{document_id}/artifact_manifest.json
        """
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/artifact_manifest.json"
        )

    @staticmethod
    def cross_ref_graph(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Путь к document-level графу перекрёстных ссылок.

        Для непрофессионального программиста:
        - Этот файл хранит найденные legal references между разделами/сегментами:
          например, "see Section 4.1", "pursuant to Article II", "defined in Annex A".
        - Используется downstream для retrieval, diagnostics и legal navigation.

        Пример пути:
        tenants/abc/deals/xyz/structures/{document_id}/cross_ref_graph.json
        """
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/cross_ref_graph.json"
        )

    @staticmethod
    def confidence_map(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Путь к confidence artifact для структуры документа.

        Для непрофессионального программиста:
        - Этот файл хранит document-level structural confidence и,
          при необходимости, confidence по узлам/сегментам.
        - Используется downstream для retrieval gating, degraded mode
          и quality diagnostics.

        Пример пути:
        tenants/abc/deals/xyz/structures/{document_id}/confidence_map.json
        """
        return (
            f"tenants/{tenant_id}/deals/{deal_id}/structures/"
            f"{document_id}/confidence_map.json"
        )


class ArtifactStore:
    """
    MinIO/S3 client for artifact storage.
    """

    def __init__(self, app_settings: Settings | None = None):
        s = app_settings or settings
        self.client = Minio(
            endpoint=s.MINIO_ENDPOINT,
            access_key=s.MINIO_ACCESS_KEY,
            secret_key=s.MINIO_SECRET_KEY,
            secure=s.MINIO_SECURE,
        )
        self.bucket = s.MINIO_BUCKET
        self._ensure_bucket()

        self._endpoint = s.MINIO_ENDPOINT
        self._secure = s.MINIO_SECURE
        self._environment = str(getattr(s, "ENVIRONMENT", "development")).lower()
        self._public_endpoint = getattr(s, "MINIO_PUBLIC_ENDPOINT", None) or None

    def _ensure_bucket(self) -> None:
        """Create bucket if it does not exist."""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info("Created MinIO bucket", bucket=self.bucket)
        except S3Error as e:
            raise TransientError(
                f"Failed to ensure bucket '{self.bucket}': {e}",
                details={"bucket": self.bucket, "error": str(e)},
            )

    def _normalize_object_path(self, path: str) -> str:
        """
        Привести путь вида s3://bucket/... или относительный путь
        к object_name внутри текущего bucket.
        """
        return path.replace(f"s3://{self.bucket}/", "")

    def put_json(self, path: str, data: dict | list) -> str:
        """Serialize data to JSON and upload to MinIO."""
        try:
            json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            data_stream = io.BytesIO(json_bytes)

            self.client.put_object(
                bucket_name=self.bucket,
                object_name=path,
                data=data_stream,
                length=len(json_bytes),
                content_type="application/json",
            )

            uri = f"s3://{self.bucket}/{path}"

            logger.debug("Stored JSON artifact", path=path, size_bytes=len(json_bytes))
            return uri
        except S3Error as e:
            raise TransientError(f"Failed to store JSON at '{path}': {e}")

    def get_json(self, path: str) -> dict | list:
        """Download JSON artifact from MinIO and deserialize."""
        try:
            clean_path = self._normalize_object_path(path)

            response = self.client.get_object(
                bucket_name=self.bucket,
                object_name=clean_path,
            )
            json_bytes = response.read()
            response.close()
            response.release_conn()
            return json.loads(json_bytes.decode("utf-8"))
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise PermanentError(f"Artifact not found: '{path}'")
            raise TransientError(f"Failed to get JSON from '{path}': {e}")

    def put_file(
        self,
        path: str,
        file_data: bytes | io.BytesIO,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload binary file to MinIO."""
        try:
            if isinstance(file_data, bytes):
                data_stream = io.BytesIO(file_data)
                length = len(file_data)
            else:
                current_pos = file_data.tell()
                file_data.seek(0, 2)
                length = file_data.tell()
                file_data.seek(0)
                file_data.seek(current_pos)
                data_stream = file_data

            self.client.put_object(
                bucket_name=self.bucket,
                object_name=path,
                data=data_stream,
                length=length,
                content_type=content_type,
            )

            return f"s3://{self.bucket}/{path}"
        except S3Error as e:
            raise TransientError(f"Failed to store file at '{path}': {e}")

    def get_file(self, path: str) -> bytes:
        """Download binary file from MinIO."""
        try:
            clean_path = self._normalize_object_path(path)
            response = self.client.get_object(
                bucket_name=self.bucket,
                object_name=clean_path,
            )
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise PermanentError(f"Artifact not found: '{path}'")
            raise TransientError(f"Failed to get file: {e}")


    def get_file_metadata(self, path: str) -> dict[str, Any]:
        """
        Вернуть метаданные файла без чтения тела объекта.

        Используется API-слоем перед streaming download:
        - чтобы fail-fast проверить существование файла;
        - чтобы вернуть корректный Content-Type;
        - чтобы при наличии проставить Content-Length / ETag / Last-Modified.
        """
        try:
            clean_path = self._normalize_object_path(path)
            stat = self.client.stat_object(
                bucket_name=self.bucket,
                object_name=clean_path,
            )

            content_type = getattr(stat, "content_type", None)
            if not content_type:
                metadata = getattr(stat, "metadata", {}) or {}
                content_type = (
                    metadata.get("Content-Type")
                    or metadata.get("content-type")
                    or "application/octet-stream"
                )

            return {
                "object_name": clean_path,
                "size": getattr(stat, "size", None),
                "etag": getattr(stat, "etag", None),
                "last_modified": getattr(stat, "last_modified", None),
                "content_type": content_type,
            }
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise PermanentError(f"Artifact not found: '{path}'")
            raise TransientError(f"Failed to get file metadata: {e}")

    def open_file_stream(self, path: str) -> Any:
        """
        Открыть объект в виде streaming-response MinIO клиента.

        Важно:
        - вызывающий код ОБЯЗАН закрыть response.close() и release_conn();
        - метод не читает объект в память целиком;
        - подходит для FastAPI StreamingResponse.
        """
        try:
            clean_path = self._normalize_object_path(path)
            return self.client.get_object(
                bucket_name=self.bucket,
                object_name=clean_path,
            )
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise PermanentError(f"Artifact not found: '{path}'")
            raise TransientError(f"Failed to open file stream: {e}")

    def get_http_url(self, path: str) -> str:
        """
        Вернуть прямой HTTP/HTTPS URL для объекта в MinIO.

        ВАЖНО:
        - Это DEV-ONLY helper.
        - В production прямые object URLs запрещены, потому что они не содержат
          подписи/expiry и могут обойти ожидаемую модель доступа.
        - Для production используйте get_presigned_get_url().

        Args:
            path: s3://bucket/... URI или относительный object path.

        Raises:
            PermanentError: Если метод вызван в production.
        """
        if self._environment == "production":
            raise PermanentError(
                "Direct HTTP artifact URLs are disabled in production. "
                "Use get_presigned_get_url() instead."
            )

        clean_path = self._normalize_object_path(path)
        object_name = quote(clean_path, safe="/")
        
        # ОПРЕДЕЛЯЕМ БАЗОВЫЙ URL: используем публичный, если он задан в .env, 
        # иначе fallback на внутренний адрес (для локальной разработки)
        if self._public_endpoint:
            base_url = self._public_endpoint.rstrip("/")
        else:
            scheme = "https" if self._secure else "http"
            base_url = f"{scheme}://{self._endpoint}"

        return f"{base_url}/{self.bucket}/{object_name}"

    def get_presigned_get_url(self, path: str, expires_seconds: int = 3600) -> str:
        """
        Вернуть presigned URL для скачивания объекта.
        Гарантирует использование MINIO_PUBLIC_ENDPOINT для корректного открытия в браузере.
        """
        clean_path = self._normalize_object_path(path)
        expires = timedelta(seconds=expires_seconds)
        
        # 1. Генерируем URL через основной клиент (он создаст его с 127.0.0.1)
        url = self.client.presigned_get_object(
            bucket_name=self.bucket,
            object_name=clean_path,
            expires=expires,
        )
        
        # 2. Если задан публичный эндпоинт, заменяем внутренний хост на публичный.
        # Подпись S3 (X-Amz-Signature) привязана к пути и параметрам, замена хоста её не ломает.
        if self._public_endpoint:
            scheme = "https" if self._secure else "http"
            old_base = f"{scheme}://{self._endpoint}"
            url = url.replace(old_base, self._public_endpoint.rstrip("/"))
            
        return url

    def exists(self, path: str) -> bool:
        """Check if an object exists at the given path."""
        try:
            clean_path = self._normalize_object_path(path)
            self.client.stat_object(bucket_name=self.bucket, object_name=clean_path)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise TransientError(f"Failed to check existence: {e}")

    def delete(self, path: str) -> None:
        """Delete an object at the given path."""
        try:
            clean_path = self._normalize_object_path(path)
            self.client.remove_object(bucket_name=self.bucket, object_name=clean_path)
        except S3Error as e:
            raise TransientError(f"Failed to delete artifact: {e}")

    def delete_many_best_effort(self, paths: list[str]) -> dict[str, Any]:
        """
        Best-effort удаление нескольких объектов.

        Не бросает исключений — логирует ошибки и продолжает.
        Возвращает summary с количеством удалённых / проваленных.

        Предназначен для post-commit cleanup stale artifacts.
        Никогда не должен ломать основной pipeline.

        Parameters
        ----------
        paths : list[str]
            Список S3 path'ей или s3://bucket/... URI для удаления.

        Returns
        -------
        dict с ключами:
            - requested: int — сколько путей запрошено
            - deleted: int — сколько успешно удалено
            - failed: int — сколько не удалось
            - errors: list[dict] — детали ошибок (path + error message)
        """
        result: dict[str, Any] = {
            "requested": len(paths),
            "deleted": 0,
            "failed": 0,
            "errors": [],
        }

        for path in paths:
            try:
                clean_path = self._normalize_object_path(path)
                self.client.remove_object(
                    bucket_name=self.bucket,
                    object_name=clean_path,
                )
                result["deleted"] += 1
            except Exception as e:
                result["failed"] += 1
                result["errors"].append({"path": path, "error": str(e)})
                logger.debug(
                    "delete_many_best_effort: failed to delete artifact",
                    path=path,
                    error=str(e),
                )

        if result["failed"] > 0:
            logger.warning(
                "delete_many_best_effort: some deletions failed",
                requested=result["requested"],
                deleted=result["deleted"],
                failed=result["failed"],
            )

        return result

    def save_export_artifact(
        self,
        tenant_id: str,
        deal_id: str,
        run_id: str,
        suffix: ExportSuffix,
        data: bytes,
        content_type: str,
    ) -> str:
        """
        Сохраняет экспортируемый артефакт под именем
        {run_id}__{suffix}.{ext} в каталоге exports.
        """
        if content_type == "application/json":
            ext = "json"
        elif content_type == "text/csv":
            ext = "csv"
        elif content_type in (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ):
            ext = "xlsx"
        elif content_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ):
            ext = "docx"
        else:
            ext = "bin"

        filename = build_export_filename(run_id, suffix, ext=ext)
        path = ArtifactPath.export(tenant_id, deal_id, run_id, filename)
        return self.put_file(path, data, content_type=content_type)


