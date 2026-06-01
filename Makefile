.PHONY: install run test lint clean format type-check help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -e .[dev]

run: ## Start the FastAPI server
	uvicorn app.main:app --host 0.0.0.0 --port 8920 --reload

test: ## Run tests with coverage
	pytest --cov=app --cov-report=term-missing --cov-report=html

lint: ## Run linting with ruff
	ruff check .

format: ## Format code with ruff
	ruff format .

type-check: ## Run type checking with mypy
	mypy app/

clean: ## Clean cache and temporary files
	rm -rf __pycache__ .pytest_cache .coverage htmlcov .mypy_cache
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
	rm -rf data/

dev: install ## Install and setup development environment
	mkdir -p data
	cp .env.example .env

check: lint type-check test ## Run all checks

build: format check ## Format, lint, type-check and test