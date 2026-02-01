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
        CREATE TABLE IF NOT EXISTS works (
            olid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            first_publish_year INTEGER
        );

        CREATE TABLE IF NOT EXISTS authors (
            olid TEXT PRIMARY KEY,
            name TEXT
        );

        CREATE TABLE IF NOT EXISTS work_authors (
            work_olid TEXT NOT NULL,
            author_olid TEXT NOT NULL,
            author_order INTEGER,
            PRIMARY KEY (work_olid, author_olid),
            FOREIGN KEY (work_olid) REFERENCES works(olid) ON DELETE CASCADE,
            FOREIGN KEY (author_olid) REFERENCES authors(olid) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reading_list_works (
            work_olid TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('read', 'reading', 'wishlist')),
            added_at TEXT NOT NULL DEFAULT (datetime('now')),
            notes TEXT,
            rating INTEGER,
            FOREIGN KEY (work_olid) REFERENCES works(olid) ON DELETE CASCADE
        );
        """
    )


def upsert_work(
    conn: sqlite3.Connection,
    *,
    olid: str,
    title: str,
    first_publish_year: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO works (
            olid,
            title,
            first_publish_year
        )
        VALUES (?, ?, ?)
        ON CONFLICT(olid) DO UPDATE SET
            title = excluded.title,
            first_publish_year = excluded.first_publish_year
        """,
        (
            olid,
            title,
            first_publish_year,
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


def add_work_author(
    conn: sqlite3.Connection,
    *,
    work_olid: str,
    author_olid: str,
    author_order: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO work_authors (work_olid, author_olid, author_order)
        VALUES (?, ?, ?)
        """,
        (work_olid, author_olid, author_order),
    )


def add_to_reading_list(
    conn: sqlite3.Connection,
    *,
    work_olid: str,
    status: str,
    notes: str | None = None,
    rating: int | None = None,
) -> None:
    if status not in READING_STATUSES:
        raise ValueError("status must be one of: read, reading, wishlist.")
    conn.execute(
        """
        INSERT INTO reading_list_works (work_olid, status, notes, rating)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(work_olid) DO UPDATE SET
            status = excluded.status,
            notes = excluded.notes,
            rating = excluded.rating
        """,
        (work_olid, status, notes, rating),
    )


def remove_from_reading_list(conn: sqlite3.Connection, *, work_olid: str) -> None:
    conn.execute(
        "DELETE FROM reading_list_works WHERE work_olid = ?",
        (work_olid,),
    )


def get_reading_list(
    conn: sqlite3.Connection, *, status: str | None = None
) -> list[dict]:
    if status is not None and status not in READING_STATUSES:
        raise ValueError("status must be one of: read, reading, wishlist.")
    query = """
        SELECT
            rl.work_olid,
            rl.status,
            rl.added_at,
            rl.notes,
            rl.rating,
            w.title,
            w.first_publish_year
        FROM reading_list_works rl
        JOIN works w ON w.olid = rl.work_olid
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
            SELECT wa.author_olid, a.name
            FROM work_authors wa
            LEFT JOIN authors a ON a.olid = wa.author_olid
            WHERE wa.work_olid = ?
            ORDER BY wa.author_order ASC
            """,
            (row["work_olid"],),
        ).fetchall()
        author_olids = [author_row["author_olid"] for author_row in author_rows]
        author_names = [author_row["name"] for author_row in author_rows if author_row["name"]]
        results.append(
            {
                "work_olid": row["work_olid"],
                "status": row["status"],
                "added_at": row["added_at"],
                "notes": row["notes"],
                "rating": row["rating"],
                "title": row["title"],
                "first_publish_year": row["first_publish_year"],
                "author_olids": author_olids,
                "author_names": author_names,
            }
        )
    return results


def get_reading_list_entry(conn: sqlite3.Connection, *, work_olid: str) -> dict | None:
    row = conn.execute(
        "SELECT work_olid, status, notes, rating FROM reading_list_works WHERE work_olid = ?",
        (work_olid,),
    ).fetchone()
    if row is None:
        return None
    return {
        "work_olid": row["work_olid"],
        "status": row["status"],
        "notes": row["notes"],
        "rating": row["rating"],
    }
