.PHONY: test lint demo demo-gif all

test:
	uv run pytest -q

lint:
	uv run ruff check src tests examples
	uv run ruff format --check src tests examples
	uv run mypy src/traceval

demo:
	uv run traceval demo -o /tmp/traceval-demo --force

all: lint test

demo-gif:
	@command -v vhs >/dev/null || { echo "vhs not found; install it with: brew install vhs"; exit 1; }
	vhs docs/demo.tape
