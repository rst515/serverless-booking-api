#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC2059
purple () {  printf "\033[0;35m$1\033[0m\n"; }

purple "Validate SAM template..."
uv run sam validate --lint

purple "Checking code quality with Ruff..."
uv run ruff check .

purple "Running static type checks with mypy..."
uv run mypy .

purple "Running security checks with bandit..."
uv run bandit -rq src -x tests,.venv

purple "Running unit tests with pytest..."
uv run pytest

purple "Running pre-commit checks complete."