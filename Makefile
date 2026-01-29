.PHONY: install lint format test run clean help

# Default target
help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies with Poetry"
	@echo "  make lint       - Run ruff and mypy"
	@echo "  make format     - Format code with black and ruff"
	@echo "  make test       - Run pytest with coverage"
	@echo "  make run        - Start the API server"
	@echo "  make clean      - Remove cache and build artifacts"

install:
	poetry install

lint:
	poetry run ruff check src tests
	poetry run mypy src

format:
	poetry run black src tests
	poetry run ruff check --fix src tests

test:
	poetry run pytest

run:
	poetry run uvicorn orchestrator.api.app:app --reload --host 0.0.0.0 --port 8000

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__ .coverage htmlcov
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
