from __future__ import annotations

"""Similarity search workflow for works.

Flow summary:
1) Normalize work OLID
2) Fetch work profile + metadata
3) Discover candidate works
4) Embed candidates in batches and store in ChromaDB
5) Query ChromaDB and rerank results
6) Stream SSE updates (status/progress/results/done)
"""

import json
import os
import time
from dataclasses import dataclass
from queue import Queue
from threading import Thread
from typing import Iterable, TypedDict

import requests
from langgraph.graph import END, StateGraph

from .catalog import fetch_author_by_olid, fetch_work_by_olid
from .config import CHROMA_COLLECTION, CHROMA_PERSIST_DIR, EMBEDDING_MODEL
from .openlibrary import WORK_PREFIX, search_openlibrary


class SimilarityState(TypedDict, total=False):
    work_olid: str
    work_record: dict
    work_profile: str
    work_metadata: dict
    candidates: list[dict]
    batch_index: int
    batch_size: int
    embedded_count: int
    max_candidates: int
    results: list[dict]
    has_more: bool
    options: dict
    time_budget_sec: int
    started_at: float


@dataclass
class SimilarityOptions:
    prefer_same_author: bool = False
    prefer_year_range: int | None = None
    max_candidates: int = 200
    batch_size: int = 25
    time_budget_sec: int = 15
    language: str | None = "eng"


def _normalize_work_key(value: str) -> str:
    trimmed = (value or "").strip()
    if not trimmed:
        raise ValueError("Work OLID must be provided.")
    if trimmed.startswith(WORK_PREFIX):
        if not trimmed.endswith("W"):
            raise ValueError("Work OLID must be a work key ending with W.")
        return trimmed
    if trimmed.startswith("works/"):
        if not trimmed.endswith("W"):
            raise ValueError("Work OLID must be a work key ending with W.")
        return f"/{trimmed}"
    if trimmed.startswith("OL") and trimmed.endswith("W"):
        return f"{WORK_PREFIX}{trimmed}"
    raise ValueError("Work OLID must be a /works/ key ending with W.")


def _coerce_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_description(record: dict) -> str | None:
    description = record.get("description")
    if isinstance(description, str):
        return description
    if isinstance(description, dict):
        value = description.get("value")
        if isinstance(value, str):
            return value
    return None


def _extract_awards(subjects: Iterable[str]) -> list[str]:
    awards: set[str] = set()
    for subject in subjects:
        lowered = subject.lower()
        if lowered.startswith("award:"):
            chunk = subject.split(":", 1)[-1]
            label = chunk.split("=", 1)[0].replace("_", " ").strip()
            if label:
                awards.add(label.title())
            continue
        if "award" in lowered:
            awards.add(subject.strip())
    return sorted(awards)


def _normalize_year(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) >= 4:
            return int(digits[:4])
    return None


def _format_list(items: Iterable[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return ", ".join(cleaned)


def _build_work_profile(record: dict, authors: list[str]) -> tuple[str, dict]:
    subjects = [s for s in _coerce_list(record.get("subjects")) if isinstance(s, str)]
    subject_keys = [
        s for s in _coerce_list(record.get("subject_key") or record.get("subject_keys"))
        if isinstance(s, str)
    ]
    subject_places = [
        s for s in _coerce_list(record.get("subject_places")) if isinstance(s, str)
    ]
    subject_people = [
        s for s in _coerce_list(record.get("subject_people")) if isinstance(s, str)
    ]
    subject_times = [
        s for s in _coerce_list(record.get("subject_times")) if isinstance(s, str)
    ]
    awards = _extract_awards(subjects)
    year = _normalize_year(record.get("first_publish_date"))
    description = _extract_description(record)

    profile_lines = [
        f"Title: {record.get('title') or 'Unknown title'}",
        f"Authors: {_format_list(authors) or 'Unknown'}",
    ]
    if description:
        profile_lines.append(f"Description: {description}")
    if subjects:
        profile_lines.append(f"Subjects: {_format_list(subjects)}")
    if subject_places:
        profile_lines.append(f"Subject places: {_format_list(subject_places)}")
    if subject_people:
        profile_lines.append(f"Subject people: {_format_list(subject_people)}")
    if subject_times:
        profile_lines.append(f"Subject times: {_format_list(subject_times)}")
    if awards:
        profile_lines.append(f"Awards: {_format_list(awards)}")
    if year is not None:
        profile_lines.append(f"Year: {year}")

    metadata = {
        "title": record.get("title") or "Unknown title",
        "authors": json.dumps(authors),
        "subjects": json.dumps(subjects),
        "subject_keys": json.dumps(subject_keys),
        "subject_places": json.dumps(subject_places),
        "subject_people": json.dumps(subject_people),
        "subject_times": json.dumps(subject_times),
        "awards": json.dumps(awards),
        "year": year,
        "olid": record.get("key"),
        "source": "similar",
    }
    metadata = {key: value for key, value in metadata.items() if value is not None}

    return "\n".join(profile_lines), metadata


def _fetch_author_names(record: dict) -> list[str]:
    authors: list[str] = []
    for entry in _coerce_list(record.get("authors"))[:3]:
        if not isinstance(entry, dict):
            continue
        author_key = None
        if "author" in entry and isinstance(entry["author"], dict):
            author_key = entry["author"].get("key")
        elif "key" in entry:
            author_key = entry.get("key")
        if not isinstance(author_key, str):
            continue
        try:
            author_record = fetch_author_by_olid(author_key)
        except ValueError:
            continue
        name = author_record.get("name") or author_record.get("personal_name")
        if isinstance(name, str) and name.strip():
            authors.append(name.strip())
    return authors


def _get_chroma_collection():
    os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
    from chromadb import PersistentClient

    client = PersistentClient(path=CHROMA_PERSIST_DIR)
    return client.get_or_create_collection(CHROMA_COLLECTION)


def _embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    def _call() -> list[list[float]]:
        response = requests.post(
            "http://localhost:11434/api/embed",
            json={"model": EMBEDDING_MODEL, "input": texts},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("embeddings", [])

    return _with_retries(_call, attempts=3, base_delay=0.6)


def _with_retries(fn, *, attempts: int, base_delay: float):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # pragma: no cover - retry path
            last_error = exc
            if attempt == attempts:
                raise
            time.sleep(base_delay * attempt)
    if last_error:
        raise last_error
    return None


def _encode_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _emit(queue: Queue, event: str, data: dict) -> None:
    queue.put(_encode_sse(event, data))


def _discover_candidates(
    *,
    title: str,
    subjects: list[str],
    subject_keys: list[str],
    authors: list[str],
    language: str | None,
    max_candidates: int,
    time_budget_sec: int,
    started_at: float,
    exclude_olid: str | None,
) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()
    subject_terms = [s for s in subject_keys if s.strip()][:5]
    if not subject_terms and subjects:
        subject_terms = [_slugify_subject(s) for s in subjects if s.strip()][:5]
    pages = 0
    while len(candidates) < max_candidates and subject_terms:
        if time.time() - started_at > time_budget_sec:
            break
        subject_clause = " OR ".join(
            f"subject_key:{_quote_query_term(term)}" for term in subject_terms
        )
        try:
            response = _with_retries(
                lambda: search_openlibrary(
                    q=f"({subject_clause})",
                    language=language,
                    limit=min(100, max_candidates - len(candidates)),
                    page=pages + 1,
                    fields=[
                        "key",
                        "title",
                        "author_name",
                        "first_publish_year",
                        "subject",
                    ],
                ),
                attempts=3,
                base_delay=0.5,
            )
        except Exception:
            break
        pages += 1
        docs = response.get("docs", [])
        if not docs:
            break
        for item in docs:
            key = item.get("key")
            if not isinstance(key, str) or not key.startswith(WORK_PREFIX):
                continue
            if exclude_olid and key == exclude_olid:
                continue
            if key in seen:
                continue
            seen.add(key)
            candidates.append(item)
            if len(candidates) >= max_candidates:
                break
        if pages >= 2:
            break

    if not candidates:
        author_term = _quote_query_term(authors[0]) if authors else None
        title_term = _quote_query_term(title) if title else None
        if title_term and author_term:
            fallback_q = f"title:{title_term} AND author:{author_term}"
        elif title_term:
            fallback_q = f"title:{title_term}"
        elif author_term:
            fallback_q = f"author:{author_term}"
        else:
            fallback_q = None
        if fallback_q:
            try:
                response = _with_retries(
                    lambda: search_openlibrary(
                        q=fallback_q,
                        language=language,
                        limit=min(100, max_candidates - len(candidates)),
                        page=1,
                        fields=[
                            "key",
                            "title",
                            "author_name",
                            "first_publish_year",
                            "subject",
                        ],
                    ),
                    attempts=2,
                    base_delay=0.4,
                )
            except Exception:
                response = {}
            for item in response.get("docs", []):
                key = item.get("key")
                if not isinstance(key, str) or not key.startswith(WORK_PREFIX):
                    continue
                if exclude_olid and key == exclude_olid:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(item)
                if len(candidates) >= max_candidates:
                    break
    return candidates


def _compute_overlap(a: Iterable[str], b: Iterable[str]) -> float:
    set_a = {item for item in a if item}
    set_b = {item for item in b if item}
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _parse_json_list(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, str)]
    return []


def _score_results(
    results: list[dict],
    query_metadata: dict,
    options: SimilarityOptions,
) -> list[dict]:
    query_subjects = _parse_json_list(query_metadata.get("subjects"))
    query_awards = _parse_json_list(query_metadata.get("awards"))
    query_year = query_metadata.get("year")
    query_authors = _parse_json_list(query_metadata.get("authors"))
    query_id = query_metadata.get("olid")

    scored: list[dict] = []
    for item in results:
        metadata = item.get("metadata", {})
        if query_id and metadata.get("olid") == query_id:
            continue
        subjects = _parse_json_list(metadata.get("subjects"))
        awards = _parse_json_list(metadata.get("awards"))
        year = metadata.get("year")
        authors = _parse_json_list(metadata.get("authors"))

        subject_overlap = _compute_overlap(query_subjects, subjects)
        award_overlap = _compute_overlap(query_awards, awards)
        year_proximity = 0.0
        if isinstance(query_year, int) and isinstance(year, int):
            delta = abs(query_year - year)
            year_proximity = max(0.0, 1.0 - min(delta, 50) / 50.0)

        score = (
            0.70 * item.get("similarity", 0.0)
            + 0.15 * subject_overlap
            + 0.10 * award_overlap
            + 0.05 * year_proximity
        )

        if options.prefer_same_author and query_authors and authors:
            if set(query_authors) & set(authors):
                score += 0.08

        if options.prefer_year_range and isinstance(query_year, int) and isinstance(year, int):
            if abs(query_year - year) <= options.prefer_year_range:
                score += 0.05
            score -= 0.05 * year_proximity

        reason = _build_reason(
            query_subjects=query_subjects,
            query_awards=query_awards,
            query_year=query_year,
            query_authors=query_authors,
            subjects=subjects,
            awards=awards,
            year=year,
            authors=authors,
            options=options,
        )
        scored.append(
            {
                "id": metadata.get("olid"),
                "title": metadata.get("title"),
                "authors": authors,
                "year": year,
                "score": round(score, 4),
                "subjects": subjects,
                "awards": awards,
                "reason": reason,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored


def _slugify_subject(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in value)
    return "_".join(part for part in cleaned.split() if part)


def _quote_query_term(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return '""'
    escaped = trimmed.replace('"', '\\"')
    if " " in escaped or ":" in escaped:
        return f'"{escaped}"'
    return escaped


def _build_reason(
    *,
    query_subjects: list[str],
    query_awards: list[str],
    query_year: int | None,
    query_authors: list[str],
    subjects: list[str],
    awards: list[str],
    year: int | None,
    authors: list[str],
    options: SimilarityOptions,
) -> str:
    parts: list[str] = []
    shared_subjects = [s for s in subjects if s in set(query_subjects)]
    if shared_subjects:
        parts.append(f"Shared subjects: {', '.join(shared_subjects[:3])}")
    shared_awards = [a for a in awards if a in set(query_awards)]
    if shared_awards:
        parts.append(f"Awards overlap: {', '.join(shared_awards[:2])}")
    if (
        isinstance(query_year, int)
        and isinstance(year, int)
        and abs(query_year - year) <= 15
    ):
        parts.append("Similar era")
    if options.prefer_same_author and query_authors and authors:
        if set(query_authors) & set(authors):
            parts.append("Same author")
    return "; ".join(parts) if parts else "Semantic similarity"


def _build_graph(emit):
    graph = StateGraph(SimilarityState)

    def parse_query(state: SimilarityState) -> SimilarityState:
        # Validate and normalize the work OLID early.
        emit("status", {"phase": "parse_query", "message": "Normalizing work key"})
        work_olid = _normalize_work_key(state["work_olid"])
        return {"work_olid": work_olid}

    def fetch_profile(state: SimilarityState) -> SimilarityState:
        # Fetch the work and build the embedding profile + metadata.
        emit("status", {"phase": "fetch_profile", "message": "Fetching work metadata"})
        record = fetch_work_by_olid(state["work_olid"])
        authors = _fetch_author_names(record)
        profile, metadata = _build_work_profile(record, authors)
        metadata["source"] = "query"
        return {
            "work_record": record,
            "work_profile": profile,
            "work_metadata": metadata,
            "work_authors": authors,
        }

    def discover_candidates(state: SimilarityState) -> SimilarityState:
        # Candidate discovery (subject_key OR query, fallback to title+author).
        emit(
            "status",
            {"phase": "discover_candidates", "message": "Discovering candidates"},
        )
        record = state["work_record"]
        subjects = [
            s for s in _coerce_list(record.get("subjects")) if isinstance(s, str)
        ]
        subject_keys = [
            s
            for s in _coerce_list(
                record.get("subject_key") or record.get("subject_keys")
            )
            if isinstance(s, str)
        ]
        title = record.get("title") or ""
        options = state["options"]
        candidates = _discover_candidates(
            title=title,
            subjects=subjects,
            subject_keys=subject_keys,
            authors=state.get("work_authors", []),
            language=options.language,
            max_candidates=state["max_candidates"],
            time_budget_sec=state["time_budget_sec"],
            started_at=state["started_at"],
            exclude_olid=state["work_olid"],
        )
        emit(
            "progress",
            {
                "embedded": state.get("embedded_count", 0),
                "total": len(candidates),
                "batch_size": state["batch_size"],
            },
        )
        if not candidates:
            emit(
                "status",
                {
                    "phase": "discover_candidates",
                    "message": "No candidates found yet. Try another title or expand filters.",
                },
            )
        emit(
            "status",
            {
                "phase": "discover_candidates",
                "message": f"Found {len(candidates)} candidates",
            },
        )
        return {"candidates": candidates, "batch_index": 0}

    def embed_batch(state: SimilarityState) -> SimilarityState:
        # Embed and upsert one batch of candidates into ChromaDB.
        candidates = state["candidates"]
        batch_index = state["batch_index"]
        batch_size = state["batch_size"]
        start = batch_index * batch_size
        end = min(len(candidates), start + batch_size)
        batch = candidates[start:end]
        if not batch:
            return {"has_more": False}

        collection = _get_chroma_collection()
        ids = [item["key"] for item in batch if "key" in item]
        existing = collection.get(ids=ids, include=[])
        existing_ids = set(existing.get("ids", []))

        texts: list[str] = []
        metadatas: list[dict] = []
        new_ids: list[str] = []
        for item in batch:
            key = item.get("key")
            if not isinstance(key, str) or key in existing_ids:
                continue
            try:
                record = fetch_work_by_olid(key)
            except ValueError:
                continue
            authors = _fetch_author_names(record)
            profile, metadata = _build_work_profile(record, authors)
            metadata["source"] = "similar"
            texts.append(profile)
            metadatas.append(metadata)
            new_ids.append(key)

        if texts:
            embeddings = _embed_texts(texts)
            if embeddings:
                collection.add(
                    ids=new_ids,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    documents=texts,
                )

        embedded_count = state.get("embedded_count", 0) + len(new_ids)
        emit(
            "progress",
            {
                "embedded": embedded_count,
                "total": len(candidates),
                "batch_size": batch_size,
            },
        )

        has_more = end < len(candidates)
        return {
            "batch_index": batch_index + 1,
            "embedded_count": embedded_count,
            "has_more": has_more,
        }

    def retrieve_similar(state: SimilarityState) -> SimilarityState:
        # Query ChromaDB with the work embedding and rerank results.
        emit("status", {"phase": "rank", "message": "Ranking similar works"})
        collection = _get_chroma_collection()
        query_embedding = _embed_texts([state["work_profile"]])
        if not query_embedding:
            return {"results": []}
        query = collection.query(
            query_embeddings=query_embedding,
            n_results=10,
            include=["metadatas", "distances"],
        )
        results: list[dict] = []
        for metadata, distance in zip(query.get("metadatas", [[]])[0], query.get("distances", [[]])[0]):
            similarity = 1.0 - float(distance)
            results.append({"metadata": metadata, "similarity": similarity})

        scored = _score_results(results, state["work_metadata"], state["options"])
        if os.getenv("SCIFI_LOG_SIMILARITY") == "1":
            for item in scored[:10]:
                title = item.get("title") or "Unknown"
                reason = item.get("reason") or ""
                print(f"Similar: {title} -> {reason}")
        emit("results", {"items": scored, "refined": True})
        return {"results": scored}

    def stream_update(state: SimilarityState) -> SimilarityState:
        # Emit completion event when no more batches are left.
        if not state.get("has_more"):
            emit(
                "done",
                {
                    "total_candidates": len(state.get("candidates", [])),
                    "embedded": state.get("embedded_count", 0),
                    "final_count": len(state.get("results", [])),
                },
            )
        return {}

    graph.add_node("parse_query", parse_query)
    graph.add_node("fetch_profile", fetch_profile)
    graph.add_node("discover_candidates", discover_candidates)
    graph.add_node("embed_batch", embed_batch)
    graph.add_node("retrieve_similar", retrieve_similar)
    graph.add_node("stream_update", stream_update)

    # Main flow with a loop for batch embedding.
    graph.set_entry_point("parse_query")
    graph.add_edge("parse_query", "fetch_profile")
    graph.add_edge("fetch_profile", "discover_candidates")
    graph.add_edge("discover_candidates", "embed_batch")
    graph.add_edge("embed_batch", "retrieve_similar")
    graph.add_edge("retrieve_similar", "stream_update")
    graph.add_conditional_edges(
        "stream_update",
        lambda state: "embed_batch" if state.get("has_more") else END,
    )

    return graph.compile()


def start_similarity_stream(
    *,
    work_olid: str,
    options: SimilarityOptions,
) -> Iterable[str]:
    queue: Queue = Queue()

    def emit(event: str, data: dict) -> None:
        _emit(queue, event, data)

    def run() -> None:
        emit("status", {"phase": "start", "message": "Starting similarity search"})
        try:
            graph = _build_graph(emit)
            graph.invoke(
                {
                    "work_olid": work_olid,
                    "options": options,
                    "batch_size": options.batch_size,
                    "max_candidates": options.max_candidates,
                    "time_budget_sec": options.time_budget_sec,
                    "started_at": time.time(),
                    "embedded_count": 0,
                }
            )
        except Exception as exc:  # pragma: no cover - stream error
            emit("error", {"message": str(exc), "recoverable": True})
        finally:
            queue.put(None)

    thread = Thread(target=run, daemon=True)
    thread.start()

    while True:
        item = queue.get()
        if item is None:
            break
        yield item
