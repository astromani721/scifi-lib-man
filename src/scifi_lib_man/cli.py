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
