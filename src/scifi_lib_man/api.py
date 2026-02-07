"""FastAPI routes for the Sci-Fi Library Manager."""

from typing import Annotated, Iterator

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .catalog import (
    extract_authors,
    extract_work_fields,
    fetch_author_by_olid,
    fetch_book_by_olid,
    fetch_work_by_olid,
    normalize_author_entries,
)
from .openlibrary import (
    AWARD_FILTERS,
    REQUIRED_FIELDS,
    WORK_PREFIX,
    build_award_query,
    fetch_by_isbn,
    search_openlibrary,
)
from .storage import (
    add_to_reading_list,
    add_work_author,
    connect,
    get_db_path,
    get_reading_list,
    get_reading_list_entry,
    init_db,
    remove_from_reading_list,
    upsert_author,
    upsert_work,
)
from .similarity import SimilarityOptions, start_similarity_stream

app = FastAPI(title="Sci-Fi Library Manager", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ReadingListEntry(BaseModel):
    status: str = Field(..., description="read, reading, or wishlist.")
    notes: str | None = None
    rating: int | None = None
    first_publish_year: int | None = None


def get_db() -> Iterator:
    conn = connect(get_db_path())
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def _normalize_work_key(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise HTTPException(status_code=404, detail="Work OLID must be provided.")
    if trimmed.startswith(WORK_PREFIX):
        if not trimmed.endswith("W"):
            raise HTTPException(
                status_code=404,
                detail="Work OLID must be a work key ending with W.",
            )
        return trimmed
    if trimmed.startswith("works/"):
        if not trimmed.endswith("W"):
            raise HTTPException(
                status_code=404,
                detail="Work OLID must be a work key ending with W.",
            )
        return f"/{trimmed}"
    raise HTTPException(
        status_code=404,
        detail="Work OLID must be a /works/ key ending with W.",
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
    subject: Annotated[
        str | None,
        Query(description="Optional subject filter."),
    ] = None,
    subject_key: Annotated[
        str | None,
        Query(description="Optional subject key filter (normalized subject)."),
    ] = None,
    language: Annotated[
        str | None,
        Query(description="Optional language filter."),
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
    """Search Open Library works with optional filters."""
    if not any(
        [
            q,
            title,
            author,
            isbn,
            subject,
            subject_key,
            language,
            year,
            year_from,
            year_to,
        ]
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of q, title, author, isbn, subject, language, or year.",
        )
    if year is not None and (year_from is not None or year_to is not None):
        raise HTTPException(
            status_code=400,
            detail="Use either year or year_from/year_to, not both.",
        )

    try:
        return search_openlibrary(
            q=q,
            title=title,
            author=author,
            isbn=isbn,
            subject=subject,
            subject_key=subject_key,
            language=language,
            year=year,
            year_from=year_from,
            year_to=year_to,
            limit=limit,
            page=page,
            fields=fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/books/quick-search")
def quick_search_books(
    q: Annotated[
        str,
        Query(description="Keyword query for quick search."),
    ],
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
) -> dict:
    """Lightweight search for quick UI lookups."""
    try:
        return search_openlibrary(
            q=q,
            limit=limit,
            page=page,
            fields=["key", "title", "author_name", "first_publish_year"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/books/isbn/{isbn}")
def get_book_by_isbn(isbn: str) -> dict:
    """Fetch an Open Library edition by ISBN."""
    try:
        return fetch_by_isbn(isbn)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/books/{olid}")
def get_book_by_olid(olid: str) -> dict:
    """Fetch an Open Library edition by OLID."""
    try:
        return fetch_book_by_olid(olid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/authors/{olid}")
def get_author_by_olid(olid: str) -> dict:
    """Fetch an Open Library author by OLID."""
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
        normalized_key = _normalize_work_key(olid_path)
        record = fetch_work_by_olid(normalized_key)
        work_fields = extract_work_fields(record)
        if work_fields.get("first_publish_year") is None and payload.first_publish_year:
            work_fields["first_publish_year"] = payload.first_publish_year
        if not work_fields["olid"]:
            raise HTTPException(status_code=502, detail="Work key missing from record.")
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
            status=payload.status,
            notes=payload.notes,
            rating=payload.rating,
        )
        conn.commit()
        return {"work_olid": work_fields["olid"], "status": payload.status}
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
    normalized = _normalize_work_key(olid_path)
    entry = get_reading_list_entry(conn, work_olid=normalized)
    if entry is None:
        raise HTTPException(status_code=404, detail="Work not found in reading list.")

    status = payload.status or entry["status"]
    notes = payload.notes if payload.notes is not None else entry["notes"]
    rating = payload.rating if payload.rating is not None else entry["rating"]
    try:
        add_to_reading_list(
            conn,
            work_olid=normalized,
            status=status,
            notes=notes,
            rating=rating,
        )
        conn.commit()
        return {"work_olid": normalized, "status": status}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/reading-list/{olid_path:path}")
def delete_reading_list_entry(olid_path: str, conn=Depends(get_db)) -> dict:
    normalized = _normalize_work_key(olid_path)
    remove_from_reading_list(conn, work_olid=normalized)
    conn.commit()
    return {"work_olid": normalized, "deleted": True}


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
    subject: Annotated[
        str | None,
        Query(description="Optional subject filter."),
    ] = None,
    subject_key: Annotated[
        str | None,
        Query(description="Optional subject key filter (normalized subject)."),
    ] = None,
    language: Annotated[
        str | None,
        Query(description="Optional language filter."),
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
    """Search for award-winning works using Open Library subject filters."""
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
            subject=subject,
            subject_key=subject_key,
            language=language,
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


@app.get("/works/{olid}")
def get_work_by_olid(olid: str) -> dict:
    """Fetch an Open Library work by OLID."""
    try:
        return fetch_work_by_olid(olid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/works/similar/stream")
def stream_similar_works(
    work_olid: Annotated[
        str,
        Query(description="Work OLID (e.g. /works/OL45804W)."),
    ],
    prefer_same_author: Annotated[
        bool,
        Query(description="Boost works by the same author."),
    ] = False,
    prefer_year_range: Annotated[
        int | None,
        Query(description="Prefer works within +/- N years."),
    ] = None,
    max_candidates: Annotated[
        int,
        Query(ge=10, le=500, description="Max candidates to index."),
    ] = 200,
    batch_size: Annotated[
        int,
        Query(ge=5, le=100, description="Batch size for embedding."),
    ] = 25,
    time_budget_sec: Annotated[
        int,
        Query(ge=5, le=60, description="Time budget in seconds."),
    ] = 15,
    language: Annotated[
        str | None,
        Query(description="Optional language filter (ISO 639-2)."),
    ] = "eng",
) -> StreamingResponse:
    """Stream SSE updates for similar works."""
    options = SimilarityOptions(
        prefer_same_author=prefer_same_author,
        prefer_year_range=prefer_year_range,
        max_candidates=max_candidates,
        batch_size=batch_size,
        time_budget_sec=time_budget_sec,
        language=language,
    )
    stream = start_similarity_stream(work_olid=work_olid, options=options)
    return StreamingResponse(stream, media_type="text/event-stream")
