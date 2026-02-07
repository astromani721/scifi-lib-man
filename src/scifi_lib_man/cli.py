import json
import os

import requests
import typer

from .catalog import (
    extract_authors,
    extract_work_fields,
    fetch_author_by_olid,
    fetch_work_by_olid,
    normalize_author_entries,
)
from .storage import (
    add_to_reading_list,
    add_work_author,
    connect,
    get_db_path,
    get_reading_list,
    init_db,
    remove_from_reading_list,
    upsert_author,
    upsert_work,
)


app = typer.Typer(help="Science Fiction Library Manager CLI")
API_BASE = os.getenv("SCIFI_API_BASE", "http://127.0.0.1:8000").rstrip("/")


@app.command()
def hello(name: str = "reader") -> None:
    """Simple sanity command for the CLI."""
    typer.echo(f"Hello, {name}!")


@app.command()
def health() -> None:
    """Basic health check for wiring/testing."""
    typer.echo("ok")


@app.command("init-db")
def init_db_cmd(
    db_path: str = typer.Option(None, help="SQLite DB path override."),
) -> None:
    """Create the SQLite schema."""
    conn = connect(db_path or get_db_path())
    init_db(conn)
    conn.close()
    typer.echo("ok")


@app.command("add")
def add_to_list(
    olid: str = typer.Argument(
        ..., help="Open Library work key (e.g., /works/OL123W)."
    ),
    status: str = typer.Option("wishlist", help="read, reading, or wishlist."),
    notes: str | None = typer.Option(None, help="Optional notes."),
    rating: int | None = typer.Option(None, help="Optional rating."),
    db_path: str | None = typer.Option(None, help="SQLite DB path override."),
) -> None:
    """Add/update a book in the reading list."""
    normalized = olid.strip()
    if normalized.startswith("works/"):
        normalized = f"/{normalized}"
    if not normalized.startswith("/works/") or not normalized.endswith("W"):
        raise typer.BadParameter("Use a /works/ key ending with W (work).")

    record = fetch_work_by_olid(normalized)
    work_fields = extract_work_fields(record)
    conn = connect(db_path or get_db_path())
    init_db(conn)
    upsert_work(conn, **work_fields)
    authors = normalize_author_entries(extract_authors(record))
    for index, author in enumerate(authors):
        author_key = author["key"]
        name = author.get("name")
        try:
            author_record = fetch_author_by_olid(author_key)
        except (ValueError, RuntimeError):
            author_record = None
        if author_record:
            name = author_record.get("name") or name
        upsert_author(
            conn,
            olid=author_key,
            name=name,
        )
        add_work_author(
            conn,
            work_olid=work_fields["olid"],
            author_olid=author_key,
            author_order=index,
        )
    add_to_reading_list(
        conn,
        work_olid=work_fields["olid"],
        status=status,
        notes=notes,
        rating=rating,
    )
    conn.commit()
    conn.close()
    typer.echo("ok")


@app.command("list")
def list_entries(
    status: str | None = typer.Option(None, help="Filter: read, reading, wishlist."),
    db_path: str | None = typer.Option(None, help="SQLite DB path override."),
) -> None:
    """List reading list entries."""
    conn = connect(db_path or get_db_path())
    init_db(conn)
    entries = get_reading_list(conn, status=status)
    conn.close()
    for entry in entries:
        typer.echo(f"{entry['work_olid']} [{entry['status']}] {entry['title']}")


@app.command("remove")
def remove_entry(
    olid: str = typer.Argument(..., help="Open Library OLID (e.g., OL123W)."),
    db_path: str | None = typer.Option(None, help="SQLite DB path override."),
) -> None:
    """Remove a book from the reading list."""
    conn = connect(db_path or get_db_path())
    init_db(conn)
    remove_from_reading_list(conn, work_olid=olid)
    conn.commit()
    conn.close()
    typer.echo("ok")


@app.command("similar")
def similar_works(
    work_olid: str = typer.Argument(
        ..., help="Open Library work key (e.g., /works/OL123W)."
    ),
    prefer_same_author: bool = typer.Option(
        False, help="Boost works by the same author."
    ),
    prefer_year_range: int | None = typer.Option(
        None, help="Prefer works within +/- N years."
    ),
    max_candidates: int = typer.Option(200, help="Max candidates to index."),
    batch_size: int = typer.Option(25, help="Batch size for embedding."),
    time_budget_sec: int = typer.Option(15, help="Time budget in seconds."),
    language: str = typer.Option("eng", help="Language filter (ISO 639-2)."),
) -> None:
    """Stream similar works via the API SSE endpoint."""
    params = {
        "work_olid": work_olid,
        "prefer_same_author": str(prefer_same_author).lower(),
        "max_candidates": max_candidates,
        "batch_size": batch_size,
        "time_budget_sec": time_budget_sec,
        "language": language,
    }
    if prefer_year_range is not None:
        params["prefer_year_range"] = prefer_year_range

    url = f"{API_BASE}/works/similar/stream"
    typer.echo(f"Connecting to {url}")
    response = requests.get(url, params=params, stream=True, timeout=60)
    response.raise_for_status()

    event_name = None
    data_lines: list[str] = []

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = raw_line.strip()
        if not line:
            if not event_name or not data_lines:
                event_name = None
                data_lines = []
                continue
            payload = json.loads("\n".join(data_lines))
            if event_name == "status":
                typer.echo(f"[status] {payload.get('message', '')}")
            elif event_name == "progress":
                embedded = payload.get("embedded", 0)
                total = payload.get("total", 0)
                typer.echo(f"[progress] {embedded}/{total}")
            elif event_name == "results":
                items = payload.get("items", [])
                typer.echo(f"[results] {len(items)} matches")
                for item in items[:10]:
                    title = item.get("title") or "Unknown"
                    score = item.get("score")
                    typer.echo(f" - {title} ({score})")
            elif event_name == "error":
                typer.echo(f"[error] {payload.get('message', '')}")
                break
            elif event_name == "done":
                typer.echo("[done] refined results ready")
                break
            event_name = None
            data_lines = []
            continue

        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
