import { useState } from "react";
import { askQuestion } from "../api/client";

export default function Ask() {
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);

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
          <h3 style={{ fontWeight: 500 }}>Sources</h3>
          <ul>
            {response.citations.map((c, i) => (
              <li key={i}>
                <a href={c.source_url} target="_blank" rel="noreferrer">{c.source_title}</a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}