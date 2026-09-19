import json
import os


RAW_DATA_DIR = "./data/raw"
CLEANED_DATA_DIR = "./data/filtered"

FACULTIES_FILE = os.path.join(
    RAW_DATA_DIR,
    "faculties.json"
)

MAPPINGS_FILE = os.path.join(
    CLEANED_DATA_DIR,
    "id_mappings.json"
)

OUTPUT_FILE = os.path.join(
    CLEANED_DATA_DIR,
    "faculties_supabase.json"
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


faculties = load_json(FACULTIES_FILE)
id_mappings = load_json(MAPPINGS_FILE)

faculty_mapping = id_mappings["faculties"]

supabase_faculties = []

for faculty in faculties:
    faculty_uuid = faculty_mapping.get(str(faculty["id"]))

    if faculty_uuid is None:
        continue

    supabase_faculties.append({
        "id": faculty_uuid,
        "name": faculty["name"]
    })


# Validation
missing_uuid = [
    faculty
    for faculty in faculties
    if str(faculty["id"]) not in faculty_mapping
]

duplicate_ids = (
    len({faculty["id"] for faculty in supabase_faculties})
    != len(supabase_faculties)
)

print("=== FACULTY PREPARATION ===")
print("Raw faculties:", len(faculties))
print("Prepared faculties:", len(supabase_faculties))
print("Missing UUID mappings:", len(missing_uuid))
print("Duplicate UUIDs:", duplicate_ids)


# Save
with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
    json.dump(
        supabase_faculties,
        file,
        indent=2,
        ensure_ascii=False
    )

print(f"Supabase-ready faculties saved to: {OUTPUT_FILE}")