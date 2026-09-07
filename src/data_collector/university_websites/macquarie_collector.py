import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


DIRECTORY_URL = (
    "https://researchers.mq.edu.au/"
    "en/organisations/"
    "school-of-computing/persons/"
)

UNIVERSITY_NAME = "Macquarie University"

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


def get_directory_page(page_number):
    """
    Requests a Pure directory page.

    Pure commonly uses ?page=0, ?page=1, etc.
    """

    params = {
        "page": page_number
    }

    response = requests.get(
        DIRECTORY_URL,
        params=params,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    return response.text


def collect_profile_links():
    """
    Collects researcher profile URLs across directory pages.
    """

    profile_links = set()

    page_number = 0

    while True:
        print(
            f"Macquarie directory page "
            f"{page_number + 1}"
        )

        html = get_directory_page(
            page_number
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        page_links = set()

        for link in soup.find_all(
            "a",
            href=True
        ):
            href = link["href"]

            if "/en/persons/" in href:
                full_url = urljoin(
                    DIRECTORY_URL,
                    href
                )

                page_links.add(
                    full_url
                )

        new_links = (
            page_links
            - profile_links
        )

        if not new_links:
            break

        profile_links.update(
            new_links
        )

        # Earlier inspection showed 141 total,
        # so 3 pages should normally be enough.
        if page_number >= 2:
            break

        page_number += 1

        time.sleep(
            REQUEST_DELAY
        )

    return sorted(
        profile_links
    )


def extract_orcid(soup):
    for link in soup.find_all(
        "a",
        href=True
    ):
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
    """
    Looks for common Pure profile position information.
    """

    selectors = [
        ".person-details",
        ".relations",
        ".rendering_person"
    ]

    for selector in selectors:
        element = soup.select_one(
            selector
        )

        if element:
            text = clean_text(
                element.get_text(
                    " ",
                    strip=True
                )
            )

            if text:
                return text

    return None


def extract_keywords(soup):
    """
    Extracts visible Pure keyword/tag values.
    """

    values = []

    for element in soup.select(
        ".keyword, .concept, "
        ".research-output-keyword"
    ):
        text = clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )

        if text:
            values.append(text)

    return list(
        dict.fromkeys(values)
    )


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
            f"Macquarie profile failed: "
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

    keywords = extract_keywords(
        soup
    )

    return {
        "name": name,
        "gender": None,
        "academic_position": extract_position(
            soup
        ),
        "research_interests": keywords,
        "areas_of_expertise": keywords,
        "profile_url": profile_url,
        "orcid_url": extract_orcid(
            soup
        ),
        "university_name": UNIVERSITY_NAME
    }


def collect_macquarie():
    print("\nCollecting Macquarie University...")

    try:
        profile_links = collect_profile_links()

    except requests.RequestException as error:
        print(
            f"Macquarie directory failed: "
            f"{error}"
        )
        return []

    print(
        f"Macquarie profiles found: "
        f"{len(profile_links)}"
    )

    academics = []

    for index, profile_url in enumerate(
        profile_links,
        start=1
    ):
        print(
            f"Macquarie: {index}/"
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
        f"Macquarie collected: "
        f"{len(academics)}"
    )

    return academics


if __name__ == "__main__":
    results = collect_macquarie()

    for result in results[:5]:
        print(result)