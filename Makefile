.PHONY: install check check-backend check-frontend format dev-backend dev-frontend db-up test-db-up migrate seed-reference

install:
	cd backend && poetry install --extras dev
	cd frontend && npm ci

check: check-backend check-frontend

check-backend:
	cd backend && poetry run ruff check .
	cd backend && poetry run ruff format --check .
	cd backend && poetry run mypy app scripts tests alembic
	cd backend && poetry run pytest

check-frontend:
	cd frontend && npm run lint
	cd frontend && npm run format:check
	cd frontend && npm run typecheck
	cd frontend && npm run test
	cd frontend && npm run build

format:
	cd backend && poetry run ruff check --fix .
	cd backend && poetry run ruff format .
	cd frontend && npm run format

dev-backend:
	cd backend && poetry run uvicorn app.main:app --reload

dev-frontend:
	cd frontend && npm run dev

db-up:
	docker compose up -d --wait mysql

test-db-up:
	docker compose --profile test up -d --wait mysql-test

migrate:
	cd backend && poetry run alembic upgrade head

seed-reference:
	cd backend && poetry run python -m scripts.seed_reference_data
