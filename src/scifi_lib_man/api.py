from typing import Annotated, Iterator

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field

from .catalog import (
    extract_authors,
    extract_book_fields,
    fetch_author_by_olid,
    fetch_book_by_olid,
    normalize_author_entries,
)
from .openlibrary import (
    AWARD_FILTERS,
    BOOK_PREFIX,
    REQUIRED_FIELDS,
    WORK_PREFIX,
    build_award_query,
    fetch_by_isbn,
    search_openlibrary,
)
from .storage import (
    add_book_author,
    add_to_reading_list,
    connect,
    get_db_path,
    get_reading_list,
    get_reading_list_entry,
    init_db,
    remove_from_reading_list,
    upsert_author,
    upsert_book,
)

app = FastAPI(title="Sci-Fi Library Manager", version="0.1.0")


class ReadingListEntry(BaseModel):
    status: str = Field(..., description="read, reading, or wishlist.")
    notes: str | None = None
    rating: int | None = None


def get_db() -> Iterator:
    conn = connect(get_db_path())
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def _normalize_book_key(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise HTTPException(status_code=404, detail="Book OLID must be provided.")
    if trimmed.startswith(BOOK_PREFIX):
        if not trimmed.endswith("M"):
            raise HTTPException(
                status_code=404,
                detail="Book OLID must be an edition key ending with M.",
            )
        return trimmed
    if trimmed.startswith("books/"):
        if not trimmed.endswith("M"):
            raise HTTPException(
                status_code=404,
                detail="Book OLID must be an edition key ending with M.",
            )
        return f"/{trimmed}"
    raise HTTPException(
        status_code=404,
        detail="Book OLID must be a /books/ key ending with M.",
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "message": "I am healthy!"}


@app.get("/books/search")
def search_books(
        q: Annotated[
            str | None,
            Query(
                description=(
                        "Optional keyword search. At least one of q, title, author, or isbn is required."
                )
            ),
        ] = None,
        title: Annotated[
            str | None,
            Query(
                description=(
                        "Optional title search. At least one of q, title, author, or isbn is required."
                ),
            ),
        ] = None,
        author: Annotated[
            str | None,
            Query(
                description=(
                        "Optional author search. At least one of q, title, author, or isbn is required."
                ),
            ),
        ] = None,
        isbn: Annotated[
            str | None,
            Query(
                description=(
                        "Optional ISBN search. At least one of q, title, author, or isbn is required."
                ),
            ),
        ] = None,
        limit: Annotated[
            int,
            Query(
                ge=1,
                le=100,
                description="Optional page size (1-100).",
            ),
        ] = 10,
        page: Annotated[
            int,
            Query(
                ge=1,
                description="Optional page number (>= 1).",
            ),
        ] = 1,
        fields: Annotated[
            list[str] | None,
            Query(
                description=(
                        "Optional list of response fields. If omitted, defaults to required fields: "
                        + ", ".join(REQUIRED_FIELDS)
                ),
            ),
        ] = None,
) -> dict:
    if not any([q, title, author, isbn]):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of q, title, author, or isbn.",
        )

    try:
        return search_openlibrary(
            q=q,
            title=title,
            author=author,
            isbn=isbn,
            limit=limit,
            page=page,
            fields=fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/books/isbn/{isbn}")
def get_book_by_isbn(isbn: str) -> dict:
    try:
        return fetch_by_isbn(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/books/{olid}")
def get_book_by_olid(olid: str) -> dict:
    try:
        return fetch_book_by_olid(olid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/authors/{olid}")
def get_author_by_olid(olid: str) -> dict:
    try:
        return fetch_author_by_olid(olid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/reading-list/{olid_path:path}")
def add_reading_list_entry(
    olid_path: str,
    payload: ReadingListEntry,
    conn=Depends(get_db),
) -> dict:
    try:
        normalized_key = _normalize_book_key(olid_path)
        record = fetch_book_by_olid(normalized_key)
        book_fields = extract_book_fields(record)
        if not book_fields["olid"]:
            raise HTTPException(status_code=502, detail="Book key missing from record.")
        upsert_book(conn, **book_fields)
        authors = normalize_author_entries(extract_authors(record))
        for index, author in enumerate(authors):
            upsert_author(
                conn,
                olid=author["key"],
                name=author.get("name"),
                personal_name=author.get("personal_name"),
            )
            add_book_author(
                conn,
                book_olid=book_fields["olid"],
                author_olid=author["key"],
                author_order=index,
            )
        add_to_reading_list(
            conn,
            book_olid=book_fields["olid"],
            status=payload.status,
            notes=payload.notes,
            rating=payload.rating,
        )
        conn.commit()
        return {"book_olid": book_fields["olid"], "status": payload.status}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/reading-list")
def list_reading_list(
    status: Annotated[
        str | None,
        Query(description="Optional filter: read, reading, wishlist."),
    ] = None,
    conn=Depends(get_db),
) -> list[dict]:
    try:
        return get_reading_list(conn, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/reading-list/{olid_path:path}")
def update_reading_list_entry(
    olid_path: str,
    payload: ReadingListEntry,
    conn=Depends(get_db),
) -> dict:
    normalized = _normalize_book_key(olid_path)
    entry = get_reading_list_entry(conn, book_olid=normalized)
    if entry is None:
        raise HTTPException(status_code=404, detail="Book not found in reading list.")

    status = payload.status or entry["status"]
    notes = payload.notes if payload.notes is not None else entry["notes"]
    rating = payload.rating if payload.rating is not None else entry["rating"]
    try:
        add_to_reading_list(
            conn,
            book_olid=normalized,
            status=status,
            notes=notes,
            rating=rating,
        )
        conn.commit()
        return {"book_olid": normalized, "status": status}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/reading-list/{olid_path:path}")
def delete_reading_list_entry(olid_path: str, conn=Depends(get_db)) -> dict:
    normalized = _normalize_book_key(olid_path)
    remove_from_reading_list(conn, book_olid=normalized)
    conn.commit()
    return {"book_olid": normalized, "deleted": True}


@app.get("/books/awards/{award}/search")
def search_award_books(
    award: Annotated[
        str,
        Path(
            description="Award name: hugo, nebula, or locus.",
        ),
    ],
    q: Annotated[
        str | None,
        Query(description="Optional raw query appended to the award filter."),
    ] = None,
    title: Annotated[
        str | None,
        Query(description="Optional title filter."),
    ] = None,
    author: Annotated[
        str | None,
        Query(description="Optional author filter."),
    ] = None,
    isbn: Annotated[
        str | None,
        Query(description="Optional ISBN filter."),
    ] = None,
    year: Annotated[
        int | None,
        Query(description="Optional year filter (first publish year)."),
    ] = None,
    year_from: Annotated[
        int | None,
        Query(description="Optional start year for a range filter."),
    ] = None,
    year_to: Annotated[
        int | None,
        Query(description="Optional end year for a range filter."),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Optional page size (1-100).",
        ),
    ] = 10,
    page: Annotated[
        int,
        Query(
            ge=1,
            description="Optional page number (>= 1).",
        ),
    ] = 1,
    fields: Annotated[
        list[str] | None,
        Query(
            description=(
                "Optional list of response fields. If omitted, defaults to required fields: "
                + ", ".join(REQUIRED_FIELDS)
            ),
        ),
    ] = None,
) -> dict:
    award_filters = AWARD_FILTERS.get(award.lower())
    if not award_filters:
        raise HTTPException(
            status_code=404,
            detail="Unknown award. Use one of: hugo, nebula, locus, pulitzer, booker, nobel.",
        )

    try:
        award_query = build_award_query(
            award_filters=award_filters,
            q=q,
            title=title,
            author=author,
            isbn=isbn,
            year=year,
            year_from=year_from,
            year_to=year_to,
        )
        return search_openlibrary(
            q=award_query,
            limit=limit,
            page=page,
            fields=fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
