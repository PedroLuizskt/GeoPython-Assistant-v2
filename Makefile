# =============================================================================
# GeoPython Assistant v2 - Makefile
# =============================================================================

PYTHON ?= python
PIP    ?= pip
APP    := src/geopyassistant/ui/app.py

.PHONY: help install install-dev lint format type test test-fast cov run build-docs clean

help:
	@echo "Comandos disponiveis:"
	@echo "  make install        Instala dependencias de producao"
	@echo "  make install-dev    Instala dependencias de desenvolvimento"
	@echo "  make lint           Executa ruff para identificar problemas"
	@echo "  make format         Formata o codigo com black e ruff"
	@echo "  make type           Executa verificacao estatica com mypy"
	@echo "  make test           Executa toda a suite de testes"
	@echo "  make test-fast      Executa apenas testes unitarios"
	@echo "  make cov            Executa testes com relatorio de cobertura"
	@echo "  make run            Sobe a aplicacao Streamlit"
	@echo "  make build-docs     Constroi o indice vetorial da documentacao"
	@echo "  make clean          Remove caches e arquivos temporarios"

install:
	$(PIP) install --upgrade pip
	$(PIP) install -e .

install-dev:
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	pre-commit install

lint:
	ruff check src tests

format:
	black src tests
	ruff check --fix src tests

type:
	mypy src

test:
	pytest -v

test-fast:
	pytest -v tests/unit

cov:
	pytest --cov=src/geopyassistant --cov-report=term-missing --cov-report=html

run:
	streamlit run $(APP)

build-docs:
	$(PYTHON) scripts/build_docs_index.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .ipynb_checkpoints -exec rm -rf {} +
