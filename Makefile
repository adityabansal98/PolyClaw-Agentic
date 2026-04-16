.PHONY: dev test lint

dev:
	docker compose up --build

test:
	uv run pytest -v

lint:
	uv run ruff check src tests && uv run ruff format --check src tests
