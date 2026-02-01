from __future__ import annotations

from fastapi.testclient import TestClient

from scifi_lib_man.api import app


client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_search_requires_query() -> None:
    response = client.get("/books/search")
    assert response.status_code == 400
    assert "Provide at least one" in response.json()["detail"]


def test_search_success(monkeypatch) -> None:
    def fake_search_openlibrary(**_kwargs):
        return {"docs": [{"key": "/works/OL1W", "title": "Test"}], "numFound": 1}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get("/books/search", params={"author": "Ayn Rand"})
    assert response.status_code == 200
    assert response.json()["numFound"] == 1


def test_search_limit_validation(monkeypatch) -> None:
    def fake_search_openlibrary(**_kwargs):
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get("/books/search", params={"title": "Dune", "limit": 0})
    assert response.status_code == 422


def test_search_page_validation(monkeypatch) -> None:
    def fake_search_openlibrary(**_kwargs):
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get("/books/search", params={"title": "Dune", "page": 0})
    assert response.status_code == 422


def test_search_fields_default(monkeypatch) -> None:
    captured = {}

    def fake_search_openlibrary(**kwargs):
        captured.update(kwargs)
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get("/books/search", params={"title": "Dune"})
    assert response.status_code == 200
    assert captured["fields"] is None


def test_search_fields_custom(monkeypatch) -> None:
    captured = {}

    def fake_search_openlibrary(**kwargs):
        captured.update(kwargs)
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get(
        "/books/search",
        params=[("title", "Dune"), ("fields", "key"), ("fields", "title")],
    )
    assert response.status_code == 200
    assert captured["fields"] == ["key", "title"]


def test_search_supports_subject_and_language(monkeypatch) -> None:
    captured = {}

    def fake_search_openlibrary(**kwargs):
        captured.update(kwargs)
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get(
        "/books/search",
        params={
            "subject": "cyberpunk",
            "language": "eng",
            "subject_key": "science_fiction",
        },
    )
    assert response.status_code == 200
    assert captured["subject"] == "cyberpunk"
    assert captured["language"] == "eng"
    assert captured["subject_key"] == "science_fiction"


def test_search_year_range_conflict(monkeypatch) -> None:
    def fake_search_openlibrary(**_kwargs):
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get(
        "/books/search",
        params={"year": 1999, "year_from": 1990},
    )
    assert response.status_code == 400
    assert "Use either year" in response.json()["detail"]


def test_isbn_success(monkeypatch) -> None:
    def fake_fetch_by_isbn(_isbn: str):
        return {"isbn_13": ["9780143111580"], "title": "Test"}

    monkeypatch.setattr(
        "scifi_lib_man.api.fetch_by_isbn",
        fake_fetch_by_isbn,
    )

    response = client.get("/books/isbn/9780143111580")
    assert response.status_code == 200
    assert response.json()["title"] == "Test"


def test_isbn_not_found(monkeypatch) -> None:
    def fake_fetch_by_isbn(_isbn: str):
        raise ValueError("ISBN not found in Open Library.")

    monkeypatch.setattr(
        "scifi_lib_man.api.fetch_by_isbn",
        fake_fetch_by_isbn,
    )

    response = client.get("/books/isbn/0000000000")
    assert response.status_code == 404
    assert "ISBN not found" in response.json()["detail"]


def test_book_by_olid_edition_success(monkeypatch) -> None:
    def fake_fetch_book_by_olid(_olid: str):
        return {"key": "/books/OL123M", "title": "Test"}

    monkeypatch.setattr(
        "scifi_lib_man.api.fetch_book_by_olid",
        fake_fetch_book_by_olid,
    )

    response = client.get("/books/OL123M")
    assert response.status_code == 200
    assert response.json()["key"] == "/books/OL123M"


def test_book_by_olid_rejects_work() -> None:
    response = client.get("/books/OL123W")
    assert response.status_code == 404
    assert "edition key" in response.json()["detail"]


def test_book_by_olid_invalid_suffix() -> None:
    response = client.get("/books/OL123A")
    assert response.status_code == 404
    assert "edition key" in response.json()["detail"]


def test_author_by_olid_success(monkeypatch) -> None:
    def fake_fetch_author_by_olid(_olid: str):
        return {"key": "/authors/OL123A", "name": "Test"}

    monkeypatch.setattr(
        "scifi_lib_man.api.fetch_author_by_olid",
        fake_fetch_author_by_olid,
    )

    response = client.get("/authors/OL123A")
    assert response.status_code == 200
    assert response.json()["key"] == "/authors/OL123A"


def test_author_by_olid_invalid_suffix() -> None:
    response = client.get("/authors/OL123M")
    assert response.status_code == 404
    assert "Author OLID must end" in response.json()["detail"]


def test_reading_list_add_and_list(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCIFI_LIB_MAN_DB", str(tmp_path / "test.db"))

    def fake_fetch_work_by_olid(_olid: str):
        return {
            "key": "/works/OL1W",
            "title": "Test Book",
            "publish_date": "1969",
            "isbn_13": ["123"],
            "authors": [{"author": {"key": "/authors/OL1A"}}],
        }

    monkeypatch.setattr(
        "scifi_lib_man.api.fetch_work_by_olid",
        fake_fetch_work_by_olid,
    )

    response = client.post(
        "/reading-list/works/OL1W",
        json={"status": "wishlist"},
    )
    assert response.status_code == 200

    response = client.get("/reading-list", params={"status": "wishlist"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["work_olid"] == "/works/OL1W"


def test_reading_list_update(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCIFI_LIB_MAN_DB", str(tmp_path / "test.db"))

    def fake_fetch_work_by_olid(_olid: str):
        return {"key": "/works/OL2W", "title": "Test Book"}

    monkeypatch.setattr(
        "scifi_lib_man.api.fetch_work_by_olid",
        fake_fetch_work_by_olid,
    )

    response = client.post(
        "/reading-list/works/OL2W",
        json={"status": "wishlist"},
    )
    assert response.status_code == 200

    response = client.put(
        "/reading-list/works/OL2M",
        json={"status": "read", "rating": 4},
    )
    assert response.status_code == 404

    response = client.put(
        "/reading-list/works/OL2W",
        json={"status": "read", "rating": 4},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "read"


def test_reading_list_delete(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCIFI_LIB_MAN_DB", str(tmp_path / "test.db"))

    def fake_fetch_work_by_olid(_olid: str):
        return {"key": "/works/OL3W", "title": "Test Book"}

    monkeypatch.setattr(
        "scifi_lib_man.api.fetch_work_by_olid",
        fake_fetch_work_by_olid,
    )

    response = client.post(
        "/reading-list/works/OL3W",
        json={"status": "wishlist"},
    )
    assert response.status_code == 200

    response = client.delete("/reading-list/books/OL3W")
    assert response.status_code == 404

    response = client.delete("/reading-list/books/OL3M")
    assert response.status_code == 404

    response = client.delete("/reading-list/works/OL3W")
    assert response.status_code == 200
    assert response.json()["deleted"] is True


def test_award_search_unknown_award() -> None:
    response = client.get("/books/awards/unknown/search")
    assert response.status_code == 404
    assert "Unknown award" in response.json()["detail"]


def test_award_search_pulitzer_subjects(monkeypatch) -> None:
    captured = {}

    def fake_search_openlibrary(**kwargs):
        captured.update(kwargs)
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get("/books/awards/pulitzer/search")
    assert response.status_code == 200
    assert "subject_key:pulitzer_prize_winner" in captured["q"]
    assert "subject_key:pulitzer_prizes" in captured["q"]
    assert 'subject:"Pulitzer Prize"' in captured["q"]
    assert 'subject:"Pulitzer Prize Winner"' in captured["q"]
    assert 'subject:"Pulitzer Prizes"' in captured["q"]
    assert " OR " in captured["q"]


def test_award_search_booker_subjects(monkeypatch) -> None:
    captured = {}

    def fake_search_openlibrary(**kwargs):
        captured.update(kwargs)
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get("/books/awards/booker/search")
    assert response.status_code == 200
    assert "subject_key:man_booker_prize_winner" in captured["q"]
    assert 'subject:"Booker Prize"' in captured["q"]
    assert 'subject:"Man Booker Prize"' in captured["q"]
    assert 'subject:"Booker Prize Winner"' in captured["q"]
    assert 'subject:"Man Booker Prize Winner"' in captured["q"]
    assert " OR " in captured["q"]


def test_award_search_nobel_subjects(monkeypatch) -> None:
    captured = {}

    def fake_search_openlibrary(**kwargs):
        captured.update(kwargs)
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get("/books/awards/nobel/search")
    assert response.status_code == 200
    assert "subject_key:nobel_prize_winners" in captured["q"]
    assert "subject_key:nobel_prizes" in captured["q"]
    assert 'subject:"Nobel Prize"' in captured["q"]
    assert 'subject:"Nobel Prize winners"' in captured["q"]
    assert 'subject:"Nobel Prizes"' in captured["q"]
    assert " OR " in captured["q"]


def test_award_search_builds_query(monkeypatch) -> None:
    captured = {}

    def fake_search_openlibrary(**kwargs):
        captured.update(kwargs)
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get(
        "/books/awards/hugo/search",
        params={"author": "Ursula Le Guin", "year": 1969},
    )
    assert response.status_code == 200
    assert "subject_key:hugo_award_winner" in captured["q"]
    assert 'author:"Ursula Le Guin"' in captured["q"]
    assert "first_publish_year:1969" in captured["q"]


def test_award_search_subject_language(monkeypatch) -> None:
    captured = {}

    def fake_search_openlibrary(**kwargs):
        captured.update(kwargs)
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get(
        "/books/awards/hugo/search",
        params={
            "subject": "cyberpunk",
            "language": "eng",
            "subject_key": "science_fiction",
        },
    )
    assert response.status_code == 200
    assert "subject:cyberpunk" in captured["q"]
    assert "language:eng" in captured["q"]
    assert "subject_key:science_fiction" in captured["q"]


def test_award_search_nebula_subjects(monkeypatch) -> None:
    captured = {}

    def fake_search_openlibrary(**kwargs):
        captured.update(kwargs)
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get("/books/awards/nebula/search")
    assert response.status_code == 200
    assert "subject_key:nebula_award_winner" in captured["q"]
    assert 'subject:"Nebula Award"' in captured["q"]
    assert " OR " in captured["q"]


def test_award_search_locus_subjects(monkeypatch) -> None:
    captured = {}

    def fake_search_openlibrary(**kwargs):
        captured.update(kwargs)
        return {"docs": [], "numFound": 0}

    monkeypatch.setattr(
        "scifi_lib_man.api.search_openlibrary",
        fake_search_openlibrary,
    )

    response = client.get("/books/awards/locus/search")
    assert response.status_code == 200
    assert "subject_key:locus_award_winner" in captured["q"]
    assert 'subject:"Locus Award"' in captured["q"]
    assert 'subject:"Locus Awards"' in captured["q"]
    assert " OR " in captured["q"]
