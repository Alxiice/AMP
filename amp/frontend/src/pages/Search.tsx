import { useState, useCallback } from "react";
import { api, type Song } from "../api";
import { SongList } from "../components/SongList";
import { Icon } from "../components/Icon";

const SEARCH_TYPES = ["songs", "videos"];

// Survives leaving the page and coming back
let last = { query: "", searchType: "songs", results: [] as Song[], hasSearched: false };

export function Search() {
  const [query, setQuery] = useState(last.query);
  const [searchType, setSearchType] = useState(last.searchType);
  const [results, setResults] = useState<Song[]>(last.results);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(last.hasSearched);

  const runSearch = useCallback(async (type: string) => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const data = await api.search(q, type, 25);
      setResults(data);
      last = { query: q, searchType: type, results: data, hasSearched: true };
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [query]);

  return (
    <div>
      <form
        className="search-box"
        onSubmit={(e) => {
          e.preventDefault();
          runSearch(searchType);
        }}
      >
        <span className="search-icon"><Icon name="search" size={18} /></span>
        <input
          className="search-input"
          type="text"
          placeholder="Search YouTube Music..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <div className="chips">
          {SEARCH_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              className={`chip${searchType === t ? " active" : ""}`}
              onClick={() => {
                setSearchType(t);
                runSearch(t);
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </form>

      {error && <div className="error-message">{error}</div>}

      <SongList
        songs={results}
        loading={loading}
        emptyMessage={hasSearched ? "No results found" : "Search for a song, an artist, an album..."}
      />
    </div>
  );
}
