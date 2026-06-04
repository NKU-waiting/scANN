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
npm install
npm run dev
```

Use `npm run build` to validate the production build, and `npm run preview` to inspect it locally. The frontend proxies `/api` to Flask.

## Coding Style & Naming Conventions

Follow PEP 8 for Python: 4-space indentation, `snake_case` functions/modules, and concise docstrings for public services or routes. Keep API handlers thin and reusable logic in `backend/app/services/`. Index implementations should follow `BaseIndex` and use lowercase names such as `flat`, `ivf`, or `hnsw`. Vue components use `<script setup>`, 2-space indentation, and descriptive reactive names such as `status`, `form`, and `loading`.

## Testing Guidelines

No automated test suite is currently checked in. When adding tests, place backend tests under `backend/tests/` with `test_*.py` filenames and prefer Flask test-client coverage for API routes plus service tests for indexes/search. Add frontend tests only after adding the required tooling. Until test scripts exist, run `npm run build` and verify the backend health/search endpoints manually.

## Commit & Pull Request Guidelines

Use the project commit pattern `<action>: <description>`, for example `fix: handle empty search results` or `doc: update setup notes`. Prefer actions such as `update`, `fix`, `delete`, and `doc`. Pull requests should include a summary, commands run, linked issues or checklist items, and screenshots for frontend UI changes. Note dependency or data-format changes explicitly.

## Security & Configuration Tips

Do not commit `.env`, databases, `.h5ad` data files, generated indexes, or `frontend/dist/`. Keep documentation and examples free of machine-specific paths, usernames, tokens, and private dataset details.
