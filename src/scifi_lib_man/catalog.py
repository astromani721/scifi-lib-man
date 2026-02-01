from __future__ import annotations

from collections.abc import Iterable

from .openlibrary import AUTHOR_PREFIX, BOOK_PREFIX, WORK_PREFIX, fetch_by_key


def fetch_book_by_olid(olid: str) -> dict:
    normalized = olid.strip()
    if not normalized:
        raise ValueError("OLID must be a non-empty string.")
    if normalized.startswith(BOOK_PREFIX):
        key = normalized
    elif normalized.startswith("books/"):
        key = f"/{normalized}"
    elif normalized.startswith("OL") and normalized.endswith("M"):
        key = f"{BOOK_PREFIX}{normalized}"
    else:
        raise ValueError("Book OLID must be an edition key ending with M.")
    allowed = (BOOK_PREFIX,)

    return fetch_by_key(key, allowed_prefixes=allowed)


def fetch_work_by_olid(olid: str) -> dict:
    normalized = olid.strip()
    if not normalized:
        raise ValueError("OLID must be a non-empty string.")
    if normalized.startswith(WORK_PREFIX):
        key = normalized
    elif normalized.startswith("works/"):
        key = f"/{normalized}"
    elif normalized.startswith("OL") and normalized.endswith("W"):
        key = f"{WORK_PREFIX}{normalized}"
    else:
        raise ValueError("Work OLID must be a work key ending with W.")
    return fetch_by_key(key, allowed_prefixes=(WORK_PREFIX,))


def fetch_author_by_olid(olid: str) -> dict:
    normalized = olid.strip()
    if not normalized:
        raise ValueError("OLID must be a non-empty string.")
    if normalized.startswith(AUTHOR_PREFIX):
        key = normalized
    elif normalized.startswith("authors/"):
        key = f"/{normalized}"
    elif normalized.startswith("OL") and normalized.endswith("A"):
        key = f"{AUTHOR_PREFIX}{normalized}"
    else:
        raise ValueError("Author OLID must end with A.")
    return fetch_by_key(key, allowed_prefixes=(AUTHOR_PREFIX,))


def _coerce_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def extract_work_fields(record: dict) -> dict:
    return {
        "olid": record.get("key"),
        "title": record.get("title") or "Unknown title",
    }


def extract_authors(record: dict) -> list[dict]:
    authors: list[dict] = []
    for entry in _coerce_list(record.get("authors")):
        if not isinstance(entry, dict):
            continue
        key = None
        name = None
        personal_name = None
        if "author" in entry and isinstance(entry["author"], dict):
            key = entry["author"].get("key")
        elif "key" in entry:
            key = entry.get("key")
        name = entry.get("name")
        personal_name = entry.get("personal_name")
        if not key:
            continue
        authors.append(
            {
                "key": key,
                "name": name,
                "personal_name": personal_name,
            }
        )
    return authors


def normalize_author_entries(
    entries: Iterable[dict],
) -> list[dict]:
    seen: set[str] = set()
    normalized: list[dict] = []
    for entry in entries:
        key = entry.get("key")
        if not isinstance(key, str) or not key.startswith(AUTHOR_PREFIX):
            continue
        if key in seen:
            continue
        seen.add(key)
        normalized.append(entry)
    return normalized
