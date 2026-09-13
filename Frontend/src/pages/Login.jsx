import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { loginUser } from "../api/authClient";
import { useAuth } from "../api/authContext";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async () => {
    setError("");
    if (!email || !password) {
      setError("Please enter email and password.");
      return;
    }
    try {
      const user = await loginUser({ email, password });
      login(user);
      navigate("/home");
    } catch (err) {
      setError(err.message);
    }
  };

    return (
    <div className="fade-in" style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "20px" }}>
      <div className="auth-card" style={{ maxWidth: "380px", width: "100%" }}>
        <h1 style={{ fontWeight: 600, fontSize: "22px", marginBottom: "20px" }}>Log in</h1>
        <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} style={{ width: "100%", marginBottom: "12px" }} />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ width: "100%", marginBottom: "4px" }} />
        {error && <p className="error-text">{error}</p>}
        <button onClick={handleSubmit} style={{ width: "100%", marginTop: "8px" }}>Log in</button>
      </div>
    </div>
  );

}

