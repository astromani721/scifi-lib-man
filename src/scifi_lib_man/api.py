from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query

from .openlibrary import (
    AWARD_FILTERS,
    REQUIRED_FIELDS,
    build_award_query,
    fetch_by_isbn,
    search_openlibrary,
)

app = FastAPI(title="Sci-Fi Library Manager", version="0.1.0")


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
            detail="Unknown award. Use one of: hugo, nebula, locus.",
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
