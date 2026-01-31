from __future__ import annotations

import os
import sqlite3
from collections.abc import Sequence


READING_STATUSES = ("read", "reading", "wishlist")
DEFAULT_DB_PATH = "data/scifi-lib-man.db"


def get_db_path() -> str:
    return os.environ.get("SCIFI_LIB_MAN_DB", DEFAULT_DB_PATH)


def connect(db_path: str | None = None) -> sqlite3.Connection:
    resolved_path = db_path or get_db_path()
    if resolved_path != ":memory:":
        directory = os.path.dirname(resolved_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(resolved_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS books (
            olid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            publish_date TEXT,
            num_pages INTEGER
        );

        CREATE TABLE IF NOT EXISTS authors (
            olid TEXT PRIMARY KEY,
            name TEXT
        );

        CREATE TABLE IF NOT EXISTS book_authors (
            book_olid TEXT NOT NULL,
            author_olid TEXT NOT NULL,
            author_order INTEGER,
            PRIMARY KEY (book_olid, author_olid),
            FOREIGN KEY (book_olid) REFERENCES books(olid) ON DELETE CASCADE,
            FOREIGN KEY (author_olid) REFERENCES authors(olid) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reading_list (
            olid TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('read', 'reading', 'wishlist')),
            added_at TEXT NOT NULL DEFAULT (datetime('now')),
            notes TEXT,
            rating INTEGER,
            FOREIGN KEY (olid) REFERENCES books(olid) ON DELETE CASCADE
        );
        """
    )


def upsert_book(
    conn: sqlite3.Connection,
    *,
    olid: str,
    title: str,
    publish_date: str | None = None,
    num_pages: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO books (
            olid,
            title,
            publish_date,
            num_pages
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(olid) DO UPDATE SET
            title = excluded.title,
            publish_date = excluded.publish_date,
            num_pages = excluded.num_pages
        """,
        (
            olid,
            title,
            publish_date,
            num_pages,
        ),
    )


def upsert_author(
    conn: sqlite3.Connection,
    *,
    olid: str,
    name: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO authors (olid, name)
        VALUES (?, ?)
        ON CONFLICT(olid) DO UPDATE SET
            name = excluded.name
        """,
        (olid, name),
    )


def add_book_author(
    conn: sqlite3.Connection,
    *,
    book_olid: str,
    author_olid: str,
    author_order: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO book_authors (book_olid, author_olid, author_order)
        VALUES (?, ?, ?)
        """,
        (book_olid, author_olid, author_order),
    )


def add_to_reading_list(
    conn: sqlite3.Connection,
    *,
    book_olid: str,
    status: str,
    notes: str | None = None,
    rating: int | None = None,
) -> None:
    if status not in READING_STATUSES:
        raise ValueError("status must be one of: read, reading, wishlist.")
    conn.execute(
        """
        INSERT INTO reading_list (olid, status, notes, rating)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(olid) DO UPDATE SET
            status = excluded.status,
            notes = excluded.notes,
            rating = excluded.rating
        """,
        (book_olid, status, notes, rating),
    )


def remove_from_reading_list(conn: sqlite3.Connection, *, book_olid: str) -> None:
    conn.execute(
        "DELETE FROM reading_list WHERE olid = ?",
        (book_olid,),
    )


def get_reading_list(
    conn: sqlite3.Connection, *, status: str | None = None
) -> list[dict]:
    if status is not None and status not in READING_STATUSES:
        raise ValueError("status must be one of: read, reading, wishlist.")
    query = """
        SELECT
            rl.olid,
            rl.status,
            rl.added_at,
            rl.notes,
            rl.rating,
            b.title,
            b.publish_date,
            b.num_pages
        FROM reading_list rl
        JOIN books b ON b.olid = rl.olid
    """
    params: Sequence[object] = ()
    if status:
        query += " WHERE rl.status = ?"
        params = (status,)
    query += " ORDER BY rl.added_at DESC"

    rows = conn.execute(query, params).fetchall()
    results: list[dict] = []
    for row in rows:
        author_rows = conn.execute(
            """
            SELECT author_olid
            FROM book_authors
            WHERE book_olid = ?
            ORDER BY author_order ASC
            """,
            (row["olid"],),
        ).fetchall()
        author_olids = [author_row["author_olid"] for author_row in author_rows]
        results.append(
            {
                "book_olid": row["olid"],
                "status": row["status"],
                "added_at": row["added_at"],
                "notes": row["notes"],
                "rating": row["rating"],
                "title": row["title"],
                "publish_date": row["publish_date"],
                "num_pages": row["num_pages"],
                "author_olids": author_olids,
            }
        )
    return results


def get_reading_list_entry(
    conn: sqlite3.Connection, *, book_olid: str
) -> dict | None:
    row = conn.execute(
        "SELECT olid, status, notes, rating FROM reading_list WHERE olid = ?",
        (book_olid,),
    ).fetchone()
    if row is None:
        return None
    return {
        "book_olid": row["olid"],
        "status": row["status"],
        "notes": row["notes"],
        "rating": row["rating"],
    }
