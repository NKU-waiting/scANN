# Repository Guidelines

## Project Structure & Module Organization

This repository implements scANN, a Flask REST API plus Vue 3/Vite frontend for single-cell approximate nearest-neighbor retrieval. Backend code lives in `backend/app/`: `api/` contains Flask blueprints, `services/` contains data loading, search, and index implementations, `core/` contains configuration, and `models/` is reserved for data models. `backend/run.py` starts the API. Frontend code lives in `frontend/src/`, with `App.vue` as the current query UI and `main.js` as the entry point. Store large datasets and generated indexes outside git-tracked files; `data/` keeps only `.gitkeep`. Project documentation and figures live in `doc/`.

## Build, Test, and Development Commands

Use a conda environment before running project code:

```bash
conda create -n scann python=3.12 -y
conda activate scann
```

Install and run the backend:

```bash
cd backend
pip install -r requirements.txt
python run.py
```

Install and run the frontend:

```bash
cd frontend
npm ci
npm run dev
```

Use `npm run build` to validate the production build, and `npm run preview` to inspect it locally. The frontend proxies `/api` to Flask.

Run quality gates before committing:

```bash
cd backend
ruff check .
ruff format --check .
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider

cd ../frontend
npm run lint
npm test
npm run build
```

## Coding Style & Naming Conventions

Follow PEP 8 for Python: 4-space indentation, `snake_case` functions/modules, and concise docstrings for public services or routes. Keep API handlers thin and reusable logic in `backend/app/services/`. Index implementations should follow `BaseIndex` and use lowercase names such as `flat`, `ivf`, or `hnsw`. Vue components use `<script setup>`, 2-space indentation, and descriptive reactive names such as `status`, `form`, and `loading`.

## Testing Guidelines

Backend tests live under `backend/tests/` with `test_*.py` filenames and use Flask test clients plus service-level index/search tests. File lifecycle tests must use pytest temporary directories and must not retain uploaded samples, databases, indexes, logs, or results. Frontend tests use Vitest/jsdom in `frontend/src/**/*.test.js`. Keep permanent regression tests in Git, but remove temporary smoke scripts and outputs after validation.

## Commit & Pull Request Guidelines

Use the project commit pattern `<action>: <message>`, for example `fix: handle empty search results` or `doc: update setup notes`. Prefer actions such as `update`, `fix`, `delete`, and `doc`. Pull requests should include a summary, commands run, linked issues or checklist items, and screenshots for frontend UI changes. Note dependency or data-format changes explicitly. Better let each commit not only contain a message, but also a corresponding detailed description.

Every commit body must contain:

```text
Changes:
- <main changes>

Verification:
- <commands and results>

Scope:
- <affected areas and limitations>
```

## Security & Configuration Tips

Do not commit `.env`, databases, `.h5ad` data files, generated indexes, or `frontend/dist/`. Keep documentation and examples free of machine-specific paths, usernames, tokens, and private dataset details.
