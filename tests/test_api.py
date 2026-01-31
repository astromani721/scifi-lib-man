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


def test_award_search_unknown_award() -> None:
    response = client.get("/books/awards/unknown/search")
    assert response.status_code == 404
    assert "Unknown award" in response.json()["detail"]


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
    assert "author:\"Ursula Le Guin\"" in captured["q"]
    assert "first_publish_year:1969" in captured["q"]


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
    assert "subject:\"Nebula Award\"" in captured["q"]
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
    assert "subject:\"Locus Award\"" in captured["q"]
    assert "subject:\"Locus Awards\"" in captured["q"]
    assert " OR " in captured["q"]
