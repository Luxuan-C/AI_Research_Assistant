import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { registerUser } from "../api/authClient";
import { useAuth } from "../api/authContext";

export default function Register() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async () => {
    setError("");
    if (!name || !email || !password) {
      setError("Please fill in all fields.");
      return;
    }
    try {
      const user = await registerUser({ name, email, password });
      login(user);
      navigate("/home");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div style={{ padding: "60px 40px", maxWidth: "400px", margin: "0 auto" }}>
      <h1 style={{ fontWeight: 500 }}>Create an account</h1>
      <input placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} style={{ width: "100%", marginBottom: "10px" }} />
      <input placeholder="Academic email (.edu.au)" value={email} onChange={(e) => setEmail(e.target.value)} style={{ width: "100%", marginBottom: "10px" }} />
      <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ width: "100%", marginBottom: "10px" }} />
      {error && <p style={{ color: "#e0847a", fontSize: "13px" }}>{error}</p>}
      <button onClick={handleSubmit} style={{ width: "100%" }}>Sign up</button>
    </div>
  );
}