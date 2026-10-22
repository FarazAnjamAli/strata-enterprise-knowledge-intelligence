.PHONY: setup up up-llm down logs test lint build

setup:      ## create .env with generated secrets
	./scripts/setup.sh
up:         ## start the stack (bring your own Ollama)
	docker compose up -d --build
up-llm:     ## start the stack plus a containerised Ollama
	docker compose --profile local-llm up -d --build
down:
	docker compose down
logs:
	docker compose logs -f api worker web
test:
	cd backend && pytest
lint:
	cd backend && ruff check . && ruff format --check .
	cd frontend && npm run lint && npm run typecheck
build:
	cd frontend && npm run build
