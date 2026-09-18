import json
import os
import uuid
from collections import Counter


# ============================================================
# CONFIGURATION
# ============================================================
RAW_DATA_DIR = "./data/raw"
CLEANED_DATA_DIR = "./data/cleaned"

RESEARCH_PAPERS_FILE = os.path.join(
    CLEANED_DATA_DIR,
    "research_papers.json"
)

MAPPINGS_FILE = os.path.join(
    CLEANED_DATA_DIR,
    "id_mappings.json"
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def load_json(path):
    """Load a JSON file from a given path."""
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def clean_string(value):
    """Convert empty strings to None."""
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def clean_issue(issue):
    """
    Supabase expects issue to be INTEGER.

    Numeric strings such as "7" become 7.
    Non-numeric values such as "1-2", "S1", etc.
    become None.
    """
    if issue is None:
        return None

    try:
        return int(issue)
    except (ValueError, TypeError):
        return None


def clean_page_numbers(page_numbers):
    """
    Remove invalid page-number values such as:
    None, "", "None-None", "None-10", etc.
    """
    if not page_numbers:
        return None

    page_numbers = str(page_numbers).strip()

    if "None" in page_numbers:
        return None

    return page_numbers


def generate_or_reuse_mapping(items, existing_mapping=None):
    """
    Generate UUIDs for local integer IDs.

    If an ID already has a UUID in id_mappings.json,
    reuse the existing UUID.
    """
    if existing_mapping is None:
        existing_mapping = {}

    mapping = {}

    for item in items:
        local_id = str(item["id"])

        if local_id in existing_mapping:
            mapping[local_id] = existing_mapping[local_id]
        else:
            mapping[local_id] = str(uuid.uuid4())

    return mapping


# ============================================================
# 1. LOAD FILTERED RESEARCH PAPERS
# ============================================================

research_papers = load_json(RESEARCH_PAPERS_FILE)

print("=== RESEARCH PAPER PREPARATION ===")
print(f"Total papers: {len(research_papers)}")


# ============================================================
# 2. INSPECT ISSUE VALUES
# ============================================================

issue_types = Counter(
    type(paper.get("issue")).__name__
    for paper in research_papers
)

print("\n=== ISSUE DATA TYPES ===")

for data_type, count in issue_types.items():
    print(f"{data_type}: {count}")


invalid_issues = []

for paper in research_papers:
    issue = paper.get("issue")

    if issue is None:
        continue

    try:
        int(issue)
    except (ValueError, TypeError):
        invalid_issues.append({
            "id": paper["id"],
            "name": paper["name"],
            "issue": issue
        })


print(f"\nInvalid issue values: {len(invalid_issues)}")

for paper in invalid_issues[:20]:
    print(
        paper["id"],
        "-",
        paper["name"],
        "- issue:",
        repr(paper["issue"])
    )


# ============================================================
# 3. INSPECT CURRENT ID TYPES
# ============================================================

print("\n=== ID TYPES ===")

if research_papers:
    example = research_papers[0]

    print("paper id:", repr(example.get("id")))
    print("journal_id:", repr(example.get("journal_id")))
    print(
        "university_ids:",
        repr(example.get("university_ids"))
    )
    print(
        "faculty_ids:",
        repr(example.get("faculty_ids"))
    )
    print(
        "academic_ids:",
        repr(example.get("academic_ids"))
    )


# ============================================================
# 4. CHECK REQUIRED FIELDS
# ============================================================

papers_without_name = [
    paper
    for paper in research_papers
    if not paper.get("name")
]

print("\n=== REQUIRED FIELDS ===")
print(f"Papers without name: {len(papers_without_name)}")


# ============================================================
# 5. CLEAN BASIC RESEARCH PAPER FIELDS
# ============================================================

prepared_research_papers = []

for paper in research_papers:
    prepared_paper = paper.copy()

    prepared_paper["name"] = clean_string(
        paper.get("name")
    )

    prepared_paper["volume"] = clean_string(
        paper.get("volume")
    )

    prepared_paper["issue"] = clean_issue(
        paper.get("issue")
    )

    prepared_paper["page_numbers"] = clean_page_numbers(
        paper.get("page_numbers")
    )

    prepared_paper["doi"] = clean_string(
        paper.get("doi")
    )

    prepared_paper["open_access_url"] = clean_string(
        paper.get("open_access_url")
    )

    prepared_paper["primary_url"] = clean_string(
        paper.get("primary_url")
    )

    prepared_paper["publication_type"] = clean_string(
        paper.get("publication_type")
    )

    prepared_research_papers.append(prepared_paper)


print("\n=== BASIC CLEANING ===")
print(f"Prepared papers: {len(prepared_research_papers)}")

papers_with_issue = sum(
    paper["issue"] is not None
    for paper in prepared_research_papers
)

papers_without_issue = sum(
    paper["issue"] is None
    for paper in prepared_research_papers
)

print(f"Papers with issue: {papers_with_issue}")
print(f"Papers without issue: {papers_without_issue}")


# ============================================================
# 6. LOAD RELATED DATA
# ============================================================

filtered_universities = load_json(
    os.path.join(
        CLEANED_DATA_DIR,
        "universities.json"
    )
)

filtered_academics = load_json(
    os.path.join(
        CLEANED_DATA_DIR,
        "academics.json"
    )
)

journals = load_json(
    os.path.join(
        RAW_DATA_DIR,
        "journals.json"
    )
)

faculties = load_json(
    os.path.join(
        RAW_DATA_DIR,
        "faculties.json"
    )
)


# ============================================================
# 7. LOAD EXISTING UUID MAPPINGS IF AVAILABLE
# ============================================================

if os.path.exists(MAPPINGS_FILE):
    existing_mappings = load_json(MAPPINGS_FILE)

    print("\nExisting UUID mappings found.")
    print("Existing UUIDs will be reused.")

else:
    existing_mappings = {}

    print("\nNo existing UUID mappings found.")
    print("New UUID mappings will be generated.")


# ============================================================
# 8. GENERATE CONSISTENT UUID MAPPINGS
# ============================================================

id_mappings = {
    "research_papers": generate_or_reuse_mapping(
        prepared_research_papers,
        existing_mappings.get("research_papers", {})
    ),

    "universities": generate_or_reuse_mapping(
        filtered_universities,
        existing_mappings.get("universities", {})
    ),

    "academics": generate_or_reuse_mapping(
        filtered_academics,
        existing_mappings.get("academics", {})
    ),

    "journals": generate_or_reuse_mapping(
        journals,
        existing_mappings.get("journals", {})
    ),

    "faculties": generate_or_reuse_mapping(
        faculties,
        existing_mappings.get("faculties", {})
    ),
}


# ============================================================
# 9. SAVE UUID MAPPINGS
# ============================================================

with open(
    MAPPINGS_FILE,
    "w",
    encoding="utf-8"
) as file:
    json.dump(
        id_mappings,
        file,
        indent=2
    )


print("\n=== UUID MAPPINGS ===")

print(
    "Research papers:",
    len(id_mappings["research_papers"])
)

print(
    "Universities:",
    len(id_mappings["universities"])
)

print(
    "Academics:",
    len(id_mappings["academics"])
)

print(
    "Journals:",
    len(id_mappings["journals"])
)

print(
    "Faculties:",
    len(id_mappings["faculties"])
)

print(
    f"\nUUID mappings saved to: {MAPPINGS_FILE}"
)


# ============================================================
# 10. FINAL VALIDATION
# ============================================================

print("\n=== VALIDATION ===")

print(
    "Prepared research papers:",
    len(prepared_research_papers)
)

print(
    "Paper UUID mappings:",
    len(id_mappings["research_papers"])
)

print(
    "University UUID mappings:",
    len(id_mappings["universities"])
)

print(
    "Academic UUID mappings:",
    len(id_mappings["academics"])
)

print("\nPreparation completed successfully.")

# ============================================================
# 11. CONVERT RESEARCH PAPERS TO SUPABASE FORMAT
# ============================================================

supabase_research_papers = []


def map_single_id(local_id, mapping):
    """Convert one local ID to its Supabase UUID."""
    if local_id is None:
        return None

    return mapping.get(str(local_id))


def map_id_list(local_ids, mapping):
    """Convert a list of local IDs to Supabase UUIDs."""
    if not local_ids:
        return []

    mapped_ids = []

    for local_id in local_ids:
        mapped_id = mapping.get(str(local_id))

        if mapped_id is not None:
            mapped_ids.append(mapped_id)

    return list(dict.fromkeys(mapped_ids))


for paper in prepared_research_papers:

    supabase_paper = {
        "id": map_single_id(
            paper["id"],
            id_mappings["research_papers"]
        ),

        "name": paper["name"],

        "publication_date": paper.get(
            "publication_date"
        ),

        "volume": paper.get("volume"),

        "issue": paper.get("issue"),

        "page_numbers": paper.get(
            "page_numbers"
        ),

        "doi": paper.get("doi"),

        "is_open_access": paper.get(
            "is_open_access"
        ),

        "open_access_url": paper.get(
            "open_access_url"
        ),

        "primary_url": paper.get(
            "primary_url"
        ),

        "publication_type": paper.get(
            "publication_type"
        ),

        "incoming_citation_count": paper.get(
            "incoming_citation_count"
        ),

        "keywords": paper.get("keywords") or [],

        # We are not mapping outgoing citations yet.
        # The collector currently does not provide usable
        # local research-paper IDs for this relationship.
        "outgoing_citations": [],

        "journal_id": map_single_id(
            paper.get("journal_id"),
            id_mappings["journals"]
        ),

        "university_ids": map_id_list(
            paper.get("university_ids", []),
            id_mappings["universities"]
        ),

        "faculty_ids": map_id_list(
            paper.get("faculty_ids", []),
            id_mappings["faculties"]
        ),

        "academic_ids": map_id_list(
            paper.get("academic_ids", []),
            id_mappings["academics"]
        )
    }

    supabase_research_papers.append(
        supabase_paper
    )


# ============================================================
# 12. VALIDATE SUPABASE RESEARCH PAPERS
# ============================================================

missing_paper_uuid = [
    paper
    for paper in supabase_research_papers
    if not paper["id"]
]

missing_academic_relationship = [
    paper
    for paper in supabase_research_papers
    if not paper["academic_ids"]
]

missing_university_relationship = [
    paper
    for paper in supabase_research_papers
    if not paper["university_ids"]
]


print("\n=== SUPABASE CONVERSION ===")

print(
    "Converted research papers:",
    len(supabase_research_papers)
)

print(
    "Missing paper UUID:",
    len(missing_paper_uuid)
)

print(
    "Missing academic relationships:",
    len(missing_academic_relationship)
)

print(
    "Missing university relationships:",
    len(missing_university_relationship)
)


# ============================================================
# 13. SAVE SUPABASE-READY PAPERS
# ============================================================

SUPABASE_PAPERS_FILE = os.path.join(
    CLEANED_DATA_DIR,
    "research_papers_supabase.json"
)

with open(
    SUPABASE_PAPERS_FILE,
    "w",
    encoding="utf-8"
) as file:
    json.dump(
        supabase_research_papers,
        file,
        indent=2,
        ensure_ascii=False
    )


print(
    f"\nSupabase-ready papers saved to: "
    f"{SUPABASE_PAPERS_FILE}"
)