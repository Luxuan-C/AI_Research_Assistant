# Academic GraphRAG

Academic GraphRAG retrieval and paper-ranking pipeline.

## Requirements

- Python 3.11 or newer

## Install

From the repository root on Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

For development, use an editable install instead:

```powershell
python -m pip install -e .
```

## Run the paper ranking pipeline

```powershell
python -m ranking.paper_ranking
```

The default demonstration calls the local academic GraphRAG mock backend,
converts its `RetrievalResponse` publication results into ranking candidates,
and prints the ranked papers.

## Run tests

```powershell
python -m unittest discover -s tests -v
```