import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


DIRECTORY_URL = "https://eecs.uq.edu.au/about/our-people"

UNIVERSITY_NAME = "The University of Queensland"

REQUEST_DELAY = 1
TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


# Positions that are clearly not academics/researchers
EXCLUDED_POSITION_TERMS = [
    "school manager",
    "project officer",
    "project support officer",
    "centre manager",
    "operations",
    "administration",
    "administrative",
    "technical officer",
    "student experience",
    "professional staff",
    "manager",
]


def clean_text(value):
    if not value:
        return None

    text = " ".join(value.split())

    unwanted_text = [
        "Read more",
        "Read less",
        "View all research interests",
        "View less",
    ]

    for unwanted in unwanted_text:
        text = text.replace(unwanted, "")

    return " ".join(text.split()) or None


def collect_profile_links():
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

    links = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "/profile/" not in href:
            continue

        full_url = urljoin(
            DIRECTORY_URL,
            href
        )

        # Keep only UQ EECS profile URLs
        if "eecs.uq.edu.au/profile/" in full_url:
            links.add(full_url)

    return sorted(links)


def extract_orcid(soup):
    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "orcid.org/" in href:
            href = href.strip()

            if href.startswith("http"):
                return href

            return urljoin(
                "https://orcid.org",
                href
            )

    return None


def extract_name(soup):
    heading = soup.find("h1")

    if not heading:
        return None

    name = clean_text(
        heading.get_text(
            " ",
            strip=True
        )
    )

    if not name:
        return None

    prefixes = [
        "Honorary Professor ",
        "Emeritus Professor ",
        "Associate Professor ",
        "Professor ",
        "Dr ",
        "Mr ",
        "Ms ",
        "Mrs ",
    ]

    for prefix in prefixes:
        if name.lower().startswith(prefix.lower()):
            name = name[len(prefix):].strip()
            break

    return name


def extract_position(soup):
    """
    Extract the first academic/research role from the UQ
    profile's explicit 'Positions' section.
    """

    position_titles = [
        "Distinguished Professor",
        "Emeritus Professor",
        "Honorary Professor",
        "Adjunct Professor",
        "Professorial Research Fellow",
        "Principal Research Fellow",
        "Senior Research Fellow",
        "Postdoctoral Research Fellow",
        "Postdoctoral Fellow",
        "Senior Research Officer",
        "Research Officer",
        "Research Fellow",
        "Associate Professor",
        "Senior Lecturer",
        "Associate Lecturer",
        "Lecturer",
        "Professor",
        "Research Engineer",
        "ARC Future Fellow",
        "Industry Research Fellow",
        "Westpac Fellow",
    ]

    # Find the explicit "Positions" heading
    positions_heading = None

    for heading in soup.find_all(
        ["h2", "h3", "h4"]
    ):
        heading_text = clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

        if (
            heading_text
            and heading_text.lower() == "positions"
        ):
            positions_heading = heading
            break

    if not positions_heading:
        return None

    # Collect text only from the Positions section
    section_text = []

    element = positions_heading.find_next_sibling()

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
            section_text.append(text)

        element = element.find_next_sibling()

    # Search each block in the order it appears.
    # This is important when a person has several positions.
    for text in section_text:
        lower = text.lower()

        for position in position_titles:
            if position.lower() in lower:

                # Preserve useful specialisation:
                #
                # Senior Lecturer - Interaction Design
                # Senior Lecturer in Neuroengineering

                start = lower.find(
                    position.lower()
                )

                result = text[start:]

                # Prevent organisation/faculty text
                # from being included after the title.
                stop_terms = [
                    " School of ",
                    " Faculty of ",
                    " Institute ",
                    " Centre for ",
                    " Center for ",
                ]

                for stop in stop_terms:
                    if stop in result:
                        result = result.split(
                            stop,
                            1
                        )[0]

                result = clean_text(result)

                # Avoid accidentally returning a
                # massive block
                if result and len(result) <= 100:
                    return result

                return position

    return None

def extract_exact_section(soup, heading_terms):
    """
    Extract content only when a heading closely matches one of the
    requested terms.

    This avoids the previous problem where the generic word
    'research' matched biographies, impact summaries, projects, etc.
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

        heading_lower = heading_text.lower()

        matched = any(
            term.lower() == heading_lower
            or term.lower() in heading_lower
            for term in heading_terms
        )

        if not matched:
            continue

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

    return results


def extract_research_interests(soup):
    raw_results = extract_exact_section(
        soup,
        [
            "research interests",
            "research interest",
        ]
    )

    interests = []

    for result in raw_results:
        if not result:
            continue

        # UQ often stores all interests in one
        # semicolon-separated block
        parts = result.split(";")

        for part in parts:
            part = clean_text(part)

            if not part:
                continue

            # Remove UI noise
            if part.lower() in [
                "read more",
                "read less"
            ]:
                continue

            if part not in interests:
                interests.append(part)

    return interests

def extract_expertise(soup):
    """
    Look for sections that are clearly describing research fields.
    """

    results = extract_exact_section(
        soup,
        [
            "fields of research",
            "research areas",
            "areas of expertise",
            "expertise",
        ]
    )

    cleaned = []

    for result in results:

        result = clean_text(result)

        if not result:
            continue

        # Skip obvious UI/navigation strings
        if result.lower() in [
            "read more",
            "read less",
        ]:
            continue

        if result not in cleaned:
            cleaned.append(result)

    return cleaned


def is_valid_academic(position):
    """
    Reject obvious administrative/professional staff.

    If position is missing, keep the record for now rather than
    accidentally deleting a genuine academic.
    """

    if not position:
        return True

    lower = position.lower()

    for term in EXCLUDED_POSITION_TERMS:
        if term in lower:
            return False

    return True


def scrape_profile(profile_url):
    try:
        response = requests.get(
            profile_url,
            headers=HEADERS,
            timeout=TIMEOUT
        )
        response.raise_for_status()

    except requests.RequestException as error:
        print(
            f"UQ profile failed: "
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

    position = extract_position(soup)

    if not is_valid_academic(position):
        print(
            f"UQ skipped non-academic: "
            f"{name} ({position})"
        )
        return None

    return {
        "name": name,
        "gender": None,
        "academic_position": position,

        "research_interests": (
            extract_research_interests(soup)
        ),

        "areas_of_expertise": (
            extract_expertise(soup)
        ),

        "profile_url": profile_url,
        "orcid_url": extract_orcid(soup),
        "university_name": UNIVERSITY_NAME
    }


def collect_uq():
    print(
        "\nCollecting University of Queensland..."
    )

    try:
        profile_links = collect_profile_links()

    except requests.RequestException as error:
        print(
            f"UQ directory failed: {error}"
        )
        return []

    print(
        f"UQ profiles found: "
        f"{len(profile_links)}"
    )

    academics = []

    for index, profile_url in enumerate(
        profile_links[:10],
        start=1
    ):
        print(
            f"UQ: {index}/"
            f"{len(profile_links)}"
        )

        academic = scrape_profile(
            profile_url
        )

        if academic:
            academics.append(academic)

        time.sleep(REQUEST_DELAY)

    print(
        f"UQ collected: "
        f"{len(academics)}"
    )

    return academics


if __name__ == "__main__":

    results = collect_uq()

    print("\nSAMPLE RESULTS")
    print("=" * 80)

    for result in results[:10]:
        print(result)