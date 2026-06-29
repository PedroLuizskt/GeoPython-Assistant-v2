#!/usr/bin/env bash
# =============================================================================
# bootstrap_structure.sh
# Cria a arvore de diretorios do GeoPython Assistant v2 conforme o padrao
# Cookiecutter Data Science adaptado para projetos geoespaciais.
# Uso: bash scripts/bootstrap_structure.sh
# =============================================================================

set -euo pipefail

# Move para a raiz do projeto (um nivel acima do script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "Criando estrutura de diretorios em: $PROJECT_ROOT"

# Diretorios de dados
mkdir -p data/{raw,interim,processed,external,samples}
touch data/raw/.gitkeep data/interim/.gitkeep data/processed/.gitkeep data/external/.gitkeep

# Documentacao
mkdir -p docs
touch docs/architecture.md docs/rag_pipeline.md docs/diagnostics_spec.md docs/references.bib

# Notebooks
mkdir -p notebooks
touch notebooks/01-exploracao-vetorial.ipynb
touch notebooks/02-exploracao-raster.ipynb
touch notebooks/03-prototipo-diagnostico.ipynb
touch notebooks/04-prototipo-rag-docs.ipynb
touch notebooks/05-avaliacao-respostas.ipynb

# References (documentacao externa)
mkdir -p references
cat > references/README.md <<'EOF'
# References

Este diretorio recebe a documentacao oficial das bibliotecas indexada pelo
script `scripts/build_docs_index.py`. O conteudo nao e versionado.
EOF

# Reports
mkdir -p reports/figures
touch reports/figures/.gitkeep

# Scripts (alem deste)
touch scripts/build_docs_index.py
touch scripts/bootstrap_samples.py
cat > scripts/run_dev.sh <<'EOF'
#!/usr/bin/env bash
streamlit run src/geopyassistant/ui/app.py
EOF
chmod +x scripts/run_dev.sh

# Codigo-fonte
mkdir -p src/geopyassistant/{ingestion,diagnostics,rag,llm,codegen,ui}

# __init__.py em cada pacote
for pkg in "" ingestion diagnostics rag llm codegen ui; do
    if [ -z "$pkg" ]; then
        touch src/geopyassistant/__init__.py
    else
        touch src/geopyassistant/$pkg/__init__.py
    fi
done

# Stubs dos modulos principais
touch src/geopyassistant/config.py
touch src/geopyassistant/ingestion/vector_loader.py
touch src/geopyassistant/ingestion/raster_loader.py
touch src/geopyassistant/ingestion/docs_loader.py
touch src/geopyassistant/diagnostics/schema.py
touch src/geopyassistant/diagnostics/vector_profiler.py
touch src/geopyassistant/diagnostics/raster_profiler.py
touch src/geopyassistant/diagnostics/formatter.py
touch src/geopyassistant/rag/embeddings.py
touch src/geopyassistant/rag/vectorstore.py
touch src/geopyassistant/rag/retriever.py
touch src/geopyassistant/rag/pipeline.py
touch src/geopyassistant/llm/prompts.py
touch src/geopyassistant/llm/client.py
touch src/geopyassistant/codegen/snippet_generator.py
touch src/geopyassistant/ui/app.py
touch src/geopyassistant/ui/components.py
touch src/geopyassistant/ui/state.py
touch src/geopyassistant/py.typed

# Testes
mkdir -p tests/{unit,integration,data}
touch tests/__init__.py tests/conftest.py
touch tests/unit/test_vector_profiler.py
touch tests/unit/test_raster_profiler.py
touch tests/unit/test_schema.py
touch tests/unit/test_prompts.py
touch tests/integration/test_rag_pipeline.py
touch tests/integration/test_full_flow.py
touch tests/data/.gitkeep

echo "Estrutura criada com sucesso."
echo "Proximo passo sugerido: 'make install-dev' e 'make test'."
