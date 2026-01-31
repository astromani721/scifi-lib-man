# AGENTS.md

## Purpose
Personal Science Fiction Library Manager. Manage a reading list of Hugo/Nebula/Locus/Pulitzer/Booker/Nobel award winners, track read/unread, and provide random unread picks. Optional Open Library integration.

## Tech Stack
- Python >= 3.9
- CLI: Typer (`scifi-lib-man`)
- API: FastAPI (`scifi_lib_man.main:app`)

## Repo Layout
- `src/scifi_lib_man/`: application code
- `tests/`: test suite
- `scripts/`: maintenance scripts
- `pyproject.toml`: project config + deps
- `requirements.txt` / `requirements-dev.txt`: synced dependency lists
  - Open Library integration uses `requests`

## Development Workflow
- Create venv: `python -m venv .venv`
- Install: `pip install -e .[dev]`
- Run CLI: `scifi-lib-man --help`
- Run API: `uvicorn scifi_lib_man.main:app --reload`
- Sync deps: `make sync-requirements`
- Tests: `pytest`

## Dependency Policy
- Add runtime deps in `pyproject.toml` under `[project].dependencies`
- Add dev tools in `[project.optional-dependencies].dev`
- Run `make sync-requirements` after changes
- Do not edit `requirements*.txt` manually
- Tests use FastAPI `TestClient` (requires `httpx` in dev deps)

## Conventions
- Keep CLI and API using the same underlying storage + models
- Add new functionality in `src/scifi_lib_man/` and test in `tests/`
- Prefer simple, explicit Python over clever abstractions
- API routes: `/health`, `/books/search`, `/books/isbn/{isbn}`, `/books/{olid}`, `/authors/{olid}`, `/books/awards/{award}/search`, `/reading-list`

## Guardrails
- Avoid breaking storage format once chosen
- Keep endpoints and commands stable (additive changes preferred)
