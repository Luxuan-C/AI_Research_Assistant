import json
import os


RAW_DATA_DIR = "./data/raw"
CLEANED_DATA_DIR = "./data/filtered"

JOURNALS_FILE = os.path.join(
    RAW_DATA_DIR,
    "journals.json"
)

MAPPINGS_FILE = os.path.join(
    CLEANED_DATA_DIR,
    "id_mappings.json"
)

OUTPUT_FILE = os.path.join(
    CLEANED_DATA_DIR,
    "journals_supabase.json"
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


journals = load_json(JOURNALS_FILE)
id_mappings = load_json(MAPPINGS_FILE)

journal_mapping = id_mappings["journals"]

supabase_journals = []

for journal in journals:

    journal_uuid = journal_mapping.get(
        str(journal["id"])
    )

    if journal_uuid is None:
        continue

    supabase_journals.append({
        "id": journal_uuid,
        "name": journal["name"],
        "type": journal.get("type"),
        "issn": journal.get("issn")
    })


# ============================================================
# VALIDATION
# ============================================================

missing_uuid = [
    journal
    for journal in journals
    if str(journal["id"]) not in journal_mapping
]

duplicate_ids = (
    len({
        journal["id"]
        for journal in supabase_journals
    })
    != len(supabase_journals)
)


print("=== JOURNAL PREPARATION ===")
print("Raw journals:", len(journals))
print("Prepared journals:", len(supabase_journals))
print("Missing UUID mappings:", len(missing_uuid))
print("Duplicate UUIDs:", duplicate_ids)


# ============================================================
# SAVE
# ============================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as file:
    json.dump(
        supabase_journals,
        file,
        indent=2,
        ensure_ascii=False
    )


print(
    f"Supabase-ready journals saved to: {OUTPUT_FILE}"
)