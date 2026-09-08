import time
import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin


DIRECTORY_URL = "https://comp.anu.edu.au/people/"

UNIVERSITY_NAME = "Australian National University"

REQUEST_DELAY = 1
TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


# Clearly out-of-scope roles
EXCLUDED_ROLE_TERMS = [
    "phd student",
    "mphil student",
    "student",
    "software developer",
    "project officer",
    "education project officer",
    "technical officer",
    "operations",
    "administrator",
    "administration",
]


ACADEMIC_ROLE_TERMS = [
    "distinguished professor",
    "senior professor",
    "professor emeritus",
    "emeritus professor",
    "honorary professor",
    "professor",
    "associate professor",
    "honorary associate professor",
    "senior lecturer",
    "honorary senior lecturer",
    "lecturer",
    "honorary lecturer",
    "principal research fellow",
    "senior research fellow",
    "research fellow",
    "postdoctoral research fellow",
    "fellow",
    "casual sessional academic",
]


def clean_text(value):
    if not value:
        return None

    text = " ".join(value.split())

    unwanted = [
        "Read more",
        "Read less",
        "View more",
        "View less",
    ]

    for item in unwanted:
        text = text.replace(item, "")

    return " ".join(text.split()) or None


def remove_duplicates(values):
    results = []
    seen = set()

    for value in values:
        value = clean_text(value)

        if not value:
            continue

        key = value.lower()

        if key in seen:
            continue

        seen.add(key)
        results.append(value)

    return results


# ============================================================
# DIRECTORY
# ============================================================

def collect_directory_people():
    """
    Collect profile URL + name + role directly from
    the ANU School of Computing people directory.

    This is much safer than determining student status
    from the whole profile page.
    """

    response = requests.get(
        DIRECTORY_URL,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    people = []
    seen_urls = set()

    for link in soup.find_all(
        "a",
        href=True
    ):
        href = link["href"]

        if "/people/" not in href:
            continue

        full_url = urljoin(
            DIRECTORY_URL,
            href
        )

        full_url = (
            full_url
            .split("?")[0]
            .split("#")[0]
        )

        if (
            full_url.rstrip("/")
            == DIRECTORY_URL.rstrip("/")
        ):
            continue

        if full_url in seen_urls:
            continue

        text = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        # The directory link text normally contains:
        # Name + role + email/location
        lower = text.lower()

        # Reject student / admin profiles
        if any(
            term in lower
            for term in EXCLUDED_ROLE_TERMS
        ):
            continue

        role = None

        # Longer/more specific positions first
        sorted_roles = sorted(
            ACADEMIC_ROLE_TERMS,
            key=len,
            reverse=True
        )

        for role_term in sorted_roles:
            if role_term in lower:
                role = role_term
                break

        # Keep only academic/research-type people
        if not role:
            continue

        # Get name separately from profile later,
        # so no need to parse it perfectly here.
        people.append(
            {
                "profile_url": full_url,
                "directory_role": role,
            }
        )

        seen_urls.add(full_url)

    return people


# ============================================================
# PROFILE BASICS
# ============================================================

def extract_name(soup):
    heading = soup.find("h1")

    if not heading:
        return None

    return clean_text(
        heading.get_text(
            " ",
            strip=True
        )
    )


def extract_orcid(soup):
    for link in soup.find_all(
        "a",
        href=True
    ):
        href = link["href"].strip()

        if "orcid.org/" in href.lower():
            if href.startswith("http"):
                return href

            match = re.search(
                r"0000-\d{4}-\d{4}-\d{3}[\dX]",
                href,
                flags=re.IGNORECASE
            )

            if match:
                return (
                    "https://orcid.org/"
                    + match.group(0)
                )

    # Fallback: look anywhere in page text
    page_text = soup.get_text(
        " ",
        strip=True
    )

    match = re.search(
        r"0000-\d{4}-\d{4}-\d{3}[\dX]",
        page_text,
        flags=re.IGNORECASE
    )

    if match:
        return (
            "https://orcid.org/"
            + match.group(0)
        )

    return None


def extract_position(soup, directory_role=None):
    """
    Prefer the visible role directly under the h1.
    Fall back to the role found on the directory.
    """

    heading = soup.find("h1")

    if heading:
        checked = 0

        for element in heading.next_elements:
            if checked > 30:
                break

            if not isinstance(element, str):
                continue

            text = clean_text(element)

            if not text:
                continue

            lower = text.lower()

            for role in sorted(
                ACADEMIC_ROLE_TERMS,
                key=len,
                reverse=True
            ):
                if role in lower:
                    # Preserve useful suffixes such as:
                    # Professor, Acting Delegated Authority Research...
                    if len(text) <= 180:
                        return text

                    return role.title()

            checked += 1

    if directory_role:
        return directory_role.title()

    return None


# ============================================================
# SECTION EXTRACTION
# ============================================================

def find_section_heading(soup, heading_names):
    wanted = {
        value.lower()
        for value in heading_names
    }

    for heading in soup.find_all(
        ["h2", "h3", "h4"]
    ):
        text = clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        if text.lower() in wanted:
            return heading

    return None


def extract_section_text(soup, heading_names):
    """
    Extract text under an exact ANU section heading.
    """

    heading = find_section_heading(
        soup,
        heading_names
    )

    if not heading:
        return []

    results = []

    element = heading.find_next_sibling()

    while element:
        if element.name in [
            "h2",
            "h3",
            "h4"
        ]:
            break

        if element.name in [
            "script",
            "style",
            "noscript"
        ]:
            element = element.find_next_sibling()
            continue

        if element.name in ["ul", "ol"]:
            for item in element.find_all(
                "li",
                recursive=True
            ):
                text = clean_text(
                    item.get_text(
                        " ",
                        strip=True
                    )
                )

                if text:
                    results.append(text)

        elif element.name in [
            "p",
            "div"
        ]:
            text = clean_text(
                element.get_text(
                    " ",
                    strip=True
                )
            )

            if text:
                results.append(text)

        element = element.find_next_sibling()

    return remove_duplicates(results)


# ============================================================
# RESEARCH INTERESTS
# ============================================================

def split_interest_text(text):
    if not text:
        return []

    text = clean_text(text)

    if not text:
        return []

    text = re.sub(
        r"[•●▪◦]",
        ";",
        text
    )

    parts = re.split(
        r"[;,]",
        text
    )

    results = []

    for part in parts:
        part = clean_text(
            part.strip(
                " .;:-"
            )
        )

        if not part:
            continue

        if len(part) > 350:
            # Keep long explanatory paragraphs intact
            results.append(part)
            continue

        results.append(part)

    return remove_duplicates(results)


def extract_research_interests(soup):
    """
    ANU profiles use several headings:
      - Research Interests
      - Current Research Interests
      - Interests
      - Research

    Prefer explicit structured headings first.
    """

    explicit = extract_section_text(
        soup,
        [
            "Research Interests",
            "Current Research Interests",
        ]
    )

    if explicit:
        results = []

        for value in explicit:
            results.extend(
                split_interest_text(value)
            )

        return remove_duplicates(results)

    # Some ANU profiles use a clean "Interests" list.
    interests = extract_section_text(
        soup,
        [
            "Interests"
        ]
    )

    if interests:
        results = []

        for value in interests:
            results.extend(
                split_interest_text(value)
            )

        return remove_duplicates(results)

    # Last resort:
    # use Research section only if it explicitly talks
    # about research interests.
    research = extract_section_text(
        soup,
        [
            "Research"
        ]
    )

    for value in research:
        lower = value.lower()

        if (
            "research interests" in lower
            or "research focuses on" in lower
            or "my research" in lower
        ):
            return [value]

    return []


# ============================================================
# EXPERTISE
# ============================================================

def extract_expertise(soup):
    """
    ANU commonly exposes Clusters near the top of profiles.
    Use these as broad expertise/category information.

    Example:
      Intelligent Systems
      Computing Foundations
      Computational Science
    """

    results = []

    page_text = soup.get_text(
        "\n",
        strip=True
    )

    lines = [
        clean_text(line)
        for line in page_text.splitlines()
    ]

    known_clusters = [
        "Intelligent Systems",
        "Computing Foundations",
        "Computational Science",
        "Data Science",
        "Software Innovation Institute",
    ]

    for cluster in known_clusters:
        if cluster.lower() in page_text.lower():
            results.append(cluster)

    # If explicit research-interest items exist,
    # don't duplicate them here.
    return remove_duplicates(results)


# ============================================================
# PROFILE
# ============================================================

def scrape_profile(person):
    profile_url = person["profile_url"]

    try:
        response = requests.get(
            profile_url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

    except requests.RequestException as error:
        print(
            f"ANU profile failed: "
            f"{profile_url} - {error}"
        )
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    name = extract_name(soup)

    if not name:
        return None

    return {
        "name": name,
        "gender": None,

        "academic_position": (
            extract_position(
                soup,
                person.get(
                    "directory_role"
                )
            )
        ),

        "research_interests": (
            extract_research_interests(
                soup
            )
        ),

        "areas_of_expertise": (
            extract_expertise(
                soup
            )
        ),

        "profile_url": profile_url,

        "orcid_url": (
            extract_orcid(
                soup
            )
        ),

        "university_name": (
            UNIVERSITY_NAME
        )
    }


# ============================================================
# MAIN
# ============================================================

def collect_anu():
    print(
        "\nCollecting ANU..."
    )

    try:
        people = (
            collect_directory_people()
        )

    except requests.RequestException as error:
        print(
            f"ANU directory failed: "
            f"{error}"
        )
        return []

    print(
        f"ANU academic/research profiles found: "
        f"{len(people)}"
    )

    people = collect_directory_people()

    academics = []

    for index, person in enumerate(
        people,
        start=1
    ):
        print(
            f"ANU: {index}/"
            f"{len(people)}"
        )

        academic = scrape_profile(
            person
        )

        if academic:
            academics.append(
                academic
            )

        time.sleep(
            REQUEST_DELAY
        )

    print(
        f"ANU academics collected: "
        f"{len(academics)}"
    )

    return academics


if __name__ == "__main__":
    results = collect_anu()

    print(
        "\nSAMPLE RESULTS"
    )
    print(
        "=" * 80
    )

    for result in results:
        print(result)