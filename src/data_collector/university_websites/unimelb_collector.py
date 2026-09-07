import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


DIRECTORY_URL = "https://cis.unimelb.edu.au/people"

UNIVERSITY_NAME = "University of Melbourne"

REQUEST_DELAY = 1
TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


def clean_text(value):
    if not value:
        return None

    return " ".join(value.split())


def collect_profile_links():
    """
    Collects profile links from the UniMelb School of Computing
    and Information Systems people page.
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

    for link in soup.find_all("a", href=True):
        href = link["href"]

        # We only want likely staff/profile links.
        if (
            "findanexpert.unimelb.edu.au" in href
            or "/people/" in href
        ):
            full_url = urljoin(
                DIRECTORY_URL,
                href
            )

            if full_url != DIRECTORY_URL:
                links.add(full_url)

    return sorted(links)


def extract_orcid(soup):
    """
    Finds an ORCID URL if one exists on the page.
    """

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "orcid.org/" in href:
            return href

    return None


def extract_name(soup):
    heading = soup.find("h1")

    if heading:
        return clean_text(
            heading.get_text(" ", strip=True)
        )

    return None


def extract_position(soup):
    """
    Attempts to find a person's academic position.
    """

    possible_labels = [
        "Professor",
        "Associate Professor",
        "Senior Lecturer",
        "Lecturer",
        "Research Fellow",
        "Senior Research Fellow",
        "Academic"
    ]

    page_text = soup.get_text(
        " ",
        strip=True
    )

    for label in possible_labels:
        if label.lower() in page_text.lower():
            return label

    return None


def extract_section(soup, heading_terms):
    """
    Extracts text underneath headings such as
    Research Interests or Areas of Expertise.
    """

    results = []

    for heading in soup.find_all(
        ["h2", "h3", "h4"]
    ):
        heading_text = clean_text(
            heading.get_text(" ", strip=True)
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

    return results


def scrape_profile(profile_url):
    """
    Scrapes one UniMelb profile.
    """

    try:
        response = requests.get(
            profile_url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

    except requests.RequestException as error:
        print(
            f"UniMelb profile failed: "
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
        "academic_position": extract_position(
            soup
        ),
        "research_interests": extract_section(
            soup,
            [
                "research interests",
                "research"
            ]
        ),
        "areas_of_expertise": extract_section(
            soup,
            [
                "expertise",
                "fields of research"
            ]
        ),
        "profile_url": profile_url,
        "orcid_url": extract_orcid(soup),
        "university_name": UNIVERSITY_NAME
    }


def collect_unimelb():
    """
    Collects UniMelb Computing and Information Systems academics.
    """

    print("\nCollecting University of Melbourne...")

    try:
        profile_links = collect_profile_links()

    except requests.RequestException as error:
        print(
            f"UniMelb directory failed: "
            f"{error}"
        )
        return []

    print(
        f"UniMelb profile links found: "
        f"{len(profile_links)}"
    )

    academics = []

    for index, profile_url in enumerate(
        profile_links,
        start=1
    ):
        print(
            f"UniMelb: {index}/"
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
        f"UniMelb collected: "
        f"{len(academics)}"
    )

    return academics


if __name__ == "__main__":
    results = collect_unimelb()

    for result in results[:5]:
        print(result)