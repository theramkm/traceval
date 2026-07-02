# Contributing to traceval

## Setup

```bash
git clone https://github.com/theramkm/traceval.git
cd traceval
uv sync          # installs the package and dev dependencies (same as CI)
```

## Development loop

```bash
make test        # pytest -q
make lint        # ruff check, ruff format --check, mypy
make demo        # end-to-end smoke: healthy agent passes, buggy agent fails
make all         # lint + test
```

CI runs the same commands on Python 3.11, 3.12, and 3.13, plus a
wheel-based demo smoke job, and enforces 85% coverage. Keep all of it
green; add a test for every behavior change.
