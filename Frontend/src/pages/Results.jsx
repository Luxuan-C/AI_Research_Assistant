import { useEffect, useState } from "react";
import { getDirectoryOptions, searchResearchers } from "../api/client";
import ResultCard from "../components/ResultCard";

export default function Results() {
  const [researchers, setResearchers] = useState([]);
  const [universities, setUniversities] = useState([]);
  const [disciplines, setDisciplines] = useState([]);
  const [query, setQuery] = useState("");
  const [university, setUniversity] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getDirectoryOptions()
      .then(({ universities: liveUniversities, disciplines: liveDisciplines }) => {
        setUniversities(liveUniversities);
        setDisciplines(liveDisciplines);
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    setLoading(true);
    searchResearchers(query, { university, discipline })
      .then(setResearchers)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [query, university, discipline]);

  return (
    <div style={{ padding: "40px", maxWidth: "600px", margin: "0 auto" }}>
      <h1 style={{ fontWeight: 500 }}>Search results</h1>

      <div style={{ display: "flex", gap: "10px", marginBottom: "20px" }}>
        <input
          type="text"
          placeholder="keyword..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ flex: 1 }}
        />
        <select value={university} onChange={(e) => setUniversity(e.target.value)}>
          <option value="">All universities</option>
          {universities.map((u) => (
            <option key={u} value={u}>{u}</option>
          ))}
        </select>
        <select value={discipline} onChange={(e) => setDiscipline(e.target.value)}>
          <option value="">All disciplines</option>
          {disciplines.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      {error && <p className="error-text">{error}</p>}
      {loading && <p style={{ color: "var(--text-muted)" }}>Loading researchers...</p>}
      {!loading && !error && researchers.length === 0 && <p style={{ color: "var(--text-muted)" }}>No results found.</p>}
      {researchers.map((r) => (
        <ResultCard key={r.id} researcher={r} />
      ))}
    </div>
  );
}