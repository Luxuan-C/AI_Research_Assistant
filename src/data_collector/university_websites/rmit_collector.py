import time
import re
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin


# ============================================================
# CONFIG
# ============================================================

DIRECTORY_URL = (
    "https://www.rmit.edu.au/about/schools-colleges/"
    "computing-technologies/people"
)

UNIVERSITY_NAME = "RMIT University"

REQUEST_DELAY = 1
TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
}


# ============================================================
# BASIC CLEANING
# ============================================================

def clean_text(value):
    if not value:
        return None

    text = " ".join(value.split())

    unwanted = [
        "Expand for full bio",
        "Collapse full bio",
        "Read more",
        "Read less",
        "View more",
        "View less",
        "See full profile",
    ]

    for item in unwanted:
        text = text.replace(item, "")

    text = " ".join(text.split())

    return text or None


def remove_title_from_name(name):
    """
    Removes titles if they appear in the person's name.

    Example:
        Professor Karin Verspoor -> Karin Verspoor
        Dr. Qiang Fu             -> Qiang Fu
    """

    if not name:
        return None

    prefixes = [
        "Distinguished Professor ",
        "Emeritus Professor ",
        "Honorary Professor ",
        "Associate Professor ",
        "Professor ",
        "A/Prof ",
        "Dr. ",
        "Dr ",
        "Mr. ",
        "Mr ",
        "Ms. ",
        "Ms ",
        "Mrs. ",
        "Mrs ",
    ]

    cleaned = name.strip()

    for prefix in prefixes:
        if cleaned.lower().startswith(
            prefix.lower()
        ):
            cleaned = cleaned[
                len(prefix):
            ].strip()
            break

    return cleaned


# ============================================================
# DIRECTORY
# ============================================================

def collect_profile_links():
    """
    Collect all RMIT profile links from the
    School of Computing Technologies people page.
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

    links = set()

    for link in soup.find_all(
        "a",
        href=True
    ):
        href = link["href"]

        if "/profiles/" not in href:
            continue

        full_url = urljoin(
            DIRECTORY_URL,
            href
        )

        # Remove query strings/fragments
        full_url = (
            full_url
            .split("?")[0]
            .split("#")[0]
        )

        # Only keep Australian RMIT profile pages
        if (
            "rmit.edu.au/profiles/"
            not in full_url
        ):
            continue

        links.add(
            full_url
        )

    return sorted(links)


# ============================================================
# GENERIC SECTION HELPERS
# ============================================================

def find_heading(soup, names):
    """
    Find a h2/h3/h4 whose text matches one of the
    supplied section names.
    """

    wanted = {
        name.lower()
        for name in names
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


def extract_section_strings(soup, heading_names):
    """
    Extract strings appearing after a particular
    heading until the next h2/h3/h4.

    This works better than searching the entire page,
    because RMIT profiles have explicit sections such as:

        Research fields
        Academic positions
        Research interests
    """

    heading = find_heading(
        soup,
        heading_names
    )

    if not heading:
        return []

    results = []
    seen = set()

    for element in heading.next_elements:

        if element is heading:
            continue

        # Stop at the next section heading
        if (
            getattr(element, "name", None)
            in ["h2", "h3", "h4"]
        ):
            break

        # We only want text nodes
        if not isinstance(
            element,
            str
        ):
            continue

        text = clean_text(
            element
        )

        if not text:
            continue

        lower = text.lower()

        # Ignore interface noise
        ignored = [
            "image",
            "see full profile",
            "expand for full bio",
            "collapse full bio",
        ]

        if lower in ignored:
            continue

        if lower in seen:
            continue

        seen.add(lower)
        results.append(text)

    return results


# ============================================================
# NAME
# ============================================================

def extract_name(soup):
    """
    RMIT's main h1 normally contains the clean name.
    """

    heading = soup.find("h1")

    if not heading:
        return None

    name = clean_text(
        heading.get_text(
            " ",
            strip=True
        )
    )

    return remove_title_from_name(
        name
    )


# ============================================================
# ORCID
# ============================================================

def extract_orcid(soup):
    """
    Extract full ORCID URL.
    """

    for link in soup.find_all(
        "a",
        href=True
    ):
        href = link["href"].strip()

        if "orcid.org/" not in href:
            continue

        # Sometimes URLs may omit protocol
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

    # Fallback: search visible page text
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


# ============================================================
# POSITION
# ============================================================

def extract_position(soup):
    page_text = soup.get_text(
        " ",
        strip=True
    )

    positions = [
        "Distinguished Professor",
        "Emeritus Professor",
        "Associate Professor",
        "Professor",
        "Principal Research Fellow",
        "Senior Research Fellow",
        "Research Fellow",
        "Senior Lecturer",
        "Lecturer"
    ]

    for position in positions:
        if position.lower() in page_text.lower():
            return position

    return None

# ============================================================
# RESEARCH FIELDS / EXPERTISE
# ============================================================

def extract_research_fields(soup):
    lines = extract_section_strings(
        soup,
        [
            "Research fields",
            "Research field",
        ]
    )

    expertise = []

    bad_expertise_terms = [
        "research interests section",
        "teaching interests section",
        "research interests",
        "teaching interests",
        "section",
    ]

    for line in lines:
        line = clean_text(line)

        if not line:
            continue

        cleaned = re.sub(
            r"^\d{2,6}\s+",
            "",
            line
        ).strip()

        if not cleaned:
            continue

        lower = cleaned.lower()

        if any(
            bad == lower
            for bad in bad_expertise_terms
        ):
            continue

        if re.fullmatch(
            r"\d+",
            cleaned
        ):
            continue

        if any(
            cleaned.lower()
            == existing.lower()
            for existing in expertise
        ):
            continue

        expertise.append(cleaned)

    return expertise

def remove_duplicates(values):
    cleaned = []
    seen = set()

    for value in values:
        value = clean_text(value)

        if not value:
            continue

        key = value.lower()

        if key in seen:
            continue

        seen.add(key)
        cleaned.append(value)

    return cleaned

def split_research_interest_text(text):
    """
    Turn an RMIT research-interest block into a list.

    Handles:
        commas
        semicolons
        bullet-like lines

    It avoids aggressively splitting on 'and' because
    legitimate topics may contain the word 'and'.
    """

    if not text:
        return []

    text = clean_text(
        text
    )

    if not text:
        return []

    # Replace bullet characters with delimiter
    text = re.sub(
        r"[•●▪◦]\s*",
        ";",
        text
    )

    # A line beginning with "-" is usually a bullet
    text = re.sub(
        r"\s+-\s+",
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
                " -:;"
            )
        )

        if not part:
            continue

        # Do not keep interface text
        if part.lower() in [
            "read more",
            "read less",
            "view more",
            "view less",
        ]:
            continue

        if any(
            part.lower()
            == existing.lower()
            for existing
            in results
        ):
            continue

        results.append(
            part
        )

    return results


def extract_research_interests(soup):
    """
    Extract only clean content from the explicit
    Research interests section.

    Avoid scripts, navigation text and page components.
    """

    results = []

    headings = soup.find_all(
        ["h2", "h3", "h4", "h5"]
    )

    research_heading = None

    for heading in headings:
        text = clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

        if (
            text
            and text.lower()
            == "research interests"
        ):
            research_heading = heading
            break

    if not research_heading:
        return []

    element = research_heading.find_next_sibling()

    while element:

        # Stop at next section
        if element.name in [
            "h2",
            "h3",
            "h4",
            "h5"
        ]:
            break

        # Never collect scripts/styles
        if element.name in [
            "script",
            "style",
            "noscript"
        ]:
            element = element.find_next_sibling()
            continue

        # Lists are ideal because they usually
        # represent individual research topics.
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

                if is_valid_research_text(text):
                    results.append(text)

        # Paragraph fallback
        elif element.name == "p":

            text = clean_text(
                element.get_text(
                    " ",
                    strip=True
                )
            )

            if is_valid_research_text(text):
                results.append(text)

        element = element.find_next_sibling()

    return remove_duplicates(results)
# ============================================================
# OPTIONAL BIOGRAPHY FALLBACK
# ============================================================

def extract_interest_from_about(soup):
    """
    Optional fallback for researchers who do not have an
    explicit Research interests section.

    Only extracts sentences that explicitly say things like:

        "research interests are..."
        "research focuses on..."
        "research primarily focuses on..."

    It does NOT store the whole biography.
    """

    explicit_interests = (
        extract_research_interests(
            soup
        )
    )

    if explicit_interests:
        return explicit_interests

    lines = extract_section_strings(
        soup,
        [
            "About",
        ]
    )

    if not lines:
        return []

    about_text = " ".join(
        lines
    )

    patterns = [
        (
            r"research interests are "
            r"(.*?)(?:\.|$)"
        ),
        (
            r"research interests include "
            r"(.*?)(?:\.|$)"
        ),
        (
            r"research primarily focuses on "
            r"(.*?)(?:\.|$)"
        ),
        (
            r"research focuses on "
            r"(.*?)(?:\.|$)"
        ),
        (
            r"research focus is "
            r"(.*?)(?:\.|$)"
        ),
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            about_text,
            flags=re.IGNORECASE
        )

        if not match:
            continue

        value = match.group(1)

        return (
            split_research_interest_text(
                value
            )
        )

    return []


# ============================================================
# PROFILE
# ============================================================

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
            f"RMIT profile failed: "
            f"{profile_url} - {error}"
        )

        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    name = extract_name(
        soup
    )

    if not name:
        print(
            f"RMIT missing name: "
            f"{profile_url}"
        )

        return None

    position = extract_position(
        soup
    )

    research_interests = (
        extract_interest_from_about(
            soup
        )
    )

    areas_of_expertise = (
        extract_research_fields(
            soup
        )
    )

    return {
        "name": name,
        "gender": None,

        "academic_position": (
            position
        ),

        "research_interests": (
            research_interests
        ),

        "areas_of_expertise": (
            areas_of_expertise
        ),

        "profile_url": (
            profile_url
        ),

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
# MAIN COLLECTOR
# ============================================================

def collect_rmit():
    print(
        "\nCollecting RMIT University..."
    )

    try:
        profile_links = (
            collect_profile_links()
        )

    except requests.RequestException as error:

        print(
            f"RMIT directory failed: "
            f"{error}"
        )

        return []

    print(
        f"RMIT profiles found: "
        f"{len(profile_links)}"
    )

    academics = []

    for index, profile_url in enumerate(
        profile_links,
        start=1
    ):

        print(
            f"RMIT: "
            f"{index}/"
            f"{len(profile_links)}"
        )

        academic = scrape_profile(
            profile_url
        )

        if academic:
            academics.append(
                academic
            )

        time.sleep(
            REQUEST_DELAY
        )

    print(
        f"RMIT collected: "
        f"{len(academics)}"
    )

    return academics


# ============================================================
# RUN DIRECTLY
# ============================================================

if __name__ == "__main__":

    results = collect_rmit()

    print(
        "\nSAMPLE RESULTS"
    )

    print(
        "=" * 80
    )

    for result in results[:10]:
        print(
            result
        )