# src/storage/artifact_store.py

"""
Abstraction over MinIO/S3 for storing and retrieving artifacts.

All pipeline artifacts (PDFs, JSON layouts, results) are stored here.
Components exchange S3 URIs (references), not raw files.
"""

import io
import json
from urllib.parse import quote
from datetime import timedelta


from minio import Minio
from minio.error import S3Error

from .exports import ExportSuffix, build_export_filename

from core.config import Settings, settings
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger

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
        Путь к PDF-версии документа, сконвертированной из офисного формата (DOCX, DOC и т.п.).

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
    def clause_tree(tenant_id: str, deal_id: str, document_id: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/structures/{document_id}/clause_tree.json"

    @staticmethod
    def chunks(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Путь к canonical snapshot'у чанков для версии документа.

        Для непрофессионального программиста:
        - Здесь будет лежать один JSON-файл с уже посчитанными чанками
          всех уровней (section / clause / subclause) для документа.
        - Этим путём будут пользоваться:
          * chunk_builder — чтобы записать снапшот;
          * DocumentContentService / RetrievalEngine / CheckRunner — чтобы читать.
        - Мы кладём чанки рядом со структурой (clause_tree) в каталоге structures.
        """
        return f"tenants/{tenant_id}/deals/{deal_id}/structures/{document_id}/chunks.json"

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
        Одноязычный layout под выбранный основной язык сделки (Deal.primary_language).

        Формируется на основе layout_raw фильтрацией по языку.
        Используется всеми downstream-стадиями (PII, структура, LLM и т.п.).
        """
        return f"tenants/{tenant_id}/deals/{deal_id}/layouts/{document_id}/primary.json"

    @staticmethod
    def layout_primary_sanitized(tenant_id: str, deal_id: str, document_id: str) -> str:
        """
        Одноязычный layout после PII-сатнитизации.

        Структура аналогична layout_primary, но все PII-токены уже заменены.
        """
        return f"tenants/{tenant_id}/deals/{deal_id}/layouts/{document_id}/primary_sanitized.json"


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
            # Очистка пути от префикса s3:// если он передан
            clean_path = path.replace(f"s3://{self.bucket}/", "")

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
            # Сохраняем байты для локальной копии ДО создания stream
            if isinstance(file_data, bytes):
                data_stream = io.BytesIO(file_data)
                length = len(file_data)
            else:
                # Для io.BytesIO: читаем данные для локальной копии
                current_pos = file_data.tell()
                file_data.seek(0, 2)
                length = file_data.tell()
                file_data.seek(0)  # сбрасываем в начало для MinIO
                file_data.seek(current_pos)  # восстанавливаем позицию
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
            clean_path = path.replace(f"s3://{self.bucket}/", "")
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

    def get_http_url(self, path: str) -> str:
        """
        Вернуть HTTP/HTTPS URL для объекта в MinIO по s3://... или относительному пути.

        На dev-стенде этого достаточно, чтобы браузер смог открыть/скачать файл.
        При желании можно заменить реализацию на presigned URL.
        """
        # убрать префикс s3://bucket/ если он есть
        clean_path = path.replace(f"s3://{self.bucket}/", "")

        # URL-encode object name, чтобы пробелы и спецсимволы не ломали ссылку
        object_name = quote(clean_path)

        scheme = "https" if self._secure else "http"
        return f"{scheme}://{self._endpoint}/{self.bucket}/{object_name}"

    def get_presigned_get_url(self, path: str, expires_seconds: int = 3600) -> str:
        """
        Вернуть presigned URL для скачивания объекта.

        path может быть как s3://bucket/..., так и относительным путём.
        """
        clean_path = path.replace(f"s3://{self.bucket}/", "")

        # Minio ждет именно timedelta, а не int
        expires = timedelta(seconds=expires_seconds)

        return self.client.presigned_get_object(
            bucket_name=self.bucket,
            object_name=clean_path,
            expires=expires,
        )

    def exists(self, path: str) -> bool:
        """Check if an object exists at the given path."""
        try:
            clean_path = path.replace(f"s3://{self.bucket}/", "")
            self.client.stat_object(bucket_name=self.bucket, object_name=clean_path)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise TransientError(f"Failed to check existence: {e}")

    def delete(self, path: str) -> None:
        """Delete an object at the given path."""
        try:
            clean_path = path.replace(f"s3://{self.bucket}/", "")
            self.client.remove_object(bucket_name=self.bucket, object_name=clean_path)
        except S3Error as e:
            raise TransientError(f"Failed to delete artifact: {e}")

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
        Сохраняет экспортируемый артефакт (classification-report, check-results и т.п.)
        под именем {run_id}__{suffix}.{ext} в каталоге exports.
        """
        if content_type == "application/json":
            ext = "json"
        elif content_type == "text/csv":
            ext = "csv"
        else:
            ext = "bin"

        filename = build_export_filename(run_id, suffix, ext=ext)
        path = ArtifactPath.export(tenant_id, deal_id, run_id, filename)
        return self.put_file(path, data, content_type=content_type)
    
    