import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


DIRECTORY_URL = (
    "https://eecs.uq.edu.au/about/our-people"
)

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


def clean_text(value):
    if not value:
        return None
    return " ".join(value.split())


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

        if "/profile/" in href:
            full_url = urljoin(
                DIRECTORY_URL,
                href
            )

            links.add(full_url)

    return sorted(links)


def extract_orcid(soup):
    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "orcid.org/" in href:
            return href

    return None


def extract_name(soup):
    heading = soup.find("h1")

    if heading:
        return clean_text(
            heading.get_text(
                " ",
                strip=True
            )
        )

    return None


def extract_position(soup):
    page_text = soup.get_text(
        " ",
        strip=True
    )

    positions = [
        "Emeritus Professor",
        "Professor",
        "Associate Professor",
        "Senior Lecturer",
        "Lecturer",
        "Senior Research Fellow",
        "Research Fellow"
    ]

    for position in positions:
        if position.lower() in page_text.lower():
            return position

    return None


def extract_section(soup, heading_terms):
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

    return results


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

    return {
        "name": name,
        "gender": None,
        "academic_position": extract_position(soup),

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
                "research areas"
            ]
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
        profile_links,
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

    for result in results[:5]:
        print(result)