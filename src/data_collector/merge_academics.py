import json
import os
import re
import unicodedata


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ACADEMICS_PATH = os.path.join(
    BASE_DIR, "data", "filtered", "academics.json"
)

UNIVERSITY_ACADEMICS_PATH = os.path.join(
    BASE_DIR, "university_websites", "university_academics.json"
)

OUTPUT_PATH = os.path.join(
    BASE_DIR, "data", "filtered", "academics_merged.json"
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def normalise_name(name):
    if not name:
        return ""

    name = unicodedata.normalize("NFKD", name)
    name = "".join(
        c for c in name
        if not unicodedata.combining(c)
    )

    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    return name


# Load data
academics = load_json(ACADEMICS_PATH)
website_academics = load_json(UNIVERSITY_ACADEMICS_PATH)


# Create website lookup by name
website_lookup = {}

for profile in website_academics:
    name = normalise_name(profile.get("name"))

    if name:
        website_lookup.setdefault(name, []).append(profile)


merged_academics = []
matched = 0


for academic in academics:

    merged = academic.copy()

    name = normalise_name(academic.get("name"))
    matches = website_lookup.get(name, [])

    # Only merge when exactly one profile matches
    if len(matches) == 1:

        profile = matches[0]
        matched += 1

        # Prefer university website values where available
        if profile.get("academic_position"):
            merged["academic_position"] = profile["academic_position"]

        if profile.get("profile_url"):
            merged["profile_url"] = profile["profile_url"]

        if profile.get("orcid_url"):
            merged["orcid_url"] = profile["orcid_url"]

        # Use existing profile/biography text as summary when available
        research_interests = profile.get("research_interests") or []

        if research_interests:
            merged["academic_summary"] = " ".join(research_interests)
        else:
            merged["academic_summary"] = None

    else:
        merged["academic_summary"] = None

    merged_academics.append(merged)


save_json(merged_academics, OUTPUT_PATH)


print("=== ACADEMIC MERGE ===")
print(f"Base academics: {len(academics)}")
print(f"University profiles: {len(website_academics)}")
print(f"Matched academics: {matched}")
print(
    "With academic summary:",
    sum(bool(a.get("academic_summary")) for a in merged_academics)
)

print("\nSaved to:")
print(OUTPUT_PATH)