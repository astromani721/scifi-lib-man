# scifi-lib-man
Personal Science Fiction Library Manager. Organize a reading list of Hugo/Nebula/Locus award winners, track read/unread status, and get random unread picks. Includes a FastAPI endpoint to query Open Library.

See `AGENTS.md` for repo-specific contributor/agent instructions.

## Features
- CLI scaffold (Typer)
- FastAPI app with `/health`, `/books/search`, `/books/isbn/{isbn}`, `/books/awards/{award}/search`
- Open Library search + ISBN detail lookup
- Dependency sync from `pyproject.toml`

## Requirements
- Python >= 3.9

## Setup
Create a virtual environment and install dev dependencies:
```
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Run the API
```
uvicorn scifi_lib_man.main:app --reload
```

### Example requests
```
curl "http://127.0.0.1:8000/health"
curl "http://127.0.0.1:8000/books/search?author=Ayn%20Rand&limit=5"
curl "http://127.0.0.1:8000/books/isbn/9780143111580"
curl "http://127.0.0.1:8000/books/awards/hugo/search?author=Ursula%20Le%20Guin&year=1969"
curl "http://127.0.0.1:8000/books/awards/nebula/search?year_from=1990&year_to=1999"
curl "http://127.0.0.1:8000/books/awards/locus/search?title=Neuromancer"
```

## Run the CLI
```
scifi-lib-man --help
scifi-lib-man hello
scifi-lib-man health
```

## Tests
```
pytest
```

## Development
Sync `requirements.txt` from `pyproject.toml`:
```
make sync-requirements
```

Dev dependencies are captured in `requirements-dev.txt` when synced.
