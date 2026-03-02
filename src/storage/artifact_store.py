"""
Abstraction over MinIO/S3 for storing and retrieving artifacts.

All pipeline artifacts (PDFs, JSON layouts, results) are stored here.
Components exchange S3 URIs (references), not raw files.
"""

import io
import json

from minio import Minio
from minio.error import S3Error

from src.core.config import Settings, settings
from src.core.exceptions import PermanentError, TransientError
from src.core.logging import get_logger

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
    def layout_raw(tenant_id: str, deal_id: str, document_id: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/layouts/{document_id}/raw.json"

    @staticmethod
    def layout_sanitized(tenant_id: str, deal_id: str, document_id: str) -> str:
        return f"tenants/{tenant_id}/deals/{deal_id}/layouts/{document_id}/sanitized.json"

    @staticmethod
    def clause_tree(tenant_id: str, deal_id: str, document_id: str) -> str:
        """Путь к дереву пунктов (Stage 6)."""
        return f"tenants/{tenant_id}/deals/{deal_id}/structures/{document_id}/clause_tree.json"

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
        """Путь к реестру типов документов (глобальный)."""
        return "playbooks/document_types/registry.yaml"

    @staticmethod
    def document_type_config(doc_type_code: str) -> str:
        """Путь к YAML-конфигурации конкретного типа документа."""
        return f"playbooks/document_types/{doc_type_code}.yaml"

    @staticmethod
    def playbook_config(playbook_name: str, version: str) -> str:
        """Путь к конфигурации playbook."""
        return f"playbooks/{playbook_name}/{version}/config.yaml"


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
            if isinstance(file_data, bytes):
                data_stream = io.BytesIO(file_data)
                length = len(file_data)
            else:
                data_stream = file_data
                current_pos = data_stream.tell()
                data_stream.seek(0, 2)
                length = data_stream.tell()
                data_stream.seek(current_pos)

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
