# office-converter/server.py

import os
import tempfile
import subprocess
from typing import Annotated
import glob

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse

import logging

logger = logging.getLogger("office-converter")
logging.basicConfig(level=logging.INFO)


app = FastAPI(title="Office → PDF Converter", debug=True)

ALLOWED_EXTENSIONS = {
    "docx", "doc",
    "xlsx", "xls",
    "pptx", "ppt",
    "odt", "ods", "odp",
    "rtf", "csv", "html",
}

DEFAULT_OUTPUT_FORMAT = "pdf"


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/convert")
async def convert(
    file: Annotated[UploadFile, File(..., description="Office document to convert")],
    format: str = Form(DEFAULT_OUTPUT_FORMAT),
):
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

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Пишем входной файл с контролируемым именем
            ext = os.path.splitext(file.filename or "")[1].lower() or ".doc"
            input_path = os.path.join(tmpdir, f"input{ext}")

            contents = await file.read()
            with open(input_path, "wb") as f:
                f.write(contents)

            # 2. Запускаем LibreOffice
            cmd = [
                "soffice",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                tmpdir,
                input_path,
            ]

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
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "Conversion failed",
                        "stderr": result.stderr,
                        "stdout": result.stdout,
                    },
                )

            # 3. Ищем фактический PDF в tmpdir
            pdf_candidates = glob.glob(os.path.join(tmpdir, "*.pdf"))
            if not pdf_candidates:
                logger.error(
                    "No PDF produced after conversion",
                    extra={
                        "tmpdir": tmpdir,
                        "stderr": result.stderr,
                        "stdout": result.stdout,
                    },
                )
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

            return FileResponse(
                path=output_path,
                media_type="application/pdf",
                filename=f"{base_name}.pdf",
            )

    finally:
        await file.close()
