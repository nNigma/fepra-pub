.PHONY: setup run test web

# One-command local setup: virtualenv + all dependencies.
setup:
	uv venv --python 3.12
	uv pip install -e '.[bot,dev]'

# Run the full local dev stack (Mini App + public tunnel + bot).
run:
	bash scripts/run-dev.sh

# Run the test suite.
test:
	PYTHONPATH=src .venv/bin/python -m pytest -p no:randomly -q

# Build the PWA (web/) into src/tjapp/static/app/ (build artifact, not committed).
web:
	cd web && npm ci && npm run build
