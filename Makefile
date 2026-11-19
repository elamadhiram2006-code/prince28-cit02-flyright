
.PHONY: up down logs ps build test test-integration cov lint migrate seed

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

build:
	docker compose build

test:
	uv run poe test

test-integration:
	uv run poe test-integration

cov:
	uv run poe cov

lint:
	uv run poe lint

migrate:
	uv run poe migrate

seed:
	uv run poe seed
