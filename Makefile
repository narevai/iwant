PYTHON ?= $(shell command -v python)
UV ?= uv

.DEFAULT_GOAL := check
.PHONY: install check lint format-check format test release

install:
	$(UV) pip install --system --python "$(PYTHON)" -e '.[dev]'

check: lint format-check test

lint:
	"$(PYTHON)" -m ruff check .
	"$(PYTHON)" -m basedpyright --pythonpath "$(PYTHON)"

format-check:
	"$(PYTHON)" -m ruff format --check .

format:
	"$(PYTHON)" -m ruff format .

test:
	"$(PYTHON)" -m pytest -v

release: check
	@test "$${GITHUB_REF:-refs/heads/$$(git branch --show-current)}" = refs/heads/main || \
		{ echo "Releases must run from main." >&2; exit 1; }
	@test -z "$$(git status --porcelain)" || \
		{ echo "Commit or stash local changes before releasing." >&2; exit 1; }
	@set -eu; \
	version=$$($(UV) version --short); \
	printf '%s\n' "$$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$'; \
	if git ls-remote --exit-code --tags origin "refs/tags/v$$version"; then \
		echo "Tag v$$version already exists. Bump project.version before releasing." >&2; exit 1; \
	else \
		status=$$?; if [ "$$status" -ne 2 ]; then exit "$$status"; fi; \
	fi; \
	release_dir=$$(mktemp -d); \
	trap 'rm -rf "$$release_dir"' EXIT; \
	sed "s/^RELEASE_TAG=\"\"$$/RELEASE_TAG=\"v$$version\"/" install.sh > "$$release_dir/install.sh"; \
	grep -Fxq "RELEASE_TAG=\"v$$version\"" "$$release_dir/install.sh"; \
	bash -n "$$release_dir/install.sh"; \
	bash "$$release_dir/install.sh" --help; \
	gh release create "v$$version" "$$release_dir/install.sh" \
		--target "$$(git rev-parse HEAD)" --title "iwant $$version" --generate-notes --latest
