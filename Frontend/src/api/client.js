import { mockResearchers, mockProfile, mockAskResponse } from "./mockData";

export async function searchResearchers(query = "", filters = {}) {
  return mockResearchers.filter((r) => {
    const matchesUniversity = !filters.university || r.university === filters.university;
    const matchesDiscipline = !filters.discipline || r.discipline === filters.discipline;
    const matchesQuery =
      !query ||
      r.name.toLowerCase().includes(query.toLowerCase()) ||
      r.research_interests.some((i) => i.toLowerCase().includes(query.toLowerCase()));
    return matchesUniversity && matchesDiscipline && matchesQuery;
  });
}

export async function getResearcherProfile(id) {
  return mockProfile;
}

export async function askQuestion(question) {
  return mockAskResponse;
}