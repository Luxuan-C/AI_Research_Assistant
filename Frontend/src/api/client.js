async function request(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "API request failed");
  return payload;
}

export async function searchResearchers(query = "", filters = {}) {
  const params = new URLSearchParams({
    q: query,
    university: filters.university || "",
    discipline: filters.discipline || "",
  });
  const payload = await request(`/api/researchers?${params}`);
  return payload.researchers;
}

export async function getResearcherProfile(id) {
  return request(`/api/researchers/${encodeURIComponent(id)}`);
}

export async function askQuestion(question) {
  return request("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export async function getDirectoryOptions() {
  return request("/api/directory-options");
}