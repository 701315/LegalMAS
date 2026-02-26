.PHONY: up down restart logs test lint format migrate seed clean

# Определяем команду sleep в зависимости от ОС
ifeq ($(OS),Windows_NT)
    SLEEP = powershell -Command "Start-Sleep -s"
else
    SLEEP = sleep
endif

# Поднять все сервисы (PostgreSQL, Redis, MinIO)
up:
	docker compose up -d
	@echo "Waiting for services to be ready..."
	@$(SLEEP) 3
	@echo "Services are up. PostgreSQL: localhost:5432, Redis: localhost:6379, MinIO: localhost:9000 (console: localhost:9001)"

# Остановить все сервисы
down:
	docker compose down

# Перезапустить сервисы
restart: down up

# Показать логи сервисов
logs:
	docker compose logs -f

# Запустить все тесты
test:
	python -m pytest tests/ -v --tb=short

# Запустить только unit-тесты
test-unit:
	python -m pytest tests/unit/ -v --tb=short

# Запустить только интеграционные тесты
test-integration:
	python -m pytest tests/integration/ -v --tb=short

# Проверить код линтером
lint:
	python -m ruff check src/ tests/
	python -m ruff format --check src/ tests/

# Автоформатирование кода
format:
	python -m ruff format src/ tests/
	python -m ruff check --fix src/ tests/

# Запустить миграции базы данных
migrate:
	alembic upgrade head

# Заполнить базу тестовыми данными
seed:
	python -m scripts.seed

# Удалить Docker volumes (осторожно: удалит все данные!)
clean:
	docker compose down -v
	@echo "All volumes removed"

# Запустить production воркер
worker:
	celery -A src.queue.celery_app:celery_app worker --loglevel=info --queues=default,high_priority,low_priority --pool=solo

# Запустить воркер с тестовыми задачами (разработка)
worker-dev:
	celery -A src.queue.celery_app:celery_app worker --loglevel=info --queues=default,high_priority,low_priority --include=tests.tasks_for_testing --pool=solo

# ═══════════════════════════════════════════════════════════════════════════════
# PII Sanitizer (Stage 5)
# ═══════════════════════════════════════════════════════════════════════════════

.PHONY: test-pii
test-pii:  ## Run PII Sanitizer tests (unit + integration if exists)
	pytest tests/unit/test_pii_sanitizer.py -v --tb=short
	@if [ -f tests/integration/test_pii_integration.py ]; then \
		pytest tests/integration/test_pii_integration.py -v --tb=short; \
	fi

.PHONY: test-pii-unit
test-pii-unit:  ## Run PII unit tests only
	pytest tests/unit/test_pii_sanitizer.py -v

.PHONY: test-pii-integration
test-pii-integration:  ## Run PII integration tests only
	@if [ -f tests/integration/test_pii_integration.py ]; then \
		pytest tests/integration/test_pii_integration.py -v; \
	else \
		echo "Integration tests not yet implemented"; \
	fi

.PHONY: pii-keygen
pii-keygen:  ## Generate a new Fernet key for PII_ENCRYPTION_KEY
	python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

.PHONY: pii-smoke
pii-smoke:  ## Quick smoke test of PII detector/tokenizer
	python3 -c "\
from src.services.pii_detector import PIIDetector; \
from src.services.pii_tokenizer import PIITokenizer, PIIPolicy; \
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