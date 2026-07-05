.PHONY: \
	up down restart logs test lint format migrate seed clean \
	monitoring-up monitoring-down monitoring-logs \
	ollama-check ollama-warm \
	worker worker-dev worker-system worker-heavy worker-heavy-enrichment worker-heavy-segment-classification worker-heavy-checks beat dev-help \
	test-pii test-pii-unit test-pii-integration pii-keygen pii-smoke


# ============================================================================
# Базовые настройки
# ============================================================================

PYTHONPATH_ENV = PYTHONPATH=src
CELERY_APP = mas_queue.celery_app:celery_app

# Имена контейнеров должны совпадать с docker-compose.yml
POSTGRES_CONTAINER = mas_dd_postgres
REDIS_CONTAINER = mas_dd_redis

# Пользователь/БД должны совпадать с docker-compose.yml
POSTGRES_USER = mas
POSTGRES_DB = mas_dd


# ============================================================================
# Ожидание сервисов
# ============================================================================

ifeq ($(OS),Windows_NT)
	SLEEP = powershell -Command "Start-Sleep -s"
	WAIT_PG = $(SLEEP) 15
	WAIT_REDIS = $(SLEEP) 3
else
	SLEEP = sleep
	WAIT_PG = until docker exec $(POSTGRES_CONTAINER) pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB) > /dev/null 2>&1; do \
		echo "PostgreSQL is starting up, waiting..."; \
		sleep 2; \
	done
	WAIT_REDIS = until docker exec $(REDIS_CONTAINER) redis-cli ping > /dev/null 2>&1; do \
		echo "Redis is starting up, waiting..."; \
		sleep 1; \
	done
endif


# ============================================================================
# Инфраструктура и API
# ============================================================================

# ---------------------------------------------------------------------------
# Observability stack (Tempo, Prometheus, Loki, Grafana, Alertmanager)
# Простым языком: система "видимости" — метрики, логи, трейсы.
# Без неё OTEL export падает с ConnectionRefused, dashboard пустой.
# ---------------------------------------------------------------------------
monitoring-up:
	@echo "Starting observability stack..."
	docker compose --env-file .env.monitoring -f docker-compose.monitoring.yml up -d
	@echo "Waiting for monitoring stack to warm up..."
	@sleep 10
	@echo "Monitoring stack status:"
	@docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "tempo|prometheus|grafana|loki|alertmanager" || echo "Warning: some monitoring containers may not be running"

monitoring-down:
	docker compose --env-file .env.monitoring -f docker-compose.monitoring.yml down

monitoring-logs:
	docker compose --env-file .env.monitoring -f docker-compose.monitoring.yml logs -f --tail=20

# Поднять инфраструктурные сервисы, observability и API
up: monitoring-up
	docker compose up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@$(WAIT_PG)
	@echo "Waiting for Redis to be ready..."
	@$(WAIT_REDIS)
	@echo "Services are up. PostgreSQL: localhost:5432, Redis: localhost:6379, MinIO: localhost:9000 (console: localhost:9001)"
	@echo "Monitoring: Grafana http://localhost:3000, Prometheus http://localhost:9090"
	$(PYTHONPATH_ENV) uvicorn api.main:app --reload --port 8000

# Остановить все docker-сервисы (включая observability)
down:
	docker compose down
	docker compose --env-file .env.monitoring -f docker-compose.monitoring.yml down

# Перезапустить docker-сервисы
restart: down up

# Показать логи docker-сервисов (основные)
logs:
	docker compose logs -f

# Удалить Docker volumes (осторожно: удалит все данные)
clean:
	docker compose down -v
	@echo "All volumes removed"


# ============================================================================
# Celery процессы
# ============================================================================

# Основной worker:
# слушает основной pipeline + импорт/конвертацию + low priority задачи
worker:
	$(PYTHONPATH_ENV) celery -A $(CELERY_APP) worker \
		--loglevel=info \
		--queues=default,high_priority,low_priority \
		--pool=solo

# Dev-версия основного worker с тестовыми задачами
worker-dev:
	$(PYTHONPATH_ENV) celery -A $(CELERY_APP) worker \
		--loglevel=info \
		--queues=default,high_priority,low_priority \
		--include=tests.tasks_for_testing \
		--pool=solo

# Отдельный system worker для инфраструктурных задач:
# outbox_dispatcher, reap_stale_stage_executions.
#
# OTEL_ENABLED=false — намеренно.
# Причина: system worker выполняет только служебные задачи без бизнес-ценности
# для трейсинга. SQLAlchemy и connection pool events от этого worker'а
# создают orphan spans в Tempo, засоряя бизнес-traces.
# Логи и метрики работают нормально — только traces отключены.
worker-system:
	OTEL_ENABLED=false $(PYTHONPATH_ENV) celery -A $(CELERY_APP) worker \
		--loglevel=INFO \
		--hostname=worker-system@%h \
		--queues=system \
		--pool=solo

worker-heavy-enrichment:
	$(PYTHONPATH_ENV) celery -A $(CELERY_APP) worker \
		--loglevel=info \
		--queues=heavy_llm_enrichment \
		--pool=solo \
		--concurrency=1

# Отдельный worker для segment-level classification.
# Изолирован от enrichment чтобы исключить head-of-line blocking:
# долгая segment classification не блокирует enrichment pipeline.
worker-heavy-segment-classification:
	$(PYTHONPATH_ENV) celery -A $(CELERY_APP) worker \
		--loglevel=info \
		--queues=heavy_llm_segment_classification \
		--pool=solo \
		--concurrency=1

# Отдельный worker для single-check heavy LLM задач.
# Тот же принцип: solo вместо prefork для стабильности native runtime.
worker-heavy-checks:
	$(PYTHONPATH_ENV) celery -A $(CELERY_APP) worker \
		--loglevel=info \
		--queues=heavy_llm_checks \
		--pool=solo \
		--concurrency=1


# Проверить доступность Ollama и список загруженных моделей
ollama-check:
	@curl -sf http://localhost:11434/api/tags | python3 -m json.tool 2>/dev/null \
		|| echo "Ollama is not running. Start it with: ollama serve"

# Прогреть модель (первый вызов загружает GGUF в память Ollama)
ollama-warm:
	@echo "Warming up Ollama model..."
	@curl -sf http://localhost:11434/api/generate \
		-d '{"model":"qwen25-legal","prompt":"test","stream":false,"options":{"num_predict":1}}' \
		> /dev/null 2>&1 \
		&& echo "Model is warm and ready." \
		|| echo "Failed. Is Ollama running and model created?"

# Удобная подсказка: исторически в dev-help фигурировал worker-heavy,
# теперь есть два отдельных target'а.
worker-heavy:
	@echo ""
	@echo "Heavy workers разделены на два target'а:"
	@echo "  make worker-heavy-segment-classification — segment-level classification LLM задачи"
	@echo "  make worker-heavy-enrichment             — semantic enrichment LLM задачи"
	@echo "  make worker-heavy-checks                 — single-check LLM задачи"
	@echo ""

# Celery Beat:
# нужен, чтобы периодически запускать workers.outbox_dispatcher
beat:
	$(PYTHONPATH_ENV) celery -A $(CELERY_APP) beat \
		--loglevel=info

# Подсказка для локальной разработки
dev-help:
	@echo ""
	@echo "Для полного локального pipeline (Ollama sidecar mode):"
	@echo "  0) ollama serve              — запустить Ollama (отдельный терминал)"
	@echo "  0a) make ollama-warm         — прогреть модель (первый раз)"
	@echo "  1) make up"
	@echo "  2) make worker"
	@echo "  3) make worker-system"
	@echo "  4) make beat"
	@echo "  5) make worker-heavy-segment-classification"
	@echo "  6) make worker-heavy-enrichment"
	@echo "  7) make worker-heavy-checks"
	@echo ""
	@echo "Первоначальная настройка Ollama (один раз на машине):"
	@echo "  curl -fsSL https://ollama.com/install.sh | sh"
	@echo "  ollama create qwen25-legal -f /tmp/Qwen25LegalModelfile"
	@echo "  make ollama-check"
	@echo ""
	@echo "Rollback к llamacpp: установить LLM_PROVIDER=llamacpp в .env"
	@echo ""


# ============================================================================
# Тесты и утилиты
# ============================================================================

test:
	python -m pytest tests/ -v --tb=short

test-unit:
	python -m pytest tests/unit/ -v --tb=short

test-integration:
	python -m pytest tests/integration/ -v --tb=short

lint:
	python -m ruff check src/ tests/
	python -m ruff format --check src/ tests/

format:
	python -m ruff format src/ tests/
	python -m ruff check --fix src/ tests/

migrate:
	alembic upgrade head

seed:
	python -m scripts.seed


# ============================================================================
# PII Sanitizer
# ============================================================================

test-pii:
	pytest tests/unit/test_pii_sanitizer.py -v --tb=short
	@if [ -f tests/integration/test_pii_integration.py ]; then \
		pytest tests/integration/test_pii_integration.py -v --tb=short; \
	fi

test-pii-unit:
	pytest tests/unit/test_pii_sanitizer.py -v

test-pii-integration:
	@if [ -f tests/integration/test_pii_integration.py ]; then \
		pytest tests/integration/test_pii_integration.py -v; \
	else \
		echo "Integration tests not yet implemented"; \
	fi

pii-keygen:
	python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

pii-smoke:
	python3 -c "\
from services.pii_detector import PIIDetector; \
from services.pii_tokenizer import PIITokenizer, PIIPolicy; \
d = PIIDetector(ner_enabled=False); \
t = PIITokenizer(); \
text = 'Продавец Сидоров, тел. +7 912 345-67-89, ИНН 7707083893.'; \
entities = d.detect(text); \
print('Detected:', [e.text for e in entities]); \
policy = PIIPolicy(use_role_map=True); \
result = t.tokenize(text, entities, policy, context_window=text[:100]); \
print('Sanitized:', result.sanitized_text); \
print('Mapping:', result.mapping); \
print('Stats:', result.entities_tokenized, result.entities_role_mapped)"


