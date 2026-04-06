from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

# ── Constants ─────────────────────────────────────────────────────────────────
APP_NAME = "office-converter"
APP_VERSION = "2.1.0"

BASE_TMP_DIR = Path(os.getenv("CONVERTER_TMP_DIR", "/tmp/office-converter"))
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_BYTES", str(100 * 1024 * 1024)))
LIBREOFFICE_TIMEOUT_SECONDS = int(os.getenv("LIBREOFFICE_TIMEOUT_SECONDS", "180"))
ENABLE_PDF_VALIDATION = os.getenv("ENABLE_PDF_VALIDATION", "true").lower() == "true"
LOG_PDF_TEXT_PREVIEW = os.getenv("LOG_PDF_TEXT_PREVIEW", "false").lower() == "true"
PDF_TEXT_PREVIEW_CHARS = int(os.getenv("PDF_TEXT_PREVIEW_CHARS", "500"))
ALLOWED_OUTPUT_FORMATS = {"pdf"}

ALLOWED_EXTENSIONS = {
    "docx", "doc", "xlsx", "xls", "pptx", "ppt",
    "odt", "ods", "odp", "rtf", "csv", "html", "htm",
}

# ── Logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger(APP_NAME)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)

# ── Prometheus metrics ────────────────────────────────────────────────────────
REQUESTS_TOTAL = Counter(
    "office_converter_requests_total",
    "Total HTTP requests",
    ["endpoint", "status"],
)
CONVERSIONS_TOTAL = Counter(
    "office_converter_conversions_total",
    "Total LibreOffice conversion attempts",
    ["input_ext", "status"],
)
CONVERSION_DURATION = Histogram(
    "office_converter_conversion_duration_seconds",
    "LibreOffice conversion wall-clock duration",
    ["input_ext"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 180, 300),
)
ACTIVE_CONVERSIONS = Gauge(
    "office_converter_active_conversions",
    "Number of conversions currently in progress",
)
VALIDATION_FAILURES_TOTAL = Counter(
    "office_converter_validation_failures_total",
    "PDF quality validation failures",
    ["reason"],
)

# ── Process-level shutdown flag (per uvicorn worker process) ──────────────────
_shutdown: bool = False


# ── Lifespan (replaces deprecated @app.on_event) ─────────────────────────────
@asynccontextmanager
async def lifespan(_app: FastAPI):
    BASE_TMP_DIR.mkdir(parents=True, exist_ok=True)
    _json_log("startup", app=APP_NAME, version=APP_VERSION, tmp_dir=str(BASE_TMP_DIR))
    yield
    global _shutdown
    _shutdown = True
    _json_log("shutdown", app=APP_NAME)


app = FastAPI(
    title="Office to PDF Converter",
    version=APP_VERSION,
    debug=False,
    lifespan=lifespan,
)


# ── Pydantic models ───────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str
    app: str
    version: str


class ConversionQuality(BaseModel):
    pages: int | None = None
    extracted_chars: int | None = None
    replacement_char_ratio: float | None = None
    contains_cyrillic: bool | None = None
    contains_arabic: bool | None = None
    contains_cjk: bool | None = None
    contains_latin: bool | None = None
    likely_text_pdf: bool | None = None
    warnings: list[str] = Field(default_factory=list)


class ConversionDiagnostics(BaseModel):
    request_id: str
    input_filename: str
    input_ext: str
    sha256: str
    libreoffice_cmd: list[str]
    stdout: str | None = None
    stderr: str | None = None
    duration_seconds: float
    output_filename: str | None = None
    quality: ConversionQuality | None = None


# ── Internal helpers ──────────────────────────────────────────────────────────
def _json_log(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))


def _sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    # Allow: word chars, hyphen, dot, space, parens, Cyrillic, Arabic, CJK
    name = re.sub(r"[^\w\-. ()\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF]", "_", name)
    return name[:255] or "document"


def _get_extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def _allowed_file(filename: str) -> bool:
    return _get_extension(filename) in ALLOWED_EXTENSIONS


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_convert_to_arg(input_ext: str) -> str:
    """Build LibreOffice --convert-to argument with font-embedding and tagged PDF options."""
    pdf_options = {
        "SelectPdfVersion": 1,          # PDF 1.4 — broad parser compatibility
        "UseTaggedPDF": "true",          # logical reading order for pdfplumber / pdfminer
        "EmbedStandardFonts": "true",    # prevents tofu/■ for Cyrillic, Arabic, CJK
        "ExportBookmarks": "true",
        "ExportNotes": "false",
        "ReduceImageResolution": "false",
        "UseLosslessCompression": "true",
    }
    if input_ext in {"xlsx", "xls", "ods", "csv"}:
        filter_name = "calc_pdf_Export"
    elif input_ext in {"pptx", "ppt", "odp"}:
        filter_name = "impress_pdf_Export"
    else:
        filter_name = "writer_pdf_Export"
    options = ",".join(f"{k}={v}" for k, v in pdf_options.items())
    return f"pdf:{filter_name}:{options}"


def _build_infilter_arg(input_ext: str) -> str | None:
    if input_ext == "csv":
        return "Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,true"
    if input_ext in {"html", "htm"}:
        return "HTML (StarWriter)"
    return None


def _find_generated_pdf(outdir: Path, source_name: str) -> Path | None:
    """Locate the PDF produced by LibreOffice inside outdir."""
    exact = outdir / f"{Path(source_name).stem}.pdf"
    if exact.exists():
        return exact
    # Fallback: newest PDF in output dir (LibreOffice may mangle names with special chars)
    pdfs = sorted(outdir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    return pdfs[0] if pdfs else None


def _extract_text_and_quality(pdf_path: Path) -> tuple[str, ConversionQuality]:
    """Single pdfplumber pass — returns (preview_text, quality).
    Called at most once per request to avoid double IO.
    Side-effects: increments Prometheus counters for validation failures."""
    quality = ConversionQuality(warnings=[])
    if not ENABLE_PDF_VALIDATION:
        return "", quality
    try:
        import pdfplumber
    except Exception:
        quality.warnings.append("pdfplumber_unavailable")
        return "", quality

    text_parts: list[str] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            quality.pages = len(pdf.pages)
            for page in pdf.pages[: min(5, len(pdf.pages))]:
                text = page.extract_text() or ""
                if text:
                    text_parts.append(text)
    except Exception as exc:
        quality.warnings.append(f"pdfplumber_error:{exc!s}")
        return "", quality

    preview = "\n".join(text_parts)
    quality.extracted_chars = len(preview)

    if preview:
        replacement_count = preview.count("■") + preview.count("\ufffd")
        quality.replacement_char_ratio = replacement_count / max(len(preview), 1)
        quality.contains_cyrillic = bool(re.search(r"[\u0400-\u04FF]", preview))
        quality.contains_arabic = bool(re.search(r"[\u0600-\u06FF]", preview))
        quality.contains_cjk = bool(re.search(r"[\u4E00-\u9FFF]", preview))
        quality.contains_latin = bool(re.search(r"[A-Za-z]", preview))
        quality.likely_text_pdf = True
    else:
        quality.likely_text_pdf = False
        quality.warnings.append("no_text_extracted")

    # Validation side-effects
    if (quality.pages or 0) == 0:
        VALIDATION_FAILURES_TOTAL.labels(reason="zero_pages").inc()
    if (quality.extracted_chars or 0) == 0:
        quality.warnings.append("pdf_has_no_extractable_text")
    if (quality.replacement_char_ratio or 0.0) > 0.15:
        VALIDATION_FAILURES_TOTAL.labels(reason="high_replacement_ratio").inc()
        quality.warnings.append("high_replacement_character_ratio")

    return preview[:PDF_TEXT_PREVIEW_CHARS], quality


def _cleanup_paths(*paths: Path) -> None:
    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        except Exception as exc:
            _json_log("cleanup_failed", path=str(path), error=str(exc))


async def _read_upload_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max allowed: {max_bytes} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _run_soffice(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Blocking LibreOffice call — must be run via asyncio.to_thread."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={
            **os.environ,
            "HOME": "/tmp",
            "TMPDIR": str(BASE_TMP_DIR),
            "LANG": os.getenv("LANG", "C.UTF-8"),
            "LC_ALL": os.getenv("LC_ALL", "C.UTF-8"),
        },
    )


def _build_soffice_cmd(
    input_path: Path,
    profile_dir: Path,
    output_dir: Path,
    input_ext: str,
) -> list[str]:
    cmd = [
        "soffice",
        "--headless",
        "--nologo",
        "--nofirststartwizard",
        "--norestore",
        f"-env:UserInstallation=file://{profile_dir}",
    ]
    infilter = _build_infilter_arg(input_ext)
    if infilter:
        cmd.extend(["--infilter", infilter])
    cmd.extend([
        "--convert-to", _build_convert_to_arg(input_ext),
        "--outdir", str(output_dir),
        str(input_path),
    ])
    return cmd


def _prepare_request_dirs(request_id: str) -> tuple[Path, Path, Path, Path]:
    """Create per-request isolated tmp tree. Returns (request_dir, input_path_parent, profile_dir, output_dir)."""
    request_dir = Path(tempfile.mkdtemp(prefix=f"{request_id}_", dir=BASE_TMP_DIR))
    profile_dir = request_dir / "lo-profile"
    output_dir = request_dir / "output"
    profile_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return request_dir, profile_dir, output_dir


# ── Middleware ────────────────────────────────────────────────────────────────
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        REQUESTS_TOTAL.labels(endpoint=request.url.path, status=str(response.status_code)).inc()
        return response
    except Exception:
        REQUESTS_TOTAL.labels(endpoint=request.url.path, status="500").inc()
        raise


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", app=APP_NAME, version=APP_VERSION)


@app.get("/ready")
async def ready() -> JSONResponse:
    soffice_path = shutil.which("soffice")
    if _shutdown or not soffice_path:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "soffice": bool(soffice_path)},
        )
    return JSONResponse(content={"status": "ready", "soffice": soffice_path})


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.post("/convert")
async def convert(
    file: UploadFile = File(..., description="Office document to convert"),
    format: str = Form("pdf"),
    validate_output: bool = Form(True),
) -> FileResponse:
    if _shutdown:
        raise HTTPException(status_code=503, detail="Service is shutting down")
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    safe_name = _sanitize_filename(file.filename)
    input_ext = _get_extension(safe_name)

    if not _allowed_file(safe_name):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {safe_name}")
    if format.lower().strip() not in ALLOWED_OUTPUT_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported output format: {format}")

    request_id = uuid.uuid4().hex
    request_dir, profile_dir, output_dir = _prepare_request_dirs(request_id)
    input_path = request_dir / safe_name
    started = time.perf_counter()
    ACTIVE_CONVERSIONS.inc()

    try:
        contents = await _read_upload_with_limit(file, MAX_FILE_SIZE_BYTES)
        sha256 = _compute_sha256(contents)
        input_path.write_bytes(contents)

        cmd = _build_soffice_cmd(input_path, profile_dir, output_dir, input_ext)
        _json_log("conversion_started", request_id=request_id, filename=safe_name,
                  input_ext=input_ext, sha256=sha256)

        result = await asyncio.to_thread(_run_soffice, cmd, LIBREOFFICE_TIMEOUT_SECONDS)
        duration = time.perf_counter() - started
        CONVERSION_DURATION.labels(input_ext=input_ext).observe(duration)

        if result.returncode != 0:
            CONVERSIONS_TOTAL.labels(input_ext=input_ext, status="failed").inc()
            _json_log("conversion_failed", request_id=request_id, filename=safe_name,
                      stderr=result.stderr[-2000:], returncode=result.returncode,
                      duration_seconds=round(duration, 3))
            raise HTTPException(status_code=500, detail={
                "error": "Conversion failed",
                "request_id": request_id,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            })

        output_path = _find_generated_pdf(output_dir, safe_name)
        if not output_path or not output_path.exists():
            CONVERSIONS_TOTAL.labels(input_ext=input_ext, status="failed").inc()
            raise HTTPException(status_code=500, detail={
                "error": "No PDF produced after conversion",
                "request_id": request_id,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            })

        if output_path.stat().st_size == 0:
            CONVERSIONS_TOTAL.labels(input_ext=input_ext, status="failed").inc()
            raise HTTPException(status_code=500, detail={
                "error": "Produced PDF is empty",
                "request_id": request_id,
            })

        quality: ConversionQuality | None = None
        if validate_output and ENABLE_PDF_VALIDATION:
            preview, quality = _extract_text_and_quality(output_path)
            if (quality.pages or 0) == 0:
                CONVERSIONS_TOTAL.labels(input_ext=input_ext, status="failed").inc()
                raise HTTPException(status_code=500, detail={
                    "error": "Produced PDF has zero pages",
                    "request_id": request_id,
                })
            if LOG_PDF_TEXT_PREVIEW and preview:
                _json_log("pdf_text_preview", request_id=request_id, preview=preview)

        CONVERSIONS_TOTAL.labels(input_ext=input_ext, status="success").inc()
        _json_log("conversion_completed", request_id=request_id, filename=safe_name,
                  output_filename=output_path.name, duration_seconds=round(duration, 3),
                  output_size=output_path.stat().st_size,
                  quality=quality.model_dump() if quality else None)

        return FileResponse(
            path=output_path,
            media_type="application/pdf",
            filename=f"{Path(safe_name).stem}.pdf",
            background=BackgroundTask(_cleanup_paths, request_dir),
        )

    except HTTPException:
        _cleanup_paths(request_dir)
        raise
    except subprocess.TimeoutExpired:
        _cleanup_paths(request_dir)
        CONVERSIONS_TOTAL.labels(input_ext=input_ext, status="timeout").inc()
        raise HTTPException(status_code=504, detail={
            "error": "Conversion timed out",
            "timeout_seconds": LIBREOFFICE_TIMEOUT_SECONDS,
        })
    except Exception as exc:
        _cleanup_paths(request_dir)
        _json_log("conversion_unexpected_error", request_id=request_id, error=str(exc))
        raise
    finally:
        ACTIVE_CONVERSIONS.dec()


@app.post("/convert/debug")
async def convert_debug(
    file: UploadFile = File(...),
    format: str = Form("pdf"),
) -> JSONResponse:
    """Returns full diagnostics JSON without streaming the PDF. Use for troubleshooting only."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    safe_name = _sanitize_filename(file.filename)
    input_ext = _get_extension(safe_name)

    if not _allowed_file(safe_name):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {safe_name}")
    if format.lower().strip() != "pdf":
        raise HTTPException(status_code=400, detail="Only pdf output is supported")

    request_id = uuid.uuid4().hex
    request_dir, profile_dir, output_dir = _prepare_request_dirs(request_id)
    input_path = request_dir / safe_name
    started = time.perf_counter()

    try:
        contents = await _read_upload_with_limit(file, MAX_FILE_SIZE_BYTES)
        sha256 = _compute_sha256(contents)
        input_path.write_bytes(contents)

        cmd = _build_soffice_cmd(input_path, profile_dir, output_dir, input_ext)
        result = await asyncio.to_thread(_run_soffice, cmd, LIBREOFFICE_TIMEOUT_SECONDS)
        duration = round(time.perf_counter() - started, 3)  # FIX: was missing `started`

        output_path = _find_generated_pdf(output_dir, safe_name)
        _, quality = (
            _extract_text_and_quality(output_path)
            if output_path and output_path.exists()
            else (None, None)
        )

        return JSONResponse(content=ConversionDiagnostics(
            request_id=request_id,
            input_filename=safe_name,
            input_ext=input_ext,
            sha256=sha256,
            libreoffice_cmd=cmd,
            stdout=result.stdout[-4000:] if result.stdout else None,
            stderr=result.stderr[-4000:] if result.stderr else None,
            duration_seconds=duration,
            output_filename=output_path.name if output_path and output_path.exists() else None,
            quality=quality,
        ).model_dump())
    finally:
        _cleanup_paths(request_dir)


# ── Signal handlers ───────────────────────────────────────────────────────────
# Each uvicorn worker process installs its own handlers — _shutdown is process-local,
# which is correct: each worker independently stops accepting new work on SIGTERM/SIGINT.
def _install_signal_handlers() -> None:
    def _handle_signal(signum: int, _frame: Any) -> None:
        global _shutdown
        _shutdown = True
        _json_log("signal_received", signal=signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_signal)


_install_signal_handlers()

