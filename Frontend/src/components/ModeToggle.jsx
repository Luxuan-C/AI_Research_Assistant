import { useNavigate } from "react-router-dom";

export default function ModeToggle() {
  const navigate = useNavigate();

  return (
    <div style={{ display: "flex", gap: "12px" }}>
      <div
        className="mode-panel"
        tabIndex={0}
        role="button"
        aria-label="Select directory search"
        onClick={() => navigate("/results")}
      >
        <p style={{ margin: 0, fontWeight: 500 }}>Directory search</p>
        <p className="mode-sub">Filter by university, discipline, keyword</p>
      </div>
      <div
        className="mode-panel"
        tabIndex={0}
        role="button"
        aria-label="Select ask AI"
        onClick={() => navigate("/ask")}
      >
        <p style={{ margin: 0, fontWeight: 500 }}>Ask AI</p>
        <p className="mode-sub">Ask a question, get a cited answer</p>
      </div>
    </div>
  );
}