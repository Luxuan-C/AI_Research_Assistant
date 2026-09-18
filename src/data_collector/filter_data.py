import json
import os


# ============================================================
# CONFIGURATION
# ============================================================

RAW_DATA_DIR = "./data/raw"
CLEANED_DATA_DIR = "./data/cleaned"

# The 9 universities in project scope.
# OpenAlex IDs are used instead of names because institution
# display names can vary.
TARGET_OPENALEX_IDS = {
    "I165779595",  # The University of Melbourne
    "I129604602",  # The University of Sydney
    "I31746571",   # UNSW Sydney
    "I114017466",  # University of Technology Sydney
    "I99043593",   # Macquarie University
    "I56590836",   # Monash University
    "I82951845",   # RMIT University
    "I165143802",  # The University of Queensland
    "I118347636",  # Australian National University
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def load_json(filename):
    """Load a JSON file from the raw data directory."""
    path = os.path.join(RAW_DATA_DIR, filename)

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def write_cleaned_json(filename, data):
    """Write data to the cleaned data directory."""
    path = os.path.join(CLEANED_DATA_DIR, filename)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

def get_openalex_id(url):
    """
    Extract the OpenAlex ID from a URL.

    Example:
    https://openalex.org/I165779595
    -> I165779595
    """
    if not url:
        return None

    return url.rstrip("/").split("/")[-1]


def remove_duplicates(values):
    """Remove duplicate IDs while preserving their original order."""
    return list(dict.fromkeys(values))


# ============================================================
# LOAD RAW DATA
# ============================================================

universities = load_json("universities.json")
academics = load_json("academics.json")
research_papers = load_json("research_papers.json")


print("=== RAW DATA ===")
print(f"Universities: {len(universities)}")
print(f"Academics: {len(academics)}")
print(f"Research papers: {len(research_papers)}")


# ============================================================
# 1. FILTER TARGET UNIVERSITIES
# ============================================================

target_universities = [
    university
    for university in universities
    if get_openalex_id(university.get("openalex_id"))
    in TARGET_OPENALEX_IDS
]

target_university_ids = {
    university["id"]
    for university in target_universities
}


print("\n=== TARGET UNIVERSITIES ===")
print(f"Target universities found: {len(target_universities)}")

for university in target_universities:
    print(
        f"{university['id']} - "
        f"{university['name']} - "
        f"{get_openalex_id(university.get('openalex_id'))}"
    )


# ============================================================
# 2. FIND ACADEMICS AFFILIATED WITH TARGET UNIVERSITIES
# ============================================================

target_academics = [
    academic
    for academic in academics
    if any(
        university_id in target_university_ids
        for university_id in academic.get("university_ids", [])
    )
]

target_academic_ids = {
    academic["id"]
    for academic in target_academics
}


print("\n=== TARGET UNIVERSITY ACADEMICS ===")
print(f"Academics affiliated with target universities: "
      f"{len(target_academics)}")


# ============================================================
# 3. FILTER COMPUTER SCIENCE / IT RESEARCH PAPERS
# ============================================================
#
# IMPORTANT:
# data_collector.py already retrieves papers using:
#
# primary_topic.field.id = 17
#
# which is OpenAlex's Computer Science field.
#
# Therefore, research_papers.json is already CS-prioritised.
# Here we additionally require each paper to have at least one
# academic affiliated with one of the 9 target universities.
# ============================================================

filtered_research_papers = []

for paper in research_papers:

    # Keep only academics from target universities.
    filtered_academic_ids = [
        academic_id
        for academic_id in paper.get("academic_ids", [])
        if academic_id in target_academic_ids
    ]

    filtered_academic_ids = remove_duplicates(
        filtered_academic_ids
    )

    # Paper is outside our useful project scope if none of its
    # academics are affiliated with a target university.
    if not filtered_academic_ids:
        continue

    # Also derive university relationships from the retained academics.
    # This handles cases where OpenAlex provides an academic affiliation
    # but the paper-level institution relationship is incomplete.
    # Keep target universities directly associated with the paper.
    filtered_university_ids = [
        university_id
        for university_id in paper.get("university_ids", [])
        if university_id in target_university_ids
    ]

    # Also derive university relationships from the retained academics.
    # This handles cases where OpenAlex provides an academic affiliation
    # but the paper-level institution relationship is incomplete.
    for academic in target_academics:
        if academic["id"] in filtered_academic_ids:
            for university_id in academic.get("university_ids", []):
                if university_id in target_university_ids:
                    filtered_university_ids.append(university_id)

    filtered_university_ids = remove_duplicates(
        filtered_university_ids
    )

    filtered_paper = paper.copy()

    filtered_paper["academic_ids"] = filtered_academic_ids
    filtered_paper["university_ids"] = filtered_university_ids

    filtered_research_papers.append(filtered_paper)


print("\n=== COMPUTER SCIENCE / IT PAPERS ===")
print(f"Filtered research papers: "
      f"{len(filtered_research_papers)}")


# ============================================================
# 4. KEEP ONLY ACADEMICS USED BY THE FILTERED PAPERS
# ============================================================
#
# This avoids keeping target-university academics who are not
# actually connected to our final CS/IT paper dataset.
# ============================================================

used_academic_ids = set()

for paper in filtered_research_papers:
    used_academic_ids.update(
        paper.get("academic_ids", [])
    )


filtered_academics = [
    academic.copy()
    for academic in target_academics
    if academic["id"] in used_academic_ids
]


# ============================================================
# 5. CLEAN ACADEMIC RELATIONSHIPS
# ============================================================
#
# Keep only:
# - target university IDs
# - research papers that survived filtering
# ============================================================

filtered_paper_ids = {
    paper["id"]
    for paper in filtered_research_papers
}


for academic in filtered_academics:

    academic["university_ids"] = remove_duplicates([
        university_id
        for university_id in academic.get("university_ids", [])
        if university_id in target_university_ids
    ])

    academic["research_paper_ids"] = remove_duplicates([
        paper_id
        for paper_id in academic.get("research_paper_ids", [])
        if paper_id in filtered_paper_ids
    ])


print("\n=== FINAL ACADEMICS ===")
print(f"CS/IT academics: {len(filtered_academics)}")


# ============================================================
# 6. VALIDATION
# ============================================================

papers_without_academics = [
    paper
    for paper in filtered_research_papers
    if not paper.get("academic_ids")
]

papers_without_universities = [
    paper
    for paper in filtered_research_papers
    if not paper.get("university_ids")
]


print("\n=== VALIDATION ===")
print(f"Target universities: {len(target_universities)}")
print(f"CS/IT academics: {len(filtered_academics)}")
print(f"CS/IT research papers: {len(filtered_research_papers)}")
print(
    f"Papers without target academics: "
    f"{len(papers_without_academics)}"
)
print(
    f"Papers without target universities: "
    f"{len(papers_without_universities)}"
)

print("\n=== PAPERS WITHOUT TARGET UNIVERSITY IDs ===")

for paper in papers_without_universities:
    print(
        f"\nPaper ID: {paper['id']}",
        f"\nTitle: {paper['name']}",
        f"\nAcademic IDs: {paper.get('academic_ids', [])}",
        f"\nUniversity IDs: {paper.get('university_ids', [])}"
    )

    print("\nMatched academics:")

    for academic in filtered_academics:
        if academic["id"] in paper.get("academic_ids", []):
            print(
                academic["id"],
                "-",
                academic["name"],
                "- universities:",
                academic.get("university_ids", [])
            )


# ============================================================
# 7. SAVE FILTERED DATA
# ============================================================

os.makedirs(CLEANED_DATA_DIR, exist_ok=True)

write_cleaned_json(
    "universities.json",
    target_universities
)

write_cleaned_json(
    "academics.json",
    filtered_academics
)

write_cleaned_json(
    "research_papers.json",
    filtered_research_papers
)


print("\n=== COMPLETE ===")
print(f"Filtered data saved to: {CLEANED_DATA_DIR}")