import json
import os
import re
import unicodedata
from collections import Counter


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CLEANED_ACADEMICS_PATH = os.path.join(
    BASE_DIR, "data", "cleaned", "academics.json"
)

UNIVERSITY_ACADEMICS_PATH = os.path.join(
    BASE_DIR, "university_websites", "university_academics.json"
)

OUTPUT_PATH = os.path.join(
    BASE_DIR, "data", "cleaned", "academics_merged.json"
)


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def normalise_name(name):
    """
    Normalise researcher names so minor formatting differences
    do not prevent matching.
    """
    if not name:
        return ""

    name = unicodedata.normalize("NFKD", name)
    name = "".join(
        char for char in name
        if not unicodedata.combining(char)
    )

    name = name.lower().strip()

    # Remove common titles
    name = re.sub(
        r"\b(professor|prof|associate professor|"
        r"assistant professor|doctor|dr|mr|mrs|ms)\b",
        "",
        name
    )

    # Remove punctuation
    name = re.sub(r"[^a-z0-9\s]", " ", name)

    # Remove repeated whitespace
    name = re.sub(r"\s+", " ", name).strip()

    return name


def normalise_orcid(orcid):
    if not orcid:
        return None

    return (
        orcid.lower()
        .replace("https://orcid.org/", "")
        .replace("http://orcid.org/", "")
        .strip()
    )


def clean_list(values):
    if not values:
        return []

    cleaned = []

    for value in values:
        if not isinstance(value, str):
            continue

        value = value.strip()

        if not value:
            continue

        # Ignore scraper headings rather than actual content
        if value.lower() in {
            "research interests",
            "research interest",
            "areas of expertise",
            "expertise"
        }:
            continue

        if value not in cleaned:
            cleaned.append(value)

    return cleaned


def create_academic_summary(profile):
    """
    Use useful biography/research-interest text from the
    university profile as academic_summary.

    We keep the original wording rather than generating
    new information.
    """

    interests = clean_list(
        profile.get("research_interests", [])
    )

    if not interests:
        return None

    return " ".join(interests)


# --------------------------------------------------
# Load datasets
# --------------------------------------------------

academics = load_json(CLEANED_ACADEMICS_PATH)
university_academics = load_json(UNIVERSITY_ACADEMICS_PATH)

print("=== INPUT ===")
print(f"OpenAlex academics: {len(academics)}")
print(f"University website profiles: {len(university_academics)}")


# --------------------------------------------------
# Build lookup indexes
# --------------------------------------------------

profiles_by_orcid = {}
profiles_by_name = {}

for profile in university_academics:

    orcid = normalise_orcid(profile.get("orcid_url"))

    if orcid:
        profiles_by_orcid.setdefault(orcid, []).append(profile)

    name = normalise_name(profile.get("name"))

    if name:
        profiles_by_name.setdefault(name, []).append(profile)


# --------------------------------------------------
# Merge
# --------------------------------------------------

merged_academics = []

stats = Counter()

for academic in academics:

    match = None
    match_method = None

    # ----------------------------------------------
    # 1. ORCID match — strongest identifier
    # ----------------------------------------------

    academic_orcid = normalise_orcid(
        academic.get("orcid_url") or academic.get("orcid")
    )

    if academic_orcid:
        candidates = profiles_by_orcid.get(academic_orcid, [])

        if len(candidates) == 1:
            match = candidates[0]
            match_method = "orcid"

    # ----------------------------------------------
    # 2. Name match
    # ----------------------------------------------

    if match is None:

        name = normalise_name(academic.get("name"))

        candidates = profiles_by_name.get(name, [])

        if len(candidates) == 1:
            match = candidates[0]
            match_method = "name"

        elif len(candidates) > 1:
            stats["ambiguous_name"] += 1

    # ----------------------------------------------
    # Copy academic so original data is untouched
    # ----------------------------------------------

    merged = academic.copy()

    if match:

        stats["matched"] += 1
        stats[f"matched_{match_method}"] += 1

        # Add university website information
        merged["academic_position"] = (
            match.get("academic_position")
            or merged.get("academic_position")
        )

        merged["profile_url"] = (
            match.get("profile_url")
            or merged.get("profile_url")
        )

        merged["orcid_url"] = (
            match.get("orcid_url")
            or merged.get("orcid_url")
        )

        merged["research_interests"] = clean_list(
            match.get("research_interests", [])
        )

        merged["areas_of_expertise"] = clean_list(
            match.get("areas_of_expertise", [])
        )

        merged["academic_summary"] = create_academic_summary(match)

        # Useful while validating the merge
        merged["university_profile_match"] = True
        merged["university_profile_match_method"] = match_method

    else:

        stats["unmatched"] += 1

        merged.setdefault("academic_position", None)
        merged.setdefault("profile_url", None)
        merged.setdefault("orcid_url", None)
        merged.setdefault("research_interests", [])
        merged.setdefault("areas_of_expertise", [])
        merged.setdefault("academic_summary", None)

        merged["university_profile_match"] = False
        merged["university_profile_match_method"] = None

    merged_academics.append(merged)


# --------------------------------------------------
# Validation
# --------------------------------------------------

print("\n=== MATCH RESULTS ===")

print(f"Matched academics: {stats['matched']}")
print(f"  ORCID matches: {stats['matched_orcid']}")
print(f"  Name matches: {stats['matched_name']}")
print(f"Ambiguous names: {stats['ambiguous_name']}")
print(f"Unmatched academics: {stats['unmatched']}")

print("\n=== ENRICHMENT ===")

print(
    "With academic position:",
    sum(bool(a.get("academic_position")) for a in merged_academics)
)

print(
    "With profile URL:",
    sum(bool(a.get("profile_url")) for a in merged_academics)
)

print(
    "With ORCID:",
    sum(bool(a.get("orcid_url")) for a in merged_academics)
)

print(
    "With research interests:",
    sum(bool(a.get("research_interests")) for a in merged_academics)
)

print(
    "With areas of expertise:",
    sum(bool(a.get("areas_of_expertise")) for a in merged_academics)
)

print(
    "With academic summary:",
    sum(bool(a.get("academic_summary")) for a in merged_academics)
)


# --------------------------------------------------
# Save
# --------------------------------------------------

save_json(merged_academics, OUTPUT_PATH)

print("\n=== COMPLETE ===")
print(f"Merged academics saved to: {OUTPUT_PATH}")