import { Navigate } from "react-router-dom";
import { useAuth } from "../api/authContext";

export default function ProtectedRoute({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/" replace />;
  return children;
}