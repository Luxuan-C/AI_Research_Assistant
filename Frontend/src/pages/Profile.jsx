import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getResearcherProfile } from "../api/client";

export default function Profile() {
  const { id } = useParams();
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    getResearcherProfile(id).then(setProfile);
  }, [id]);

  if (!profile) return <p style={{ padding: "40px" }}>Loading...</p>;

  return (
    <div style={{ padding: "40px", maxWidth: "600px", margin: "0 auto" }}>
      <h1 style={{ fontWeight: 500 }}>{profile.name}</h1>
      <p style={{ color: "var(--text-muted)" }}>
        {profile.university} — {profile.discipline}
      </p>

      <h3 style={{ fontWeight: 500 }}>Summary</h3>
      <p>{profile.ai_summary}</p>

      <h3 style={{ fontWeight: 500 }}>Publications</h3>
      <ul>
        {profile.publications.map((pub, i) => (
          <li key={i}>{pub}</li>
        ))}
      </ul>

      <a href={profile.official_profile_url} target="_blank" rel="noreferrer">
        Official profile →
      </a>
    </div>
  );
}