import { useState } from "react";
import { askQuestion } from "../api/client";
import FactorRadar from "../components/FactorRadar";

export default function Ask() {
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const uniqueCitations = response
    ? Array.from(
        new Map(
          response.citations.map((citation) => [
            citation.source_url || citation.source_title,
            citation,
          ]),
        ).values(),
      )
    : [];
  const displayFactor = (value, available) =>
    available && Number.isFinite(value) ? value.toFixed(3) : "unavailable";
  const sourceOriginLabel = (origin) => ({
    internal: "Validated internal evidence",
    external_url_context: "External paper URL context",
    external_google_search: "External scholarly/web discovery",
    internal_database_record: "Internal database record",
  }[origin] || "Source");

  const handleSubmit = async () => {
    if (!question.trim()) return;
    setLoading(true);
    const result = await askQuestion(question);
    setResponse(result);
    setLoading(false);
  };

  return (
    <div style={{ padding: "40px", maxWidth: "600px", margin: "0 auto" }}>
      <h1 style={{ fontWeight: 500 }}>Ask a research question</h1>
      <input
        type="text"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="e.g. Are academics researching electric vehicles?"
        style={{ width: "100%", marginBottom: "10px" }}
      />
      <button onClick={handleSubmit}>Ask</button>

      {loading && <p style={{ color: "var(--text-muted)" }}>Thinking...</p>}

      {response && (
        <div style={{ marginTop: "30px" }}>
          <p>{response.answer}</p>
          <h3 style={{ fontWeight: 500 }}>Ranked papers</h3>
          <ol>
            {response.papers.map((paper) => (
              <li key={paper.id} style={{ marginBottom: "16px" }}>
                <strong>{paper.title}</strong>
                <div>Final score: {paper.final_score.toFixed(3)}</div>
                <div style={{ display: "flex", alignItems: "center", gap: "16px", margin: "8px 0" }}>
                  <FactorRadar
                    scoreBreakdown={paper.score_breakdown}
                    factorAvailability={paper.factor_availability}
                  />
                </div>
                <div style={{ color: "var(--text-muted)", fontSize: "13px" }}>
                  Evidence: {paper.evidence.source_type}; confidence {paper.evidence.confidence.toFixed(2)}
                </div>
              </li>
            ))}
          </ol>
          <h3 style={{ fontWeight: 500 }}>Sources</h3>
          <ul>
            {uniqueCitations.map((c) => (
              <li key={`${c.source_title}-${c.source_url}`}>
                <a href={c.source_url} target="_blank" rel="noreferrer">{c.source_title}</a>
                {c.source_origin && (
                  <small style={{ display: "block", color: "var(--text-muted)" }}>
                    {sourceOriginLabel(c.source_origin)}
                  </small>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
