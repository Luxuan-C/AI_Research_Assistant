import { useEffect, useState } from "react";
import { searchResearchers } from "../api/client";
import ResultCard from "../components/ResultCard";

const UNIVERSITIES = ["UNSW", "University of Sydney", "Monash University", "ANU"];
const DISCIPLINES = ["Computer Science", "Information Technology", "Data Science"];

export default function Results() {
  const [researchers, setResearchers] = useState([]);
  const [query, setQuery] = useState("");
  const [university, setUniversity] = useState("");
  const [discipline, setDiscipline] = useState("");

  useEffect(() => {
    searchResearchers(query, { university, discipline }).then(setResearchers);
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
          {UNIVERSITIES.map((u) => (
            <option key={u} value={u}>{u}</option>
          ))}
        </select>
        <select value={discipline} onChange={(e) => setDiscipline(e.target.value)}>
          <option value="">All disciplines</option>
          {DISCIPLINES.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      {researchers.length === 0 && <p style={{ color: "var(--text-muted)" }}>No results found.</p>}
      {researchers.map((r) => (
        <ResultCard key={r.id} researcher={r} />
      ))}
    </div>
  );
}