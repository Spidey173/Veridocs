.PHONY: help test unit eval clean

PYTHON ?= $(shell which python3)
VENV_PYTHON = .venv/bin/python
PYTEST_CMD = $(if $(wildcard $(VENV_PYTHON)),VIRTUAL_ENV=.venv PYTHONPATH=.venv/lib/python3.11/site-packages:backend:. /opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest,$(PYTHON) -m pytest)

EVAL_RUNS ?= 5
EVAL_THRESHOLD ?= 0.75

help:
	@echo "Veridocs Developer & Evaluation Targets:"
	@echo "  make test      - Run fast unit tests (tests/unit/)"
	@echo "  make eval      - Run live LLM evaluation harness (tests/evals/)"
	@echo "                   Options: EVAL_RUNS=5 EVAL_THRESHOLD=0.75"
	@echo "  make clean     - Clean temporary test artifacts and pytest caches"

test:
	$(PYTEST_CMD) backend/tests/unit

unit: test

eval:
	EVAL_RUNS=$(EVAL_RUNS) EVAL_THRESHOLD=$(EVAL_THRESHOLD) $(PYTEST_CMD) -m live_eval backend/tests/evals

clean:
	rm -rf .pytest_cache backend/.pytest_cache backend/tests/.pytest_cache backend/tests/unit/.pytest_cache backend/tests/evals/.pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
