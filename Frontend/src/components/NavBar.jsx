import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../api/authContext";

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 32px", borderBottom: "0.5px solid var(--border-soft)" }}>
      <Link to="/home" style={{ color: "var(--text)", textDecoration: "none", fontWeight: 500 }}>
        Vecton research assistant
      </Link>
      <div style={{ display: "flex", gap: "20px", alignItems: "center" }}>
        <Link to="/results" style={{ color: "var(--text-muted)", textDecoration: "none", fontSize: "14px" }}>Directory</Link>
        <Link to="/ask" style={{ color: "var(--text-muted)", textDecoration: "none", fontSize: "14px" }}>Ask AI</Link>
        {user && <button onClick={handleLogout}>Log out</button>}
      </div>
    </div>
  );
}