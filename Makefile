# Makefile per Guess the Player
# Compatibile con Linux, macOS, WSL e Windows con GNU make.
# Su Windows senza make e' possibile usare:
#   .\dev.ps1 <comando>
# oppure direttamente:
#   python -m tools.dev <comando>

PYTHON ?= python

.PHONY: help check-env check-api test test-cov test-node lint typecheck syntax dataset-check check api admin webapp emulator

help:
	@$(PYTHON) -m tools.dev --help

check-env:
	@$(PYTHON) -m tools.check_environment

check-api:
	@$(PYTHON) -m tools.check_environment --mode api

test:
	@$(PYTHON) -m pytest -q

test-cov:
	@$(PYTHON) -m pytest -q --cov=services --cov=handlers --cov-report=term-missing

test-node:
	node --test tests/client.test.cjs

lint:
	@$(PYTHON) -m ruff check .

typecheck:
	@$(PYTHON) -m mypy services/

syntax:
	@$(PYTHON) -m compileall -q bot.py config.py services handlers scripts admin_pages admin_ui.py tools

dataset-check:
	@$(PYTHON) scripts/dataset_report.py --strict

check:
	@$(PYTHON) -m tools.dev check

api:
	@$(PYTHON) -m tools.dev api

admin:
	@$(PYTHON) -m streamlit run admin_ui.py

webapp:
	@$(PYTHON) scripts/preview_webapp.py

emulator:
	gcloud emulators firestore start --host-port=127.0.0.1:8571
