from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from .openlibrary import REQUIRED_FIELDS, fetch_by_isbn, search_openlibrary

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
