.PHONY: test lint demo all

test:
	uv run pytest -q

lint:
	uv run ruff check src tests examples
	uv run ruff format --check src tests examples
	uv run mypy src/traceval

demo:
	uv run traceval demo -o /tmp/traceval-demo --force

all: lint test
