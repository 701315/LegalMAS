FROM python:3.11-slim

# ── System deps + LibreOffice + multilingual fonts ──────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libreoffice \
        fonts-dejavu \
        fonts-liberation \
        fonts-noto-core \
        fonts-noto-cjk \
        fonts-noto-extra \
        fonts-noto-color-emoji \
        fonts-freefont-ttf \
        fonts-unifont \
        locales \
        poppler-utils \
        curl && \
    rm -rf /var/lib/apt/lists/*

# ── Locales: keep C.UTF-8 as primary, add ru/en/zh/ar for LibreOffice ───────
RUN sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    sed -i 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen && \
    sed -i 's/# zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/' /etc/locale.gen && \
    sed -i 's/# ar_SA.UTF-8 UTF-8/ar_SA.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CONVERTER_TMP_DIR=/tmp/office-converter \
    LIBREOFFICE_TIMEOUT_SECONDS=180 \
    MAX_FILE_SIZE_BYTES=104857600 \
    ENABLE_PDF_VALIDATION=true \
    LOG_PDF_TEXT_PREVIEW=false \
    LOG_LEVEL=INFO

# ── Pre-create tmp dir with correct permissions ──────────────────────────────
RUN mkdir -p /tmp/office-converter && chmod 1777 /tmp/office-converter

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

EXPOSE 8080

# Use multiple workers to handle concurrent conversions
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", \
     "--workers", "2", "--timeout-keep-alive", "30"]
