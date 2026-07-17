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
    HOME=/home/appuser \
    XDG_CACHE_HOME=/home/appuser/.cache \
    XDG_CONFIG_HOME=/home/appuser/.config \
    XDG_DATA_HOME=/home/appuser/.local/share \
    CONVERTER_TMP_DIR=/tmp/office-converter \
    LIBREOFFICE_TIMEOUT_SECONDS=180 \
    MAX_FILE_SIZE_BYTES=104857600 \
    ENABLE_PDF_VALIDATION=true \
    LOG_PDF_TEXT_PREVIEW=false \
    LOG_LEVEL=INFO

# ── Pre-create tmp dir with correct permissions ──────────────────────────────
RUN mkdir -p /tmp/office-converter && chmod 1777 /tmp/office-converter

# ── Non-root runtime user ────────────────────────────────────────────────────
# LibreOffice и uvicorn не должны работать от root.
# HOME/.config и HOME/.cache заранее подготавливаем для runtime profile/cache.
RUN groupadd --system app && \
    useradd --system --create-home --gid app --home-dir /home/appuser --shell /usr/sbin/nologin appuser && \
    install -d -o appuser -g app /app && \
    install -d -o appuser -g app /home/appuser/.cache && \
    install -d -o appuser -g app /home/appuser/.config && \
    install -d -o appuser -g app /home/appuser/.local/share

WORKDIR /app

COPY --chown=appuser:app requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY --chown=appuser:app server.py /app/server.py

USER appuser

EXPOSE 8080

# Use multiple workers to handle concurrent conversions
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2", "--timeout-keep-alive", "30"]

