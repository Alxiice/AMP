import { useState, useCallback } from "react";
import { api, type Song } from "../api";
import { SongList } from "../components/SongList";

const SEARCH_TYPES = ["songs", "videos", "albums", "artists", "playlists"];

export function Search() {
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState("songs");
  const [results, setResults] = useState<Song[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const data = await api.search(query.trim(), searchType, 25);
      // For non-song types, the API returns raw results — filter to those with id
      setResults(data.filter((r) => r.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [query, searchType]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") handleSearch();
    },
    [handleSearch],
  );

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Search</h1>
      </div>

      <div className="search-box">
        <input
          className="search-input"
          type="text"
          placeholder="Search YouTube Music..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          autoFocus
        />
        <select
          className="search-type-select"
          value={searchType}
          onChange={(e) => setSearchType(e.target.value)}
        >
          {SEARCH_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <button className="btn" onClick={handleSearch} disabled={loading || !query.trim()}>
          Search
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      <SongList
        songs={results}
        loading={loading}
        emptyMessage={hasSearched ? "No results found" : "Enter a search query above"}
      />
    </div>
  );
}
