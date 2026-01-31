from __future__ import annotations

from typing import Iterable

import requests


BASE_URL = "https://openlibrary.org"
SEARCH_ENDPOINT = f"{BASE_URL}/search.json"
ISBN_ENDPOINT = f"{BASE_URL}/isbn"
REQUIRED_FIELDS = [
    "key",
    "title",
    "author_name",
    "first_publish_year",
    "isbn",
    "cover_i",
]
AWARD_FILTERS = {
    "hugo": [("subject_key", "hugo_award_winner")],
    "nebula": [
        ("subject_key", "nebula_award_winner"),
        ("subject", "Nebula Award"),
    ],
    "locus": [
        ("subject_key", "locus_award_winner"),
        ("subject", "Locus Award"),
        ("subject", "Locus Awards"),
    ],
}


def _normalize_fields(fields: Iterable[str] | None) -> str:
    if not fields:
        return ",".join(REQUIRED_FIELDS)
    normalized = [field.strip() for field in fields if field.strip()]
    if not normalized:
        return ",".join(REQUIRED_FIELDS)
    return ",".join(normalized)


def _quote_term(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return '""'
    escaped = trimmed.replace('"', '\\"')
    if " " in escaped or ":" in escaped:
        return f'"{escaped}"'
    return escaped


def build_award_query(
    *,
    award_filters: Iterable[tuple[str, str]] | None = None,
    q: str | None = None,
    title: str | None = None,
    author: str | None = None,
    isbn: str | None = None,
    year: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> str:
    if not award_filters:
        raise ValueError("award_filters must include at least one filter.")
    if year is not None and (year_from is not None or year_to is not None):
        raise ValueError("Use either year or year_from/year_to, not both.")

    filter_terms = [
        f"{field}:{_quote_term(value)}" for field, value in award_filters
    ]
    subject_clause = filter_terms[0]
    if len(filter_terms) > 1:
        subject_clause = "(" + " OR ".join(filter_terms) + ")"

    parts = [subject_clause]
    if q:
        parts.append(f"({q})")
    if title:
        parts.append(f"title:{_quote_term(title)}")
    if author:
        parts.append(f"author:{_quote_term(author)}")
    if isbn:
        parts.append(f"isbn:{_quote_term(isbn)}")
    if year is not None:
        parts.append(f"first_publish_year:{year}")
    if year_from is not None or year_to is not None:
        start = "*" if year_from is None else year_from
        end = "*" if year_to is None else year_to
        parts.append(f"first_publish_year:[{start} TO {end}]")

    return " AND ".join(parts)


def search_openlibrary(
    *,
    q: str | None = None,
    title: str | None = None,
    author: str | None = None,
    isbn: str | None = None,
    limit: int = 10,
    page: int = 1,
    fields: Iterable[str] | None = None,
) -> dict:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100.")
    if page < 1:
        raise ValueError("page must be >= 1.")

    params: dict[str, str | int] = {
        "limit": limit,
        "page": page,
        "fields": _normalize_fields(fields),
    }
    if q:
        params["q"] = q
    if title:
        params["title"] = title
    if author:
        params["author"] = author
    if isbn:
        params["isbn"] = isbn

    try:
        response = requests.get(SEARCH_ENDPOINT, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError("Open Library search request failed.") from exc

    return response.json()


def fetch_by_isbn(isbn: str) -> dict:
    if not isbn or not isbn.strip():
        raise ValueError("isbn must be a non-empty string.")

    url = f"{ISBN_ENDPOINT}/{isbn}.json"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise ValueError("ISBN not found in Open Library.") from exc
        raise RuntimeError("Open Library ISBN request failed.") from exc
    except requests.RequestException as exc:
        raise RuntimeError("Open Library ISBN request failed.") from exc

    return response.json()
