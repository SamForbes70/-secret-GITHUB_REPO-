.PHONY: lint test test-cov run

lint:
/opt/venv/bin/ruff check src tests
/opt/venv/bin/mypy src/maps4u/core src/maps4u/geo

test:
MAPS4U_QUEUE=inline /opt/venv/bin/pytest -m "not live"

test-cov:
MAPS4U_QUEUE=inline /opt/venv/bin/pytest -m "not live" --cov=src/maps4u --cov-report=term-missing

run:
/opt/venv/bin/uvicorn maps4u.api.main:app --host 127.0.0.1 --port 8080
