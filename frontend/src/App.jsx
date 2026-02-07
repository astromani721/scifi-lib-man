import { useEffect, useMemo, useRef, useState } from "react";
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
  const [readingList, setReadingList] = useState([]);
  const [activeTab, setActiveTab] = useState("search");
  const [updating, setUpdating] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [similarWork, setSimilarWork] = useState(null);
  const [similarResults, setSimilarResults] = useState([]);
  const [similarStatus, setSimilarStatus] = useState("");
  const [similarProgress, setSimilarProgress] = useState(null);
  const [similarError, setSimilarError] = useState("");
  const [preferSameAuthor, setPreferSameAuthor] = useState(false);
  const [preferYearRange, setPreferYearRange] = useState(false);
  const [yearRange, setYearRange] = useState(20);
  const [statusDots, setStatusDots] = useState("");
  const [similarBusy, setSimilarBusy] = useState(false);
  const similarStreamRef = useRef(null);
  const statusTimerRef = useRef(null);

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
    setReadingList(data);
    return map;
  };

  const refreshReadingList = async () => {
    try {
      const map = await fetchReadingList();
      setStatusMap(map);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load list.");
    }
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
    refreshReadingList();
  }, []);

  useEffect(() => {
    return () => {
      if (similarStreamRef.current) {
        similarStreamRef.current.close();
      }
      if (statusTimerRef.current) {
        clearInterval(statusTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!similarStatus || !similarBusy) {
      setStatusDots("");
      if (statusTimerRef.current) {
        clearInterval(statusTimerRef.current);
        statusTimerRef.current = null;
      }
      return;
    }
    if (statusTimerRef.current) {
      return;
    }
    statusTimerRef.current = setInterval(() => {
      setStatusDots((prev) => {
        if (prev.length >= 3) {
          return ".";
        }
        return prev + ".";
      });
    }, 600);
    return () => {
      if (statusTimerRef.current) {
        clearInterval(statusTimerRef.current);
        statusTimerRef.current = null;
      }
    };
  }, [similarStatus]);

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

  const updateStatus = async (workKey, nextStatus, year) => {
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
        options.body = JSON.stringify({
          status: nextStatus,
          first_publish_year: year,
        });
      }
      const response = await fetch(url, options);
      if (!response.ok) {
        throw new Error("Failed to update status.");
      }
      await refreshReadingList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed.");
    } finally {
      setUpdating((prev) => ({ ...prev, [workKey]: false }));
    }
  };

  const updateNotesRating = async (workKey, nextNotes, nextRating) => {
    const cleaned = workKey.replace(/^\//, "");
    const url = `${API_BASE}/reading-list/${cleaned}`;
    setUpdating((prev) => ({ ...prev, [workKey]: true }));
    try {
      const response = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: statusMap[workKey],
          notes: nextNotes,
          rating: nextRating,
        }),
      });
      if (!response.ok) {
        throw new Error("Failed to update entry.");
      }
      await refreshReadingList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed.");
    } finally {
      setUpdating((prev) => ({ ...prev, [workKey]: false }));
    }
  };

  const deleteEntry = async (workKey) => {
    const cleaned = workKey.replace(/^\//, "");
    const url = `${API_BASE}/reading-list/${cleaned}`;
    setUpdating((prev) => ({ ...prev, [workKey]: true }));
    try {
      const response = await fetch(url, { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Failed to delete entry.");
      }
      await refreshReadingList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setUpdating((prev) => ({ ...prev, [workKey]: false }));
    }
  };

  const startSimilarStream = (work) => {
    if (!work?.key) {
      return;
    }
    if (similarStreamRef.current) {
      similarStreamRef.current.close();
    }
    setSimilarWork(work);
    setSimilarResults([]);
    setSimilarStatus("Starting similarity search…");
    setSimilarProgress(null);
    setSimilarError("");
    setStatusDots("");
    setSimilarBusy(true);
    setActiveTab("similar");

    const url = new URL(`${API_BASE}/works/similar/stream`);
    url.searchParams.set("work_olid", work.key);
    url.searchParams.set("prefer_same_author", preferSameAuthor.toString());
    if (preferYearRange) {
      url.searchParams.set("prefer_year_range", yearRange.toString());
    }

    const eventSource = new EventSource(url.toString());
    similarStreamRef.current = eventSource;

    eventSource.addEventListener("status", (event) => {
      const payload = JSON.parse(event.data);
      setSimilarStatus(payload.message || "");
      setStatusDots("");
    });

    eventSource.addEventListener("progress", (event) => {
      const payload = JSON.parse(event.data);
      setSimilarProgress(payload);
    });

    eventSource.addEventListener("results", (event) => {
      const payload = JSON.parse(event.data);
      setSimilarResults(payload.items || []);
    });

    eventSource.addEventListener("done", () => {
      setSimilarStatus("Refined results ready.");
      setStatusDots("");
      setSimilarBusy(false);
      eventSource.close();
    });

    eventSource.addEventListener("error", (event) => {
      const payload = event?.data ? JSON.parse(event.data) : null;
      setSimilarError(
        payload?.message || "Similarity search failed. Try again later.",
      );
      setSimilarStatus("");
      setStatusDots("");
      setSimilarBusy(false);
      eventSource.close();
    });
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
        <div className="tabs">
          <button
            type="button"
            className={activeTab === "search" ? "tab active" : "tab"}
            onClick={() => setActiveTab("search")}
          >
            Search
          </button>
          <button
            type="button"
            className={activeTab === "similar" ? "tab active" : "tab"}
            onClick={() => setActiveTab("similar")}
          >
            Similar Works
          </button>
          <button
            type="button"
            className={activeTab === "list" ? "tab active" : "tab"}
            onClick={() => setActiveTab("list")}
          >
            My Reading List
          </button>
        </div>
        {activeTab === "search" && (
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
        )}
      </header>

      <main className="results">
        <div className="results__meta">
          {activeTab === "search" ? (
            <>
              <span>
                {total > 0
                  ? `${total.toLocaleString()} results`
                  : "No results yet"}
              </span>
              <span className="results__page">
                Page {page} of {totalPages}
              </span>
            </>
          ) : activeTab === "similar" ? (
            <>
              <span>
                {similarResults.length > 0
                  ? `${similarResults.length} matches`
                  : "No matches yet"}
              </span>
              <span className="results__page">Similarity search</span>
            </>
          ) : (
            <>
              <span>{readingList.length} saved</span>
              <span className="results__page">Reading list</span>
            </>
          )}
        </div>

        {error && <div className="notice notice--error">{error}</div>}

        {activeTab === "search" ? (
          <div className="results__table">
            <div className="results__row results__row--header results__row--search">
              <span>Title</span>
              <span>Author</span>
              <span>Year</span>
              <span>Status</span>
              <span></span>
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
                <div className="results__row results__row--search" key={key}>
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
                        updateStatus(
                          key,
                          event.target.value,
                          item.first_publish_year,
                        )
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
                  <div>
                    <button
                      type="button"
                      className="similar-button"
                      onClick={() =>
                        startSimilarStream({
                          key,
                          title: item.title,
                          author,
                          year: item.first_publish_year,
                        })
                      }
                    >
                      Search similar
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : activeTab === "similar" ? (
          <div className="similar">
            <div className="similar__header">
              <div>
                <div className="similar__label">Selected work</div>
                <div className="similar__title">
                  {similarWork?.title || "Pick a work from Search"}
                </div>
                {similarWork?.key && (
                  <div className="similar__key">{similarWork.key}</div>
                )}
              </div>
              <button
                type="button"
                className="similar-button"
                onClick={() => startSimilarStream(similarWork)}
                disabled={!similarWork}
              >
                Refresh
              </button>
            </div>

            <div className="similar__controls">
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={preferSameAuthor}
                  onChange={(event) =>
                    setPreferSameAuthor(event.target.checked)
                  }
                />
                Prefer same author
              </label>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={preferYearRange}
                  onChange={(event) =>
                    setPreferYearRange(event.target.checked)
                  }
                />
                Prefer similar era
              </label>
              <select
                className="range-select"
                value={yearRange}
                onChange={(event) => setYearRange(Number(event.target.value))}
                disabled={!preferYearRange}
              >
                {[10, 20, 30, 40].map((value) => (
                  <option key={value} value={value}>
                    ±{value} years
                  </option>
                ))}
              </select>
            </div>

            {similarError && (
              <div className="notice notice--error">{similarError}</div>
            )}

            {similarStatus && (
              <div className="similar__status">
                {similarStatus}
                {statusDots}
              </div>
            )}
            {similarProgress && (
              <div className="similar__progress">
                Indexed {similarProgress.embedded ?? 0} of{" "}
                {similarProgress.total ?? 0}
              </div>
            )}

            <div className="results__table">
              <div className="results__row results__row--header similar__row">
                <span>Title</span>
                <span>Author</span>
                <span>Year</span>
                <span>Score</span>
              </div>
              {similarResults.map((item) => (
                <div
                  className="results__row similar__row"
                  key={item.id || item.title}
                >
                  <div>
                    <div className="results__title">{item.title}</div>
                    <div className="results__key">{item.id}</div>
                    {item.reason && (
                      <div className="similar__reason">{item.reason}</div>
                    )}
                  </div>
                  <div>
                    {Array.isArray(item.authors) && item.authors.length
                      ? item.authors.join(", ")
                      : "Unknown"}
                  </div>
                  <div>{item.year ?? "—"}</div>
                  <div>{item.score}</div>
                </div>
              ))}
              {similarResults.length === 0 && (
                <div className="similar__empty">
                  No results yet. Start a similarity search from the Search tab.
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="results__table">
            <div className="results__row results__row--header results__row--list">
              <span>Title</span>
              <span>Author</span>
              <span>Year</span>
              <span>Status</span>
              <span>Notes</span>
              <span>Rating</span>
              <span></span>
            </div>
            {readingList.map((item) => {
              const key = item.work_olid;
              const author = item.author_names?.length
                ? item.author_names.join(", ")
                : "Unknown";
              const disabled = Boolean(updating[key]);
              return (
                <div className="results__row results__row--list" key={key}>
                  <div>
                    <div className="results__title">{item.title}</div>
                    <div className="results__key">{key}</div>
                  </div>
                  <div>{author}</div>
                  <div>{item.first_publish_year ?? "—"}</div>
                  <div className="results__status">
                    <select
                      className={`status-select status-select--${item.status}`}
                      value={item.status}
                      onChange={(event) =>
                        updateStatus(key, event.target.value, null)
                      }
                      disabled={disabled}
                    >
                      {STATUSES.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <textarea
                      className="notes"
                      rows={2}
                      defaultValue={item.notes ?? ""}
                      placeholder="Add notes…"
                      onBlur={(event) =>
                        updateNotesRating(
                          key,
                          event.target.value,
                          item.rating,
                        )
                      }
                    />
                  </div>
                  <div>
                    <input
                      className="rating"
                      type="number"
                      min="1"
                      max="5"
                      defaultValue={item.rating ?? ""}
                      placeholder="—"
                      onBlur={(event) => {
                        const value = event.target.value;
                        const rating = value ? Number(value) : null;
                        updateNotesRating(key, item.notes, rating);
                      }}
                    />
                  </div>
                  <div>
                    <button
                      type="button"
                      className="delete"
                      onClick={() => deleteEntry(key)}
                      disabled={disabled}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {activeTab === "search" && (
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
        )}
      </main>
    </div>
  );
}

export default App;
