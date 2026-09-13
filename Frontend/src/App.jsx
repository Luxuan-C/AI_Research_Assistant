import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./api/authContext";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Home from "./pages/Home";
import Results from "./pages/Results";
import Profile from "./pages/Profile";
import Ask from "./pages/Ask";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/home"
            element={<Layout><ProtectedRoute><Home /></ProtectedRoute></Layout>}
          />
          <Route
            path="/results"
            element={<Layout><ProtectedRoute><Results /></ProtectedRoute></Layout>}
          />
          <Route
            path="/researcher/:id"
            element={<Layout><ProtectedRoute><Profile /></ProtectedRoute></Layout>}
          />
          <Route
            path="/ask"
            element={<Layout><ProtectedRoute><Ask /></ProtectedRoute></Layout>}
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}