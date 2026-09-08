import json
from collections import defaultdict

FILE = "data/university_academics.json"

with open(FILE, "r", encoding="utf-8") as f:
    academics = json.load(f)

stats = defaultdict(lambda: {
    "total": 0,
    "position": 0,
    "research_interests": 0,
    "expertise": 0,
    "orcid": 0
})

for academic in academics:
    university = academic.get("university_name", "Unknown")

    stats[university]["total"] += 1

    if academic.get("academic_position"):
        stats[university]["position"] += 1

    if academic.get("research_interests"):
        stats[university]["research_interests"] += 1

    if academic.get("areas_of_expertise"):
        stats[university]["expertise"] += 1

    if academic.get("orcid_url"):
        stats[university]["orcid"] += 1


def display(value, total):
    percentage = value / total * 100 if total else 0
    return f"{value} ({percentage:.1f}%)"


print(
    f"{'University':<40}"
    f"{'Total':>7}"
    f"{'Position':>18}"
    f"{'Interests':>18}"
    f"{'Expertise':>18}"
    f"{'ORCID':>18}"
)

print("-" * 119)

for university, s in stats.items():
    total = s["total"]

    print(
        f"{university:<40}"
        f"{total:>7}"
        f"{display(s['position'], total):>18}"
        f"{display(s['research_interests'], total):>18}"
        f"{display(s['expertise'], total):>18}"
        f"{display(s['orcid'], total):>18}"
    )


print("\n\nDATA QUALITY CHECKS")
print("=" * 80)

# Words that may indicate people outside our intended academic scope
suspicious_positions = [
    "student",
    "phd",
    "candidate",
    "administrator",
    "administration",
    "professional staff",
    "project officer",
    "research assistant",
    "honours"
]

missing_names = []
missing_profiles = []
suspicious_roles = []
long_interests = []
duplicate_profiles = {}
duplicate_orcids = {}
names_across_universities = {}

for academic in academics:

    name = academic.get("name")
    university = academic.get("university_name")
    position = academic.get("academic_position")
    profile = academic.get("profile_url")
    orcid = academic.get("orcid_url")
    interests = academic.get("research_interests", [])

    # -------------------------
    # Missing important fields
    # -------------------------

    if not name:
        missing_names.append(academic)

    if not profile:
        missing_profiles.append(academic)

    # -------------------------
    # Suspicious positions
    # -------------------------

    if position:
        position_lower = position.lower()

        if any(word in position_lower for word in suspicious_positions):
            suspicious_roles.append({
                "name": name,
                "university": university,
                "position": position,
                "profile_url": profile
            })

    # -------------------------
    # Suspicious research interests
    # -------------------------

    for interest in interests:
        if isinstance(interest, str) and len(interest) > 250:
            long_interests.append({
                "name": name,
                "university": university,
                "interest": interest[:200] + "..."
            })

    # -------------------------
    # Duplicate profile URLs
    # -------------------------

    if profile:
        duplicate_profiles.setdefault(profile, []).append(academic)

    # -------------------------
    # Duplicate ORCIDs
    # -------------------------

    if orcid:
        duplicate_orcids.setdefault(orcid, []).append(academic)

    # -------------------------
    # Same name across universities
    # -------------------------

    if name:
        normalized_name = name.lower().strip()

        names_across_universities.setdefault(
            normalized_name, []
        ).append(academic)


# Keep only actual duplicates
duplicate_profiles = {
    key: value
    for key, value in duplicate_profiles.items()
    if len(value) > 1
}

duplicate_orcids = {
    key: value
    for key, value in duplicate_orcids.items()
    if len(value) > 1
}

cross_university_names = {}

for name, records in names_across_universities.items():

    universities = {
        record.get("university_name")
        for record in records
    }

    if len(universities) > 1:
        cross_university_names[name] = records


# -------------------------
# Print summary
# -------------------------

print(f"Missing names: {len(missing_names)}")
print(f"Missing profile URLs: {len(missing_profiles)}")
print(f"Suspicious positions: {len(suspicious_roles)}")
print(f"Very long research interests: {len(long_interests)}")
print(f"Duplicate profile URLs: {len(duplicate_profiles)}")
print(f"Duplicate ORCIDs: {len(duplicate_orcids)}")
print(f"Same names across universities: {len(cross_university_names)}")


# -------------------------
# Print suspicious roles
# -------------------------

print("\nSUSPICIOUS POSITIONS")
print("-" * 80)

for person in suspicious_roles:
    print(
        f"{person['name']} | "
        f"{person['university']} | "
        f"{person['position']}"
    )


# -------------------------
# Print long interests
# -------------------------

print("\nSUSPICIOUSLY LONG RESEARCH INTERESTS")
print("-" * 80)

for person in long_interests[:30]:
    print(
        f"\n{person['name']} | "
        f"{person['university']}\n"
        f"{person['interest']}"
    )


# -------------------------
# Print duplicate ORCIDs
# -------------------------

print("\nDUPLICATE ORCIDS")
print("-" * 80)

for orcid, records in duplicate_orcids.items():

    print(f"\n{orcid}")

    for record in records:
        print(
            f"  {record.get('name')} | "
            f"{record.get('university_name')}"
        )


# -------------------------
# Print same names at different universities
# -------------------------

print("\nSAME NAME ACROSS UNIVERSITIES")
print("-" * 80)

for name, records in cross_university_names.items():

    print(f"\n{name}")

    for record in records:
        print(
            f"  {record.get('name')} | "
            f"{record.get('university_name')} | "
            f"{record.get('orcid_url')}"
        )