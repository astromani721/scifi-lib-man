from fastapi.testclient import TestClient

import scifi_lib_man.api as api
from scifi_lib_man.similarity import SimilarityOptions, _score_results


def test_similarity_stream_sse(monkeypatch):
    def fake_stream(*_args, **_kwargs):
        yield 'event: status\ndata: {"message": "ok"}\n\n'
        yield 'event: done\ndata: {"final_count": 1}\n\n'

    monkeypatch.setattr(api, "start_similarity_stream", lambda **_: fake_stream())
    client = TestClient(api.app)

    response = client.get(
        "/works/similar/stream",
        params={"work_olid": "/works/OL12345W", "prefer_same_author": "true"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: status" in response.text
    assert "event: done" in response.text


def test_score_results_boosts_author_and_year():
    query_metadata = {
        "olid": "/works/OL1W",
        "subjects": '["Science fiction"]',
        "awards": '["Hugo Award"]',
        "authors": '["Author A"]',
        "year": 1984,
    }
    options = SimilarityOptions(prefer_same_author=True, prefer_year_range=10)

    results = [
        {
            "metadata": {
                "olid": "/works/OL2W",
                "title": "Similar Work",
                "authors": '["Author A"]',
                "subjects": '["Science fiction"]',
                "awards": '["Hugo Award"]',
                "year": 1980,
            },
            "similarity": 0.8,
        },
        {
            "metadata": {
                "olid": "/works/OL3W",
                "title": "Far Work",
                "authors": '["Author B"]',
                "subjects": '["Fantasy"]',
                "awards": '[]',
                "year": 1950,
            },
            "similarity": 0.8,
        },
    ]

    scored = _score_results(results, query_metadata, options)
    assert scored[0]["id"] == "/works/OL2W"
    assert scored[0]["score"] > scored[1]["score"]


def test_score_results_year_proximity_default():
    query_metadata = {
        "olid": "/works/OL1W",
        "subjects": "[]",
        "awards": "[]",
        "authors": "[]",
        "year": 2000,
    }
    options = SimilarityOptions()

    results = [
        {
            "metadata": {
                "olid": "/works/OL2W",
                "title": "Near Work",
                "authors": "[]",
                "subjects": "[]",
                "awards": "[]",
                "year": 1998,
            },
            "similarity": 0.6,
        },
        {
            "metadata": {
                "olid": "/works/OL3W",
                "title": "Far Work",
                "authors": "[]",
                "subjects": "[]",
                "awards": "[]",
                "year": 1950,
            },
            "similarity": 0.6,
        },
    ]

    scored = _score_results(results, query_metadata, options)
    assert scored[0]["id"] == "/works/OL2W"
