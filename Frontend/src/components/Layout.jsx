import Navbar from "./NavBar";

export default function Layout({ children }) {
  return (
    <div style={{ minHeight: "100vh" }}>
      <Navbar />
      {children}
    </div>
  );
}