import json
import os
import uuid


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ACADEMICS_PATH = os.path.join(
    BASE_DIR, "data", "filtered", "academics_merged.json"
)

MAPPINGS_PATH = os.path.join(
    BASE_DIR, "data", "filtered", "id_mappings.json"
)

OUTPUT_PATH = os.path.join(
    BASE_DIR, "data", "filtered", "academics_supabase.json"
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


academics = load_json(ACADEMICS_PATH)
mappings = load_json(MAPPINGS_PATH)

# Create missing discipline UUID mappings
if "disciplines" not in mappings:
    mappings["disciplines"] = {
        str(i): str(uuid.uuid4())
        for i in range(26)
    }

# Create missing field UUID mappings
if "fields" not in mappings:
    mappings["fields"] = {
        str(i): str(uuid.uuid4())
        for i in range(132)
    }

with open(MAPPINGS_PATH, "w", encoding="utf-8") as f:
    json.dump(mappings, f, indent=4, ensure_ascii=False)

print("Updated UUID mappings saved.")

print("Academics:", len(academics))
print("Available mappings:", list(mappings.keys()))

def convert_ids(ids, mapping):
    """Convert local integer IDs to UUIDs and remove duplicates."""
    converted = []

    for local_id in ids or []:
        uuid_value = mapping.get(str(local_id))

        if uuid_value and uuid_value not in converted:
            converted.append(uuid_value)

    return converted

VALID_CS_DISCIPLINE_IDS = {
    "4780a5ce-ed92-4ad7-a863-126b8e8477a7"
}

VALID_CS_FIELD_IDS = {
    "edf06679-a420-4028-a675-e6b0406082a9",  # Computer Networks and Communications
    "8a2787cf-3f7d-4e40-8c0f-893e8a72950f",  # Information Systems
    "22a7121d-7b7b-4b8e-8e51-6df0d44cd822",  # Artificial Intelligence
    "66591424-5e4a-4400-b73f-b3a79b1034ce",  # Computational Theory and Mathematics
    "b3b631f6-937e-41bb-ab53-5410fbf05a18",  # Computer Vision and Pattern Recognition
    "2cfc5ac4-da1d-4f2f-8ae2-9981f225b8d8",  # Signal Processing
    "8ce9555b-c407-4c97-9b28-3369faea9352",  # Software
    "0012f2c4-9245-4b20-883c-266b1fae74ce",  # Computer Science Applications
}

supabase_academics = []

for academic in academics:
    academic_uuid = mappings["academics"].get(str(academic["id"]))

    if not academic_uuid:
        continue

    converted = {
        "id": academic_uuid,
        "name": academic.get("name"),
        "academic_position": academic.get("academic_position"),
        "profile_url": academic.get("profile_url"),
        "orcid_url": academic.get("orcid_url"),
        "academic_summary": academic.get("academic_summary"),
        "research_paper_ids": convert_ids(
            academic.get("research_paper_ids"),
            mappings["research_papers"]
        ),
        "university_ids": convert_ids(
            academic.get("university_ids"),
            mappings["universities"]
        ),
        "discipline_ids": [
            x for x in convert_ids(
                academic.get("discipline_ids"),
                mappings["disciplines"]
            )
            if x in VALID_CS_DISCIPLINE_IDS
        ],
        "field_ids": [
            x for x in convert_ids(
                academic.get("field_ids"),
                mappings["fields"]
            )
            if x in VALID_CS_FIELD_IDS
        ]
    }

    supabase_academics.append(converted)


with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(supabase_academics, f, indent=4, ensure_ascii=False)


print("\n=== SUPABASE ACADEMICS ===")
print("Converted academics:", len(supabase_academics))
print("With academic summary:",
      sum(bool(a["academic_summary"]) for a in supabase_academics))
print("Saved to:", OUTPUT_PATH)