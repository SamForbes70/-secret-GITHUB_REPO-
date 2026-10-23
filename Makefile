PYTHON ?= $(shell command -v /opt/venv/bin/python 2>/dev/null || command -v python3 || command -v python)
HOST ?= 127.0.0.1
PORT ?= 8080

.PHONY: lint test test-cov run

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m mypy src/maps4u/core src/maps4u/geo

test:
	MAPS4U_QUEUE=inline $(PYTHON) -m pytest -m "not live"

test-cov:
	MAPS4U_QUEUE=inline $(PYTHON) -m pytest -m "not live" --cov=src/maps4u --cov-report=term-missing

run:
	$(PYTHON) -m uvicorn maps4u.api.main:create_app --factory --host $(HOST) --port $(PORT)
