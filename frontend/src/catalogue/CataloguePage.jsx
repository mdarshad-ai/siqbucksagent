import { useEffect, useRef, useState } from "react";
import { assetUrl, fetchCatalog } from "../api.js";
import { Link, navigate } from "../router.jsx";
import { pageTitle } from "../site/brand.js";

const PAGE_SIZE = 24;

const SORTS = [
  ["newest", "Newest"],
  ["price_asc", "Price: low to high"],
  ["price_desc", "Price: high to low"],
  ["carat_desc", "Carat: largest first"],
];

export function formatPrice(price) {
  if (!price) return "Price on request";
  return `$${Number(price).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

// Filters live in the URL, so the back button and shared links keep them.
function readFilters(search) {
  const q = new URLSearchParams(search);
  return {
    q: q.get("q") || "",
    agent: q.get("agent") || "",
    category: q.get("category") || "",
    min_price: q.get("min_price") || "",
    max_price: q.get("max_price") || "",
    include_reserved: q.get("include_reserved") !== "false",
    sort: q.get("sort") || "newest",
  };
}

function writeFilters(filters) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (k === "include_reserved") {
      if (!v) q.set(k, "false");
    } else if (k === "sort") {
      if (v !== "newest") q.set(k, v);
    } else if (v) {
      q.set(k, v);
    }
  }
  const s = q.toString();
  navigate(`/catalogue${s ? `?${s}` : ""}`, { replace: true });
}

function StoneTile({ stone }) {
  return (
    <Link
      to={`/stones/${stone.id}`}
      className="cat-tile"
      style={{ "--stall-accent": stone.agent.theme.accent, "--stall-glow": stone.agent.theme.glow }}
    >
      <span className={`cat-tile-image ${stone.image_url ? "has-image" : ""}`}>
        {stone.image_url ? (
          <img src={assetUrl(stone.image_url)} alt={stone.name} loading="lazy" />
        ) : (
          <span className="cat-tile-placeholder">
            <span aria-hidden="true">◆</span>
            <span className="cat-tile-placeholder-text">Photos coming soon</span>
          </span>
        )}
        {stone.status === "reserved" && <span className="cat-tile-badge">On hold</span>}
      </span>
      <span className="cat-tile-body">
        <span className="cat-tile-code">{stone.code}</span>
        <span className="cat-tile-name">{stone.name}</span>
        <span className={`cat-tile-price ${stone.price ? "" : "is-request"}`}>{formatPrice(stone.price)}</span>
        <span className="cat-tile-partner">
          <span className="cat-dot" aria-hidden="true" /> {stone.agent.display_name} · {stone.agent.stall_name}
        </span>
      </span>
    </Link>
  );
}

export default function CataloguePage({ agents, search }) {
  const filters = readFilters(search);
  const [data, setData] = useState({ items: [], total: 0, categories: [] });
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const [query, setQuery] = useState(filters.q);
  const requestId = useRef(0);

  const key = JSON.stringify(filters);

  useEffect(() => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    fetchCatalog({ ...filters, limit: PAGE_SIZE, offset: 0 })
      .then((res) => id === requestId.current && setData(res))
      .catch((err) => id === requestId.current && setError(err.message))
      .finally(() => id === requestId.current && setLoading(false));
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    document.title = pageTitle("Catalogue");
    return () => {
      document.title = pageTitle();
    };
  }, []);

  const update = (changes) => writeFilters({ ...filters, ...changes });
  const activeCount = ["agent", "category", "min_price", "max_price"].filter((k) => filters[k]).length + (filters.include_reserved ? 0 : 1);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const more = await fetchCatalog({ ...filters, limit: PAGE_SIZE, offset: data.items.length });
      setData((prev) => ({ ...more, items: [...prev.items, ...more.items] }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section className="catalogue">
      <div className="site-container">
        <div className="cat-head">
          <div>
            <nav className="breadcrumb" aria-label="Breadcrumb">
              <Link to="/">Home</Link> <span aria-hidden="true">/</span> <span>Catalogue</span>
            </nav>
            <h1>Gemstones</h1>
          </div>
          <div className="cat-controls">
            <form
              className="cat-search"
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                update({ q: query.trim() });
              }}
            >
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search stones..."
                aria-label="Search stones"
              />
            </form>
            <button
              className={`cat-button ${showFilters ? "is-open" : ""}`}
              onClick={() => setShowFilters((v) => !v)}
              aria-expanded={showFilters}
            >
              Filter {activeCount > 0 && <span className="cat-count">{activeCount}</span>}
              <span aria-hidden="true">⚙</span>
            </button>
            <label className="cat-sort">
              <span className="visually-hidden">Sort by</span>
              <select value={filters.sort} onChange={(e) => update({ sort: e.target.value })}>
                {SORTS.map(([value, label]) => (
                  <option key={value} value={value}>
                    Sort: {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {showFilters && (
          <div className="cat-filters">
            <div className="cat-filter-group">
              <span className="cat-filter-label">Partner</span>
              <div className="cat-chips">
                <button className={`chip ${!filters.agent ? "is-selected" : ""}`} onClick={() => update({ agent: "" })}>
                  Everyone
                </button>
                {agents.map((a) => (
                  <button
                    key={a.id}
                    className={`chip ${filters.agent === a.id ? "is-selected" : ""}`}
                    style={{ "--stall-accent": a.theme.accent }}
                    onClick={() => update({ agent: a.id })}
                  >
                    {a.display_name} · {a.stall_name}
                  </button>
                ))}
              </div>
            </div>
            <div className="cat-filter-group">
              <span className="cat-filter-label">Gem</span>
              <div className="cat-chips">
                <button className={`chip ${!filters.category ? "is-selected" : ""}`} onClick={() => update({ category: "" })}>
                  All
                </button>
                {data.categories.map((c) => (
                  <button
                    key={c}
                    className={`chip ${filters.category.toLowerCase() === c.toLowerCase() ? "is-selected" : ""}`}
                    onClick={() => update({ category: c })}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>
            <div className="cat-filter-row">
              <div className="cat-filter-group">
                <span className="cat-filter-label">Price (USD)</span>
                <form
                  className="cat-price"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const f = new FormData(e.currentTarget);
                    update({ min_price: f.get("min") || "", max_price: f.get("max") || "" });
                  }}
                >
                  <input name="min" type="number" min="0" placeholder="Min" defaultValue={filters.min_price} aria-label="Minimum price" />
                  <span aria-hidden="true">–</span>
                  <input name="max" type="number" min="0" placeholder="Max" defaultValue={filters.max_price} aria-label="Maximum price" />
                  <button className="cat-button">Apply</button>
                </form>
              </div>
              <label className="cat-toggle">
                <input
                  type="checkbox"
                  checked={filters.include_reserved}
                  onChange={(e) => update({ include_reserved: e.target.checked })}
                />
                Show stones on hold
              </label>
              {activeCount > 0 && (
                <button
                  className="cat-clear"
                  onClick={() => update({ agent: "", category: "", min_price: "", max_price: "", include_reserved: true })}
                >
                  Clear filters
                </button>
              )}
            </div>
          </div>
        )}

        <div className="cat-results" aria-live="polite">
          {loading ? "Loading..." : `${data.total.toLocaleString()} ${data.total === 1 ? "result" : "results"}`}
          {filters.q && !loading && (
            <>
              {" "}for “{filters.q}”{" "}
              <button className="cat-clear" onClick={() => { setQuery(""); update({ q: "" }); }}>
                Clear search
              </button>
            </>
          )}
        </div>

        {error && <div className="load-error">{error}</div>}

        <div className={`cat-grid ${loading ? "is-loading" : ""}`}>
          {data.items.map((stone) => (
            <StoneTile key={stone.id} stone={stone} />
          ))}
        </div>

        {!loading && data.items.length === 0 && !error && (
          <div className="cat-empty">
            <p>No stones match those filters.</p>
            <p className="hero-lede">Not finding it? Our AI partners can help, or source it for you.</p>
          </div>
        )}

        {data.items.length < data.total && (
          <div className="cat-more">
            <button className="cat-button" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? "Loading..." : `Show more (${data.total - data.items.length} left)`}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
