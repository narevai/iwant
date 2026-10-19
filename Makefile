PYTHON ?= python
UV ?= uv

.DEFAULT_GOAL := check
.PHONY: install-dev check lint format-check format types test

install-dev:
	$(UV) pip install --python "$(PYTHON)" -e '.[dev]'

check: lint format-check types test

lint:
	"$(PYTHON)" -m ruff check .

format-check:
	"$(PYTHON)" -m ruff format --check .

format:
	"$(PYTHON)" -m ruff format .

types:
	"$(PYTHON)" -m basedpyright --pythonpath "$$("$(PYTHON)" -c 'import sys; print(sys.executable)')"

test:
	"$(PYTHON)" -m pytest -v
