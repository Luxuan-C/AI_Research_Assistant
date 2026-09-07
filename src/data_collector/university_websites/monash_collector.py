import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


DIRECTORY_URLS = [
    (
        "https://research.monash.edu/"
        "en/organisations/"
        "department-of-data-science-ai/persons/"
    ),
    (
        "https://research.monash.edu/"
        "en/organisations/"
        "department-of-software-systems-cybersecurity/"
        "persons/"
    )
]

UNIVERSITY_NAME = "Monash University"

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

    return " ".join(
        value.split()
    )


def collect_directory_links(
    directory_url
):
    """
    Collects profile URLs from one Monash Pure department.
    """

    profile_links = set()

    page_number = 0

    while True:
        print(
            f"Monash directory page "
            f"{page_number + 1}"
        )

        params = {
            "page": page_number
        }

        response = requests.get(
            directory_url,
            params=params,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
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
                    directory_url,
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

        next_link = soup.find(
            "a",
            attrs={
                "rel": "next"
            }
        )

        if not next_link:
            break

        page_number += 1

        time.sleep(
            REQUEST_DELAY
        )

    return profile_links


def collect_profile_links():
    """
    Combines people from all selected Monash departments.
    """

    all_links = set()

    for directory_url in DIRECTORY_URLS:
        print(
            "\nMonash department:"
        )
        print(
            directory_url
        )

        try:
            links = collect_directory_links(
                directory_url
            )

            all_links.update(
                links
            )

        except requests.RequestException as error:
            print(
                f"Monash directory failed: "
                f"{error}"
            )

    return sorted(
        all_links
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
            values.append(
                text
            )

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
            f"Monash profile failed: "
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


def collect_monash():
    print("\nCollecting Monash University...")

    profile_links = collect_profile_links()

    print(
        f"Monash unique profiles found: "
        f"{len(profile_links)}"
    )

    academics = []

    for index, profile_url in enumerate(
        profile_links,
        start=1
    ):
        print(
            f"Monash: {index}/"
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
        f"Monash collected: "
        f"{len(academics)}"
    )

    return academics


if __name__ == "__main__":
    results = collect_monash()

    for result in results[:5]:
        print(result)