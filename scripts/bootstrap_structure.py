"""
bootstrap_structure.py
======================
Cria a arvore de diretorios e arquivos stub do GeoPython Assistant v2
seguindo o padrao Cookiecutter Data Science adaptado para projetos
geoespaciais.

Funciona em Windows (PowerShell ou cmd), Linux e macOS, pois usa apenas
a biblioteca padrao do Python.

Uso:
    python scripts/bootstrap_structure.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Raiz do projeto: um nivel acima do diretorio que contem este script.
PROJECT_ROOT: Path = Path(__file__).parent.parent.resolve()

# ---------------------------------------------------------------------------
# Especificacao da arvore do projeto
# ---------------------------------------------------------------------------

DIRECTORIES: list[str] = [
    "data/raw",
    "data/interim",
    "data/processed",
    "data/external",
    "data/samples",
    "docs",
    "notebooks",
    "references",
    "reports/figures",
    "scripts",
    "src/geopyassistant/ingestion",
    "src/geopyassistant/diagnostics",
    "src/geopyassistant/rag",
    "src/geopyassistant/llm",
    "src/geopyassistant/codegen",
    "src/geopyassistant/ui",
    "tests/unit",
    "tests/integration",
    "tests/data",
]

EMPTY_FILES: list[str] = [
    # Marcadores para versionar diretorios vazios
    "data/raw/.gitkeep",
    "data/interim/.gitkeep",
    "data/processed/.gitkeep",
    "data/external/.gitkeep",
    "reports/figures/.gitkeep",
    "tests/data/.gitkeep",
    # Documentacao tecnica
    "docs/architecture.md",
    "docs/rag_pipeline.md",
    "docs/diagnostics_spec.md",
    "docs/references.bib",
    # Notebooks didaticos
    "notebooks/01-exploracao-vetorial.ipynb",
    "notebooks/02-exploracao-raster.ipynb",
    "notebooks/03-prototipo-diagnostico.ipynb",
    "notebooks/04-prototipo-rag-docs.ipynb",
    "notebooks/05-avaliacao-respostas.ipynb",
    # Scripts utilitarios
    "scripts/build_docs_index.py",
    "scripts/bootstrap_samples.py",
    # Codigo-fonte: pacote principal
    "src/geopyassistant/__init__.py",
    "src/geopyassistant/config.py",
    "src/geopyassistant/py.typed",
    # Subpacote: ingestao
    "src/geopyassistant/ingestion/__init__.py",
    "src/geopyassistant/ingestion/vector_loader.py",
    "src/geopyassistant/ingestion/raster_loader.py",
    "src/geopyassistant/ingestion/docs_loader.py",
    # Subpacote: diagnostico
    "src/geopyassistant/diagnostics/__init__.py",
    "src/geopyassistant/diagnostics/schema.py",
    "src/geopyassistant/diagnostics/vector_profiler.py",
    "src/geopyassistant/diagnostics/raster_profiler.py",
    "src/geopyassistant/diagnostics/formatter.py",
    # Subpacote: RAG
    "src/geopyassistant/rag/__init__.py",
    "src/geopyassistant/rag/embeddings.py",
    "src/geopyassistant/rag/vectorstore.py",
    "src/geopyassistant/rag/retriever.py",
    "src/geopyassistant/rag/pipeline.py",
    # Subpacote: LLM
    "src/geopyassistant/llm/__init__.py",
    "src/geopyassistant/llm/prompts.py",
    "src/geopyassistant/llm/client.py",
    # Subpacote: geracao de codigo
    "src/geopyassistant/codegen/__init__.py",
    "src/geopyassistant/codegen/snippet_generator.py",
    # Subpacote: UI
    "src/geopyassistant/ui/__init__.py",
    "src/geopyassistant/ui/app.py",
    "src/geopyassistant/ui/components.py",
    "src/geopyassistant/ui/state.py",
    # Testes
    "tests/__init__.py",
    "tests/conftest.py",
    "tests/unit/__init__.py",
    "tests/unit/test_vector_profiler.py",
    "tests/unit/test_raster_profiler.py",
    "tests/unit/test_schema.py",
    "tests/unit/test_prompts.py",
    "tests/integration/__init__.py",
    "tests/integration/test_rag_pipeline.py",
    "tests/integration/test_full_flow.py",
]

# Arquivos que precisam nascer ja com algum conteudo minimo.
FILES_WITH_CONTENT: dict[str, str] = {
    "references/README.md": (
        "# References\n\n"
        "Este diretorio recebe a documentacao oficial das bibliotecas indexada\n"
        "pelo script `scripts/build_docs_index.py`. Conteudo nao versionado.\n"
    ),
    "scripts/run_dev.sh": (
        "#!/usr/bin/env bash\n"
        "streamlit run src/geopyassistant/ui/app.py\n"
    ),
    "scripts/run_dev.ps1": (
        "# Atalho PowerShell para subir a aplicacao em modo desenvolvimento\n"
        "streamlit run src/geopyassistant/ui/app.py\n"
    ),
}


# ---------------------------------------------------------------------------
# Logica de criacao
# ---------------------------------------------------------------------------

def create_directory(path: Path) -> str:
    """Cria diretorio recursivamente. Retorna [OK], [SKIP] ou [ERRO]."""
    try:
        if path.exists():
            return "[SKIP]"
        path.mkdir(parents=True, exist_ok=True)
        return "[OK]"
    except OSError as exc:
        print(f"  [ERRO] {path}: {exc}", file=sys.stderr)
        return "[ERRO]"


def touch_file(path: Path) -> str:
    """Cria arquivo vazio se nao existir. Retorna [OK], [SKIP] ou [ERRO]."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return "[SKIP]"
        path.touch()
        return "[OK]"
    except OSError as exc:
        print(f"  [ERRO] {path}: {exc}", file=sys.stderr)
        return "[ERRO]"


def write_file(path: Path, content: str) -> str:
    """Escreve arquivo com conteudo. Sobrescreve se vazio."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            return "[SKIP]"
        path.write_text(content, encoding="utf-8", newline="\n")
        return "[OK]"
    except OSError as exc:
        print(f"  [ERRO] {path}: {exc}", file=sys.stderr)
        return "[ERRO]"


def main() -> int:
    print(f"GeoPython Assistant v2 - bootstrap da estrutura")
    print(f"Raiz do projeto: {PROJECT_ROOT}")
    print("-" * 60)

    print("\n[1/3] Criando diretorios...")
    for d in DIRECTORIES:
        status = create_directory(PROJECT_ROOT / d)
        print(f"  {status} {d}")

    print("\n[2/3] Criando arquivos stub vazios...")
    for f in EMPTY_FILES:
        status = touch_file(PROJECT_ROOT / f)
        print(f"  {status} {f}")

    print("\n[3/3] Criando arquivos com conteudo inicial...")
    for f, content in FILES_WITH_CONTENT.items():
        status = write_file(PROJECT_ROOT / f, content)
        print(f"  {status} {f}")

    print("-" * 60)
    print("Estrutura criada com sucesso.")
    print()
    print("Proximo passo no PowerShell:")
    print("  pip install --upgrade pip")
    print('  pip install -e ".[dev]"')
    print("  pre-commit install")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
