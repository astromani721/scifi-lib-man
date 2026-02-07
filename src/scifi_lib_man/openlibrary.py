from __future__ import annotations

"""Open Library client helpers and query builders."""

import os
from typing import Iterable

import requests


BASE_URL = "https://openlibrary.org"
SEARCH_ENDPOINT = f"{BASE_URL}/search.json"
ISBN_ENDPOINT = f"{BASE_URL}/isbn"
WORK_PREFIX = "/works/"
BOOK_PREFIX = "/books/"
AUTHOR_PREFIX = "/authors/"
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
    "pulitzer": [
        ("subject_key", "pulitzer_prize_winner"),
        ("subject_key", "pulitzer_prizes"),
        ("subject", "Pulitzer Prize"),
        ("subject", "Pulitzer Prize Winner"),
        ("subject", "Pulitzer Prizes"),
    ],
    "booker": [
        ("subject_key", "man_booker_prize_winner"),
        ("subject", "Booker Prize"),
        ("subject", "Man Booker Prize"),
        ("subject", "Booker Prize Winner"),
        ("subject", "Man Booker Prize Winner"),
    ],
    "nobel": [
        ("subject_key", "nobel_prize_winners"),
        ("subject_key", "nobel_prizes"),
        ("subject", "Nobel Prize"),
        ("subject", "Nobel Prize winners"),
        ("subject", "Nobel Prizes"),
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


def _append_query(existing: str | None, clause: str) -> str:
    if not existing:
        return clause
    return f"({existing}) AND {clause}"


def build_award_query(
    *,
    award_filters: Iterable[tuple[str, str]] | None = None,
    q: str | None = None,
    title: str | None = None,
    author: str | None = None,
    isbn: str | None = None,
    subject: str | None = None,
    subject_key: str | None = None,
    language: str | None = None,
    year: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> str:
    """Build a boolean Open Library query with award filters and optional facets."""
    if not award_filters:
        raise ValueError("award_filters must include at least one filter.")
    if year is not None and (year_from is not None or year_to is not None):
        raise ValueError("Use either year or year_from/year_to, not both.")

    filter_terms = [f"{field}:{_quote_term(value)}" for field, value in award_filters]
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
    if subject:
        parts.append(f"subject:{_quote_term(subject)}")
    if subject_key:
        parts.append(f"subject_key:{_quote_term(subject_key)}")
    if language:
        parts.append(f"language:{_quote_term(language)}")
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
    subject: str | None = None,
    subject_key: str | None = None,
    language: str | None = None,
    year: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 10,
    page: int = 1,
    fields: Iterable[str] | None = None,
) -> dict:
    """Perform a search against Open Library with standardized parameters."""
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100.")
    if page < 1:
        raise ValueError("page must be >= 1.")
    if year is not None and (year_from is not None or year_to is not None):
        raise ValueError("Use either year or year_from/year_to, not both.")

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
    if subject:
        params["subject"] = subject
    if subject_key:
        params["subject_key"] = subject_key
    if language:
        params["language"] = language
    if year is not None:
        params["first_publish_year"] = year
    if year_from is not None or year_to is not None:
        start = "*" if year_from is None else year_from
        end = "*" if year_to is None else year_to
        params["q"] = _append_query(
            params.get("q"), f"first_publish_year:[{start} TO {end}]"
        )

    try:
        response = requests.get(SEARCH_ENDPOINT, params=params, timeout=10)
        if os.getenv("SCIFI_LOG_OPENLIBRARY") == "1":
            print(f"Open Library search URL: {response.url}")
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError("Open Library search request failed.") from exc

    return response.json()


def fetch_by_isbn(isbn: str) -> dict:
    """Fetch an edition by ISBN via Open Library."""
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


def fetch_by_key(key: str, *, allowed_prefixes: Iterable[str]) -> dict:
    """Fetch a record by its Open Library key."""
    if not key or not key.strip():
        raise ValueError("key must be a non-empty string.")
    if not any(key.startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError(
            "key must start with one of: " + ", ".join(sorted(allowed_prefixes))
        )

    url = f"{BASE_URL}{key}.json"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise ValueError("Key not found in Open Library.") from exc
        raise RuntimeError("Open Library key request failed.") from exc
    except requests.RequestException as exc:
        raise RuntimeError("Open Library key request failed.") from exc

    return response.json()
