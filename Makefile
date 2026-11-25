.PHONY: lint format test build clean

lint:
	ruff check backend scripts evals
	ruff format --check backend scripts evals
	mypy backend
	npm run lint
	npx tsc --noEmit

format:
	ruff format backend scripts evals

test:
	.venv/bin/python -m pytest backend/tests/ -v
	npm run test:frontend

build:
	npm run build

clean:
	find backend/uploads -mindepth 1 ! -name '.gitkeep' -delete
	find backend/data -mindepth 1 ! -name '.gitkeep' -delete
