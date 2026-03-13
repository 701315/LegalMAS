FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libreoffice \
        fonts-dejavu \
        fonts-liberation \
        locales && \
    rm -rf /var/lib/apt/lists/*

RUN sed -i 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen
ENV LANG=ru_RU.UTF-8 \
    LC_ALL=ru_RU.UTF-8

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
