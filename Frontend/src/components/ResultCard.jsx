import { useNavigate } from "react-router-dom";

export default function ResultCard({ researcher }) {
  const navigate = useNavigate();

  return (
    <div
      onClick={() => navigate(`/researcher/${researcher.id}`)}
      style={{
        border: "0.5px solid var(--border)",
        borderRadius: "8px",
        background: "var(--bg-elevated)",
        padding: "14px 16px",
        marginBottom: "10px",
        cursor: "pointer",
      }}
    >
      <p style={{ margin: 0, fontWeight: 500 }}>{researcher.name}</p>
      <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--text-muted)" }}>
        {researcher.university} — {researcher.discipline}
      </p>
      <p style={{ margin: "4px 0 0", fontSize: "12px", color: "var(--text-muted)" }}>
        {researcher.research_interests.join(", ")}
      </p>
    </div>
  );
}