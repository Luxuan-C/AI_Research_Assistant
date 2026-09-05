import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div style={{ padding: "80px 40px", textAlign: "center", maxWidth: "480px", margin: "0 auto" }}>
      <h1 style={{ fontWeight: 500, fontSize: "26px" }}>Vecton research assistant</h1>
      <p style={{ color: "var(--text-muted)", marginBottom: "32px" }}>
        Discover Australian research expertise
      </p>
      <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
        <Link to="/login"><button>Log in</button></Link>
        <Link to="/register"><button>Sign up</button></Link>
      </div>
    </div>
  );
}