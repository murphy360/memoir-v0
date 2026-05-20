SHELL := /bin/sh

.PHONY: lint lint-backend lint-frontend

lint: lint-backend lint-frontend

lint-backend:
	@echo "Running backend lint (Ruff)..."
	cd backend && ../.venv/Scripts/python -m ruff check app test_exif_gps.py
	@echo "Running backend advisory guardrails (Pylint size/length/complexity)..."
	cd backend && ../.venv/Scripts/python -m pylint --rcfile=.pylintrc --exit-zero app

lint-frontend:
	@echo "Running frontend lint (Next.js ESLint)..."
	cd frontend && npm run lint
