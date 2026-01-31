from __future__ import annotations

import sqlite3

from scifi_lib_man import storage


def _connect(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    conn = storage.connect(str(db_path))
    storage.init_db(conn)
    return conn


def test_upsert_and_list(tmp_path) -> None:
    conn = _connect(tmp_path)
    storage.upsert_book(
        conn,
        olid="/works/OL1W",
        title="Test Book",
        publish_date="1969",
        num_pages=300,
    )
    storage.add_to_reading_list(
        conn,
        book_olid="/works/OL1W",
        status="wishlist",
        notes="Try this soon",
        rating=5,
    )
    conn.commit()

    entries = storage.get_reading_list(conn, status="wishlist")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["book_olid"] == "/works/OL1W"
    assert entry["title"] == "Test Book"


def test_invalid_status(tmp_path) -> None:
    conn = _connect(tmp_path)
    storage.upsert_book(conn, olid="/works/OL2W", title="Other")
    conn.commit()

    try:
        storage.add_to_reading_list(conn, book_olid="/works/OL2W", status="bad")
    except ValueError as exc:
        assert "status must be one of" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid status")
