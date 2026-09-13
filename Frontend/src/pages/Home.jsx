import { useState } from "react";
import ModeToggle from "../components/ModeToggle";

export default function Home() {
  const [query, setQuery] = useState("");

  return (
    <div style={{ padding: "60px 40px", textAlign: "center", maxWidth: "560px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "28px", fontWeight: 500 }}>Discover Australian research expertise</h1>
      <p style={{ color: "var(--text-muted)", marginBottom: "28px" }}>
        Search by topic, or ask a question in plain English
      </p>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="describe a research interest..."
        style={{ width: "100%", marginBottom: "24px" }}
      />
      <ModeToggle />
    </div>
  );
}