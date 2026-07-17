FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    HOME=/home/appuser \
    XDG_CACHE_HOME=/home/appuser/.cache \
    XDG_CONFIG_HOME=/home/appuser/.config \
    XDG_DATA_HOME=/home/appuser/.local/share \
    HF_HOME=/home/appuser/.cache/huggingface \
    TORCH_HOME=/home/appuser/.cache/torch

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gcc \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-rus \
    tesseract-ocr-deu \
    tesseract-ocr-fra \
    tesseract-ocr-tur \
    tesseract-ocr-ara \
    && rm -rf /var/lib/apt/lists/*

# Создаём отдельного непривилегированного пользователя для runtime.
# Дополнительно заранее подготавливаем writable directories для кэшей.
RUN groupadd --system app && \
    useradd --system --create-home --gid app --home-dir /home/appuser --shell /usr/sbin/nologin appuser && \
    install -d -o appuser -g app /app && \
    install -d -o appuser -g app /app/.cache && \
    install -d -o appuser -g app /home/appuser/.cache && \
    install -d -o appuser -g app /home/appuser/.config && \
    install -d -o appuser -g app /home/appuser/.local/share && \
    install -d -o appuser -g app /home/appuser/.cache/huggingface && \
    install -d -o appuser -g app /home/appuser/.cache/torch

COPY --chown=appuser:app requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY --chown=appuser:app . /app

USER appuser

EXPOSE 8000


