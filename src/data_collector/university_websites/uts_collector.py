import time
import requests
from bs4 import BeautifulSoup


API_URL = (
    "https://profiles.uts.edu.au/"
    "api/users/membersOfGroup"
)

PROFILE_BASE_URL = (
    "https://profiles.uts.edu.au/"
)

GROUP_ID = 162

PER_PAGE = 25
REQUEST_DELAY = 1
TIMEOUT = 20


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Content-Type": "application/json"
}


def build_payload(start_from):
    """
    Builds the UTS School of Computer Science API request.
    """

    return {
        "groupId": GROUP_ID,

        "pagination": {
            "perPage": PER_PAGE,
            "startFrom": start_from
        },

        "sort": "lastNameAsc"
    }


def find_members(data):
    """
    Returns the list of UTS School of Computer Science members
    from the API response.
    """

    if not isinstance(data, dict):
        return []

    resource = data.get("resource")

    if isinstance(resource, list):
        return resource

    return []

def get_value(person, possible_keys):
    """
    Retrieves the first available field.
    """

    for key in possible_keys:

        value = person.get(key)

        if value not in (
            None,
            "",
            []
        ):
            return value

    return None


def build_profile_url(person):
    """
    Builds the UTS profile URL.
    """

    discovery_url_id = person.get("discoveryUrlId")

    if not discovery_url_id:
        return None

    return (
        "https://profiles.uts.edu.au/"
        + discovery_url_id
    )

def normalise_member(person):
    """
    Converts a UTS API member into our common academic format.
    """

    if not isinstance(person, dict):
        return None

    discovery_url_id = person.get("discoveryUrlId", "")

    # Exclude student profiles
    if discovery_url_id.lower().startswith("student_"):
        return None

    name = person.get("firstNameLastName")

    if not name:
        first_name = person.get("firstName", "")
        last_name = person.get("lastName", "")

        name = f"{first_name} {last_name}".strip()

    if not name:
        return None

    return {
        "name": name,
        "gender": None,
        "academic_position": person.get("title"),
        "research_interests": [],
        "areas_of_expertise": [],
        "profile_url": build_profile_url(person),
        "orcid_url": None,
        "university_name": "University of Technology Sydney"
    }
def clean_text(value):
    if not value:
        return None

    return " ".join(value.split())


def extract_orcid(soup):
    """
    Extracts ORCID from a UTS profile page.
    """

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "orcid.org/" in href:
            return href

    return None


def extract_section(soup, heading_terms):
    """
    Extracts text that appears under matching headings.
    """

    results = []

    for heading in soup.find_all(
        ["h2", "h3", "h4"]
    ):
        heading_text = clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

        if not heading_text:
            continue

        if any(
            term.lower() in heading_text.lower()
            for term in heading_terms
        ):
            element = heading.find_next_sibling()

            while element:
                if element.name in [
                    "h2",
                    "h3",
                    "h4"
                ]:
                    break

                text = clean_text(
                    element.get_text(
                        " ",
                        strip=True
                    )
                )

                if text:
                    results.append(text)

                element = element.find_next_sibling()

    return list(dict.fromkeys(results))



def extract_tags(profile):
    tags = profile.get("tags", {})

    if not isinstance(tags, dict):
        return []

    explicit = tags.get("explicit", [])

    results = []

    for tag in explicit:
        if isinstance(tag, dict):
            value = tag.get("value")
            if value:
                results.append(value)

    return results

def extract_orcid(profile):
    orcid = profile.get("orcid")

    if isinstance(orcid, dict):
        return orcid.get("uri")

    return None

import re


def extract_research_interests(profile):
    """
    Extracts research interests from the UTS profile summary text.
    """

    summary = profile.get("tabSummaryAbout", {})

    if not isinstance(summary, dict):
        return []

    text = (
        summary.get("htmlStripped")
        or summary.get("value")
        or ""
    )

    if not text:
        return []

    patterns = [
        r"areas of interest are\s+(.+?)(?:\.|$)",
        r"research interests include\s+(.+?)(?:\.|$)",
        r"research interests are\s+(.+?)(?:\.|$)",
        r"interests include\s+(.+?)(?:\.|$)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            interests_text = match.group(1)

            interests_text = interests_text.replace(
                " and ",
                ", "
            )

            interests = [
                item.strip(" .")
                for item in interests_text.split(",")
                if item.strip()
            ]

            return interests

    return []
    
def collect_uts():
    """
    Collects members of UTS School of Computer Science.
    """

    print("\nCollecting UTS...")

    academics = []

    start_from = 0

    while True:

        print(
            f"UTS: requesting results "
            f"{start_from + 1}-"
            f"{start_from + PER_PAGE}"
        )

        payload = build_payload(
            start_from
        )

        try:

            response = requests.post(
                API_URL,
                headers=HEADERS,
                json=payload,
                timeout=TIMEOUT
            )

            response.raise_for_status()

        except requests.RequestException as error:

            print(
                f"UTS request failed: "
                f"{error}"
            )

            break

        try:

            data = response.json()

        except ValueError:

            print(
                "UTS returned invalid JSON."
            )

            break

        members = find_members(
            data
        )

        if not members:

            print(
                "UTS: no more results."
            )

            break

        for member in members:
            discovery_url_id = member.get(
                "discoveryUrlId"
            )

            if not discovery_url_id:
                continue

            if discovery_url_id.lower().startswith(
                "student_"
            ):
                continue

            profile = get_profile_details(
                discovery_url_id
            )

            name = (
                profile.get(
                    "firstNameLastName"
                )
                or member.get(
                    "firstNameLastName"
                )
            )

            positions = profile.get(
                "positions",
                []
            )

            academic_position = None

            if positions:
                first_position = positions[0]

                if isinstance(
                    first_position,
                    dict
                ):
                    academic_position = (
                        first_position.get(
                            "position"
                        )
                    )

            if not academic_position:
                academic_position = (
                    profile.get("title")
                    or member.get("title")
                )

            academic = {
                "name": name,
                "gender": None,
                "academic_position": academic_position,
                "research_interests": extract_research_interests(
                    profile
                ),
                "areas_of_expertise": extract_tags(
                    profile
                ),
                "profile_url": (
                    "https://profiles.uts.edu.au/"
                    + discovery_url_id
                ),
                "orcid_url": extract_orcid(
                    profile
                ),
                "university_name": (
                    "University of Technology Sydney"
                )
            }

            academics.append(
                academic
            )

            time.sleep(
                REQUEST_DELAY
            )

        if len(members) < PER_PAGE:
            break

        start_from += PER_PAGE

        time.sleep(
            REQUEST_DELAY
        )

    print(
        f"UTS collected: "
        f"{len(academics)}"
    )

    return academics

def get_profile_details(discovery_url_id):
    """
    Get the full UTS profile JSON for one academic.
    """
    url = f"https://profiles.uts.edu.au/api/users/{discovery_url_id}"

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json"
            },
            timeout=20
        )
        response.raise_for_status()
        return response.json()

    except requests.RequestException as e:
        print(f"UTS profile failed for {discovery_url_id}: {e}")
        return {}




if __name__ == "__main__":

    results = collect_uts()

    for result in results[:5]:
        print(result)