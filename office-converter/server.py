# office-converter/server.py

import os
import uuid
import subprocess
import glob
from typing import Annotated

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

import logging

logger = logging.getLogger("office-converter")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Office → PDF Converter", debug=True)

# Разрешённые расширения входных файлов
ALLOWED_EXTENSIONS = {
    "docx", "doc",
    "xlsx", "xls",
    "pptx", "ppt",
    "odt", "ods", "odp",
    "rtf", "csv", "html",
}

# Поддерживаемый формат вывода (сейчас только PDF)
DEFAULT_OUTPUT_FORMAT = "pdf"

# Базовая директория для временных файлов внутри контейнера
BASE_TMP_DIR = "/tmp/office-converter"


def _allowed_file(filename: str) -> bool:
    """Проверяем, что расширение файла входит в список разрешённых."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.get("/health")
async def health():
    """Простой health-check endpoint."""
    return {"status": "ok"}


@app.post("/convert")
async def convert(
    file: Annotated[UploadFile, File(..., description="Office document to convert")],
    format: str = Form(DEFAULT_OUTPUT_FORMAT),
):
    """
    Принимает офисный документ, конвертирует его в PDF через LibreOffice
    и возвращает готовый PDF-файл.
    """

    target_format = format.lower()

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not _allowed_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.filename}",
        )

    if target_format != "pdf":
        raise HTTPException(
            status_code=400,
            detail=f"Only pdf output is supported, got: {target_format}",
        )

    # Готовим базовую временную директорию (общую для всех запросов)
    os.makedirs(BASE_TMP_DIR, exist_ok=True)

    # Уникальный идентификатор для этого запроса (чтобы не пересекаться с другими)
    request_id = uuid.uuid4().hex

    # Имя входного файла: <request_id>_input.<ext>
    ext = os.path.splitext(file.filename or "")[1].lower() or ".doc"
    input_path = os.path.join(BASE_TMP_DIR, f"{request_id}_input{ext}")

    # Читаем загруженный файл полностью и сохраняем на диск
    contents = await file.read()
    with open(input_path, "wb") as f:
        f.write(contents)

    # Команда для LibreOffice
    cmd = [
        "soffice",
        "--headless",
        "--norestore",
        "--convert-to",
        "pdf",
        "--outdir",
        BASE_TMP_DIR,
        input_path,
    ]

    # Запускаем LibreOffice и ждём завершения
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        logger.error(
            "LibreOffice conversion failed",
            extra={
                "stderr": result.stderr,
                "stdout": result.stdout,
                "cmd": " ".join(cmd),
            },
        )
        # Убираем входной файл в случае ошибки
        try:
            os.remove(input_path)
        except FileNotFoundError:
            pass

        raise HTTPException(
            status_code=500,
            detail={
                "error": "Conversion failed",
                "stderr": result.stderr,
                "stdout": result.stdout,
            },
        )

    # Ищем PDF, созданный LibreOffice для этого запроса
    pdf_pattern = os.path.join(BASE_TMP_DIR, f"{request_id}_*.pdf")
    pdf_candidates = glob.glob(pdf_pattern)

    # Если LibreOffice переименовал файл (например, исходное имя),
    # можно ослабить фильтр до "* .pdf", но тогда сложнее однозначно
    # сопоставить файл конкретному запросу при высокой нагрузке.
    if not pdf_candidates:
        # fallback: пробуем искать любой PDF, основанный на оригинальном имени
        original_base = os.path.splitext(os.path.basename(file.filename))[0]
        fallback_pattern = os.path.join(BASE_TMP_DIR, f"{original_base}*.pdf")
        pdf_candidates = glob.glob(fallback_pattern)

    if not pdf_candidates:
        logger.error(
            "No PDF produced after conversion",
            extra={
                "tmpdir": BASE_TMP_DIR,
                "stderr": result.stderr,
                "stdout": result.stdout,
            },
        )
        try:
            os.remove(input_path)
        except FileNotFoundError:
            pass

        raise HTTPException(
            status_code=500,
            detail={
                "error": "No PDF produced after conversion",
                "stderr": result.stderr,
                "stdout": result.stdout,
            },
        )

    output_path = pdf_candidates[0]
    base_name = os.path.splitext(os.path.basename(output_path))[0]

    # Функция для очистки временных файлов после отправки ответа
    def _cleanup_files():
        for path in (input_path, output_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except Exception as exc:  # логируем, но не падаем
                logger.warning(
                    "Failed to remove temporary file",
                    extra={"path": path, "error": str(exc)},
                )

    # Планируем очистку как фоновую задачу
    background_task = BackgroundTask(_cleanup_files)

    # Возвращаем PDF-файл; FileResponse сам прочитает его по пути
    # уже после того, как мы вернём ответ из функции.
    return FileResponse(
        path=output_path,
        media_type="application/pdf",
        filename=f"{base_name}.pdf",
        background=background_task,
    )
