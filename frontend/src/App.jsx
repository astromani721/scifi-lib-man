import { useEffect, useMemo, useState } from "react";
import "./App.css";

const PAGE_SIZE = 10;
const API_BASE =
  import.meta.env.VITE_API_BASE?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";
const STATUSES = ["read", "reading", "wishlist"];

function App() {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [statusMap, setStatusMap] = useState({});
  const [updating, setUpdating] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(total / PAGE_SIZE)),
    [total],
  );

  const fetchReadingList = async () => {
    const response = await fetch(`${API_BASE}/reading-list`);
    if (!response.ok) {
      throw new Error("Failed to load reading list.");
    }
    const data = await response.json();
    const map = {};
    for (const item of data) {
      if (item?.work_olid) {
        map[item.work_olid] = item.status;
      }
    }
    return map;
  };

  const runSearch = async (nextPage = 1) => {
    if (!query.trim()) {
      setResults([]);
      setTotal(0);
      setError("");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const url = new URL(`${API_BASE}/books/quick-search`);
      url.searchParams.set("q", query.trim());
      url.searchParams.set("limit", PAGE_SIZE.toString());
      url.searchParams.set("page", nextPage.toString());

      const [searchResponse, readingListMap] = await Promise.all([
        fetch(url.toString()),
        fetchReadingList(),
      ]);
      if (!searchResponse.ok) {
        throw new Error("Search failed. Try again.");
      }
      const payload = await searchResponse.json();
      setResults(payload.docs ?? []);
      setTotal(payload.numFound ?? 0);
      setStatusMap(readingListMap);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setTotal(0);
      setPage(1);
    }
  }, [query]);

  const handleSubmit = (event) => {
    event.preventDefault();
    const nextPage = 1;
    setPage(nextPage);
    runSearch(nextPage);
  };

  const handlePageChange = (direction) => {
    const nextPage = Math.min(
      totalPages,
      Math.max(1, page + direction),
    );
    if (nextPage === page) {
      return;
    }
    setPage(nextPage);
    runSearch(nextPage);
  };

  const updateStatus = async (workKey, nextStatus) => {
    const cleaned = workKey.replace(/^\//, "");
    const url = `${API_BASE}/reading-list/${cleaned}`;
    const hasEntry = Boolean(statusMap[workKey]);
    setUpdating((prev) => ({ ...prev, [workKey]: true }));
    try {
      const method = nextStatus
        ? hasEntry
          ? "PUT"
          : "POST"
        : "DELETE";
      const options = { method };
      if (nextStatus) {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify({ status: nextStatus });
      }
      const response = await fetch(url, options);
      if (!response.ok) {
        throw new Error("Failed to update status.");
      }
      setStatusMap((prev) => {
        const next = { ...prev };
        if (nextStatus) {
          next[workKey] = nextStatus;
        } else {
          delete next[workKey];
        }
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed.");
    } finally {
      setUpdating((prev) => ({ ...prev, [workKey]: false }));
    }
  };

  return (
    <div className="app">
      <header className="hero">
        <div className="hero__glow" />
        <p className="hero__eyebrow">Sci‑Fi Library Manager</p>
        <h1>Search the cosmos of books.</h1>
        <p className="hero__subhead">
          Quick-search Open Library works and see what’s already on your
          reading list.
        </p>
        <form className="search" onSubmit={handleSubmit}>
          <input
            aria-label="Search for books"
            placeholder="Search by title, author, subject..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit" disabled={loading}>
            {loading ? "Searching…" : "Search"}
          </button>
        </form>
      </header>

      <main className="results">
        <div className="results__meta">
          <span>
            {total > 0 ? `${total.toLocaleString()} results` : "No results yet"}
          </span>
          <span className="results__page">
            Page {page} of {totalPages}
          </span>
        </div>

        {error && <div className="notice notice--error">{error}</div>}

        <div className="results__table">
          <div className="results__row results__row--header">
            <span>Title</span>
            <span>Author</span>
            <span>Year</span>
            <span>Status</span>
          </div>
          {results.map((item) => {
            const key = item.key;
            const author =
              Array.isArray(item.author_name) && item.author_name.length
                ? item.author_name.join(", ")
                : "Unknown";
            const status = statusMap[key] || "New";
            const disabled = Boolean(updating[key]);
            return (
              <div className="results__row" key={key}>
                <div>
                  <div className="results__title">{item.title}</div>
                  <div className="results__key">{key}</div>
                </div>
                <div>{author}</div>
                <div>{item.first_publish_year ?? "—"}</div>
                <div className="results__status">
                  <select
                    className={`status-select status-select--${status}`}
                    value={status === "New" ? "" : status}
                    onChange={(event) =>
                      updateStatus(key, event.target.value)
                    }
                    disabled={disabled}
                  >
                    <option value="">New</option>
                    {STATUSES.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            );
          })}
        </div>

        <div className="pagination">
          <button
            type="button"
            onClick={() => handlePageChange(-1)}
            disabled={page <= 1 || loading}
          >
            Prev
          </button>
          <button
            type="button"
            onClick={() => handlePageChange(1)}
            disabled={page >= totalPages || loading}
          >
            Next
          </button>
        </div>
      </main>
    </div>
  );
}

export default App;
