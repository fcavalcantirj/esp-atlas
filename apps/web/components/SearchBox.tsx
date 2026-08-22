"use client";

import { useState } from "react";
import { searchParts, type SearchFilters, type PartRecord } from "@/lib/api";
import PartResultCard from "@/components/PartResultCard";

export default function SearchBox() {
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [radio, setRadio] = useState("");
  const [band, setBand] = useState("");
  const [form, setForm] = useState("");
  const [protocol, setProtocol] = useState("");

  const [results, setResults] = useState<PartRecord[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const filters: SearchFilters = { q };
    if (type) filters.type = type as SearchFilters["type"];
    if (radio) filters.radio = radio;
    if (band) filters.band = Number(band);
    if (form) filters.form = form;
    if (protocol) filters.protocol = protocol;

    try {
      const { results } = await searchParts(filters);
      setResults(results);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <h2>Search</h2>
      <form onSubmit={handleSubmit} className="search-form">
        <input
          type="text"
          placeholder="free text, e.g. zigbee"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <input type="text" placeholder="type (soc/module/board)" value={type} onChange={(e) => setType(e.target.value)} />
        <input type="text" placeholder="radio, e.g. wifi-6" value={radio} onChange={(e) => setRadio(e.target.value)} />
        <input type="text" placeholder="band, e.g. 5" value={band} onChange={(e) => setBand(e.target.value)} />
        <input type="text" placeholder="form, e.g. xiao" value={form} onChange={(e) => setForm(e.target.value)} />
        <input
          type="text"
          placeholder="protocol, e.g. thread"
          value={protocol}
          onChange={(e) => setProtocol(e.target.value)}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}
      {results && results.length === 0 && <p>No matches.</p>}
      {results && results.length > 0 && (
        <ul className="results-list">
          {results.map((part) => (
            <PartResultCard key={part.id} part={part} />
          ))}
        </ul>
      )}
    </section>
  );
}
