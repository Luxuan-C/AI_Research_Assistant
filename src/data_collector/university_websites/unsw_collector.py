from playwright.sync_api import sync_playwright
from urllib.parse import urlencode
import time
import re
import requests
from bs4 import BeautifulSoup


UNSW_PAGE_URL = (
    "https://www.unsw.edu.au/engineering/about-us/our-people"
    "#search=&filters=f.School%257CstaffSchool%3A"
    "Computer%2BScience%2Band%2BEngineering"
    "&sort=metastaffLastName"
    "&startRank=1"
    "&numRanks=12"
)

RESULTS_PER_PAGE = 12
REQUEST_DELAY = 1


def normalise_result(result):
    """
    Converts one UNSW Funnelback result into our
    common academic format.
    """

    metadata = result.get(
        "metaData",
        {}
    )

    name = (
        metadata.get("staffFullName")
        or result.get("title")
    )

    position = metadata.get(
        "staffRole"
    )

    profile_url = (
        result.get("liveUrl")
        or result.get("displayUrl")
    )

    if not name:
        return None

    return {
        "name": name,
        "gender": None,
        "academic_position": position,
        "research_interests": [],
        "areas_of_expertise": [],
        "profile_url": profile_url,
        "orcid_url": None,
        "university_name": "UNSW Sydney"
    }

def clean_text(value):
    if not value:
        return ""

    return " ".join(value.split())


def extract_research_interests_from_text(text):
    """
    Extracts research interests only when the biography
    explicitly describes them.
    """

    if not text:
        return []

    patterns = [
        r"research interests lie at\s+(.+?)(?:\.|$)",
        r"research interests include\s+(.+?)(?:\.|$)",
        r"research interests are\s+(.+?)(?:\.|$)",
        r"research focuses on\s+(.+?)(?:\.|$)",
        r"research focus is\s+(.+?)(?:\.|$)",
        r"research areas include\s+(.+?)(?:\.|$)",
        r"interested in\s+(.+?)(?:\.|$)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            interests_text = match.group(1)

            # Remove introductory wording
            interests_text = re.sub(
                r"^(?:in\s+)?(?:the\s+)?intersection\s+of\s+",
                "",
                interests_text,
                flags=re.IGNORECASE
            )

            interests_text = re.sub(
                r"^in\s+",
                "",
                interests_text,
                flags=re.IGNORECASE
            )

            interests_text = interests_text.replace(
                " and ",
                ", "
            )

            interests_text = interests_text.replace(
                " especially ",
                ", "
            )

            return [
                item.strip(" .—-")
                for item in interests_text.split(",")
                if item.strip()
            ]


def enrich_unsw_profile(academic):
    """
    Visits the UNSW staff profile and extracts explicit
    research interests from the biography/about text.
    """

    profile_url = academic.get("profile_url")

    if not profile_url:
        return academic

    try:
        response = requests.get(
            profile_url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=20
        )

        response.raise_for_status()

    except requests.RequestException as error:
        print(
            f"UNSW profile enrichment failed: "
            f"{profile_url} - {error}"
        )

        return academic

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    page_text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    academic["research_interests"] = (
        extract_research_interests_from_text(
            page_text
        )
    )

    # Leave these empty unless explicitly available.
    academic["areas_of_expertise"] = []
    academic["orcid_url"] = None

    return academic


def collect_unsw():
    """
    Collects UNSW Computer Science and Engineering staff
    using Playwright because the Funnelback API is protected
    by Cloudflare.
    """

    print("\nCollecting UNSW...")

    academics = []

    start_rank = 1

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page()

        while True:
            page_url = (
                "https://www.unsw.edu.au/engineering/about-us/our-people"
                "#search=&filters=f.School%257CstaffSchool%3A"
                "Computer%2BScience%2Band%2BEngineering"
                "&sort=metastaffLastName"
                f"&startRank={start_rank}"
                "&numRanks=12"
            )

            print(
                f"UNSW: requesting ranks "
                f"{start_rank}-"
                f"{start_rank + RESULTS_PER_PAGE - 1}"
            )

            try:
                with page.expect_response(
                    lambda response: (
                        "search.html" in response.url
                        and "form=json" in response.url
                        and f"start_rank={start_rank}" in response.url
                    ),
                    timeout=30000
                ) as response_info:

                    page.goto(
                        page_url,
                        wait_until="domcontentloaded"
                    )

                response = response_info.value

                data = response.json()

                results = (
                    data
                    .get("response", {})
                    .get("resultPacket", {})
                    .get("results", [])
                )

            except Exception as error:
                print(
                    f"UNSW page failed at rank "
                    f"{start_rank}: {error}"
                )
                break

            print(
                f"UNSW results returned: "
                f"{len(results)}"
            )

            if not results:
                break

            for result in results:
                academic = normalise_result(
                    result
                )

                if academic:
                    academic = enrich_unsw_profile(
                        academic
                    )

                    academics.append(
                        academic
                    )

                    time.sleep(
                        REQUEST_DELAY
                    )

            if len(results) < RESULTS_PER_PAGE:
                break

            start_rank += RESULTS_PER_PAGE

            time.sleep(
                REQUEST_DELAY
            )

        browser.close()

    print(
        f"UNSW collected: "
        f"{len(academics)}"
    )

    return academics

if __name__ == "__main__":

    results = collect_unsw()

    for result in results[:5]:
        print(result)