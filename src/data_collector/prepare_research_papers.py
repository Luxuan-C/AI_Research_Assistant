import json
import os
import uuid
from collections import Counter


# ============================================================
# CONFIGURATION
# ============================================================

RAW_DATA_DIR = "./data/raw"
CLEANED_DATA_DIR = "./data/filtered"

RESEARCH_PAPERS_FILE = os.path.join(
    CLEANED_DATA_DIR,
    "research_papers.json"
)

MAPPINGS_FILE = os.path.join(
    CLEANED_DATA_DIR,
    "id_mappings.json"
)

SUPABASE_PAPERS_FILE = os.path.join(
    CLEANED_DATA_DIR,
    "research_papers_supabase.json"
)


# Existing university UUIDs from the team's Supabase database.
# These MUST be reused so papers point to existing university rows.
SUPABASE_UNIVERSITY_UUIDS = {
    "0": "c5198c6a-8f7d-4684-b1fc-782fa625ae9a",      # Melbourne
    "100": "570e618b-14b2-4ce6-8c70-7b2bd5284fd7",    # ANU
    "148": "e6384eb4-8ee5-4bcf-8a49-22146c29c4da",    # Sydney
    "149": "27c870c5-6b24-4889-bf1a-082d7b749c25",    # UNSW
    "181": "76ccfb81-7253-46d8-899e-25e39ba20023",    # Monash
    "263": "fdd57748-5185-4e73-863d-8304e834885d",    # Queensland
    "296": "2ff40b74-fefd-43dd-a0be-2540e9f25e43",    # UTS
    "921": "76197670-83f1-40ce-87c4-4172c6829f90",    # Macquarie
    "3646": "c062e483-3506-4add-813c-07885ef30eb2",   # RMIT
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def load_json(path):
    """Load a JSON file."""
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
    Non-numeric values such as "1-2" or "S1" become None.
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


def map_single_id(local_id, mapping):
    """Convert one local ID to its UUID."""
    if local_id is None:
        return None

    return mapping.get(str(local_id))


def map_id_list(local_ids, mapping):
    """Convert local IDs to UUIDs and remove duplicates."""
    if not local_ids:
        return []

    mapped_ids = []

    for local_id in local_ids:
        mapped_id = mapping.get(str(local_id))

        if mapped_id is not None:
            mapped_ids.append(mapped_id)

    return list(dict.fromkeys(mapped_ids))


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
# 3. CHECK REQUIRED FIELDS
# ============================================================

papers_without_name = [
    paper
    for paper in research_papers
    if not paper.get("name")
]

print("\n=== REQUIRED FIELDS ===")
print(f"Papers without name: {len(papers_without_name)}")


# ============================================================
# 4. CLEAN BASIC RESEARCH PAPER FIELDS
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
# 5. LOAD RELATED DATA
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
# 6. LOAD EXISTING UUID MAPPINGS
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
# 7. GENERATE / REUSE UUID MAPPINGS
# ============================================================

id_mappings = {
    "research_papers": generate_or_reuse_mapping(
        prepared_research_papers,
        existing_mappings.get("research_papers", {})
    ),

    # Use the UUIDs that already exist in Supabase.
    "universities": SUPABASE_UNIVERSITY_UUIDS.copy(),

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


# Preserve mappings created by prepare_academics.py.
if "disciplines" in existing_mappings:
    id_mappings["disciplines"] = existing_mappings["disciplines"]

if "fields" in existing_mappings:
    id_mappings["fields"] = existing_mappings["fields"]


# ============================================================
# 8. SAVE UUID MAPPINGS
# ============================================================

with open(
    MAPPINGS_FILE,
    "w",
    encoding="utf-8"
) as file:
    json.dump(
        id_mappings,
        file,
        indent=2,
        ensure_ascii=False
    )


print("\n=== UUID MAPPINGS ===")
print("Research papers:", len(id_mappings["research_papers"]))
print("Universities:", len(id_mappings["universities"]))
print("Academics:", len(id_mappings["academics"]))
print("Journals:", len(id_mappings["journals"]))
print("Faculties:", len(id_mappings["faculties"]))

if "disciplines" in id_mappings:
    print("Disciplines:", len(id_mappings["disciplines"]))

if "fields" in id_mappings:
    print("Fields:", len(id_mappings["fields"]))

print(f"\nUUID mappings saved to: {MAPPINGS_FILE}")


# ============================================================
# 9. CREATE OPENALEX PAPER LOOKUP
# ============================================================

# Allows:
#
# OpenAlex Work ID
#       ↓
# local paper ID
#       ↓
# Supabase paper UUID
#
# Only references to papers that are part of our 759-paper
# dataset are stored in outgoing_citations.

openalex_to_local_id = {
    paper["openalex_id"]: paper["id"]
    for paper in prepared_research_papers
    if paper.get("openalex_id")
}


# ============================================================
# 10. CONVERT RESEARCH PAPERS TO SUPABASE FORMAT
# ============================================================

supabase_research_papers = []

for paper in prepared_research_papers:

    paper_uuid = map_single_id(
        paper["id"],
        id_mappings["research_papers"]
    )

    outgoing_citations = [
        id_mappings["research_papers"][
            str(openalex_to_local_id[openalex_id])
        ]
        for openalex_id in paper.get("outgoing_citations", [])
        if (
            openalex_id in openalex_to_local_id
            and openalex_to_local_id[openalex_id] != paper["id"]
        )
    ]

    # Remove duplicate citation UUIDs while preserving order.
    outgoing_citations = list(
        dict.fromkeys(outgoing_citations)
    )

    supabase_paper = {
        "id": paper_uuid,

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

        "outgoing_citations": outgoing_citations,

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
# 11. VALIDATE SUPABASE RESEARCH PAPERS
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

all_paper_uuids = {
    paper["id"]
    for paper in supabase_research_papers
}

all_outgoing_citations = [
    citation
    for paper in supabase_research_papers
    for citation in paper["outgoing_citations"]
]

invalid_citations = [
    citation
    for citation in all_outgoing_citations
    if citation not in all_paper_uuids
]

self_citations = [
    paper
    for paper in supabase_research_papers
    if paper["id"] in paper["outgoing_citations"]
]

duplicate_citation_papers = [
    paper
    for paper in supabase_research_papers
    if len(paper["outgoing_citations"])
    != len(set(paper["outgoing_citations"]))
]


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

print(
    "Papers with outgoing citations:",
    sum(
        bool(paper["outgoing_citations"])
        for paper in supabase_research_papers
    )
)

print(
    "Total mapped outgoing citations:",
    len(all_outgoing_citations)
)

print(
    "Invalid citation UUIDs:",
    len(invalid_citations)
)

print(
    "Self-citations:",
    len(self_citations)
)

print(
    "Papers with duplicate citations:",
    len(duplicate_citation_papers)
)


# ============================================================
# 12. SAVE SUPABASE-READY PAPERS
# ============================================================

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