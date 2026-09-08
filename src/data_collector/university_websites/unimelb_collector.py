import time
import re
import json

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


UNIVERSITY_NAME = "University of Melbourne"

DIRECTORY_URLS = [
    "https://cis.unimelb.edu.au/people/academic"
]

REQUEST_DELAY = 1


def clean_text(value):
    if not value:
        return None

    return " ".join(value.split())


def extract_research_interests(bio):
    """
    Extract explicitly stated research interests
    from the profile biography.
    """

    if not bio:
        return []

    soup = BeautifulSoup(
        bio,
        "html.parser"
    )

    text = soup.get_text(
        " ",
        strip=True
    )

    patterns = [
        r"research interests include\s+(.+?)(?:\.|$)",
        r"research interests are\s+(.+?)(?:\.|$)",
        r"research interests lie in\s+(.+?)(?:\.|$)",
        r"research interests lie at\s+(.+?)(?:\.|$)",
        r"research focuses on\s+(.+?)(?:\.|$)",
        r"research focus is\s+(.+?)(?:\.|$)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if not match:
            continue

        interests_text = match.group(1)

        interests_text = interests_text.replace(
            " and ",
            ", "
        )

        interests = []

        for item in interests_text.split(","):
            item = item.strip(
                " .;:-"
            )

            if not item:
                continue

            if any(
                item.lower()
                == existing.lower()
                for existing in interests
            ):
                continue

            interests.append(
                item
            )

        return interests

    return []


def clean_expertise(keywords):
    """
    Clean UniMelb research/publication keywords.
    """

    if not keywords:
        return []

    cleaned = []

    for item in keywords:
        if not item:
            continue

        # Some entries may unexpectedly not be strings
        if not isinstance(item, str):
            continue

        item = clean_text(item)

        if not item:
            continue

        # Remove SDG-style labels such as:
        # "7 Affordable and Clean Energy"
        if re.match(
            r"^\d+\s+",
            item
        ):
            continue

        if any(
            item.lower()
            == existing.lower()
            for existing in cleaned
        ):
            continue

        cleaned.append(
            item
        )

    return cleaned


def collect_directory_people():
    """
    Load the UniMelb CIS academic directory
    using Playwright and extract basic staff data.
    """

    people = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page()

        for directory_url in DIRECTORY_URLS:
            print(
                f"UniMelb directory: "
                f"{directory_url}"
            )

            try:
                page.goto(
                    directory_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )

                page.wait_for_timeout(2000)

            except Exception as error:
                print(
                    f"UniMelb directory failed: "
                    f"{error}"
                )
                continue

            soup = BeautifulSoup(
                page.content(),
                "html.parser"
            )

            for link in soup.find_all(
                "a",
                href=True
            ):
                href = link["href"]

                if (
                    "findanexpert.unimelb.edu.au/profile/"
                    not in href
                ):
                    continue

                profile_url = href.split("?")[0]

                if profile_url in seen_urls:
                    continue

                name = clean_text(
                    link.get_text(
                        " ",
                        strip=True
                    )
                )

                if not name:
                    continue

                position = None

                # Walk upwards through parent containers
                # until we find the staff card text.
                container = link

                for _ in range(5):
                    container = container.parent

                    if not container:
                        break

                    card_text = clean_text(
                        container.get_text(
                            " ",
                            strip=True
                        )
                    ) or ""

                    possible_positions = [
                        "Professor and Head of School",
                        "Associate Professor",
                        "Senior Lecturer",
                        "Lecturer",
                        "Professor",
                        "Senior Research Fellow",
                        "Research Fellow",
                        "Academic Specialist",
                        "Online Educator",
                    ]

                    for possible in possible_positions:
                        if (
                            possible.lower()
                            in card_text.lower()
                        ):
                            position = possible
                            break

                    if position:
                        break

                people.append(
                    {
                        "name": name,
                        "academic_position": position,
                        "profile_url": profile_url,
                    }
                )

                seen_urls.add(profile_url)

        browser.close()

    return people


def extract_profile_data(page, profile_url):
    """
    Enrich one UniMelb Find an Expert profile
    using window.__DATA__ from the browser.

    If structured data is unavailable,
    return None so directory data is preserved.
    """

    try:
        page.goto(
            profile_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(2500)

    except Exception as error:
        print(
            f"UniMelb profile failed: "
            f"{profile_url} - {error}"
        )
        return None

    # Detect interruption/block page
    title = page.title() or ""

    if "Pardon Our Interruption" in title:
        print(
            f"UniMelb blocked/interrupted: "
            f"{profile_url}"
        )
        return None

    # Read the actual JS object directly
    try:
        data = page.evaluate(
            "() => window.__DATA__ || null"
        )

    except Exception as error:
        print(
            f"UniMelb: could not read window.__DATA__ "
            f"for {profile_url} - {error}"
        )
        return None

    if not data:
        print(
            f"UniMelb: no structured data for "
            f"{profile_url}"
        )
        return None

    profile_data = None

    components = data.get(
        "components",
        []
    )

    for component in components:
        if not isinstance(
            component,
            dict
        ):
            continue

        profile = component.get(
            "profile"
        )

        if isinstance(
            profile,
            dict
        ):
            profile_data = profile
            break

    if not profile_data:
        print(
            f"UniMelb: no profile object for "
            f"{profile_url}"
        )
        return None

    name = profile_data.get(
        "display_name"
    )

    position = profile_data.get(
        "position"
    )

    if not position:
        organisation_objects = (
            profile_data.get(
                "organisation_objects",
                []
            )
        )

        for organisation in organisation_objects:
            if not isinstance(
                organisation,
                dict
            ):
                continue

            possible_position = (
                organisation.get(
                    "organisation_position_title"
                )
            )

            if possible_position:
                position = possible_position
                break

    orcid = profile_data.get(
        "orc_id"
    )

    bio = profile_data.get(
        "bio",
        ""
    )

    keywords = []

    publication_keywords = (
        profile_data.get(
            "publication_keywords",
            []
        )
    )

    if isinstance(
        publication_keywords,
        list
    ):
        keywords.extend(
            publication_keywords
        )

    workcloud_keywords = (
        profile_data.get(
            "workcloud_keywords",
            []
        )
    )

    if isinstance(
        workcloud_keywords,
        list
    ):
        keywords.extend(
            workcloud_keywords
        )

    return {
        "name": name,

        "academic_position": (
            position
        ),

        "research_interests": (
            extract_research_interests(
                bio
            )
        ),

        "areas_of_expertise": (
            clean_expertise(
                keywords
            )
        ),

        "orcid_url": (
            f"https://orcid.org/{orcid}"
            if orcid
            else None
        )
    }


def collect_unimelb():
    """
    Collect UniMelb Computing and
    Information Systems academics.

    Directory data is always preserved.
    Profile enrichment is optional.
    """

    print(
        "\nCollecting University of Melbourne..."
    )

    academics = []

    people = collect_directory_people()

    print(
        f"UniMelb directory people found: "
        f"{len(people)}"
    )

    # TEMPORARY TEST
    # Only process first 3 profiles for now
    people_to_process = people

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page()

        for index, person in enumerate(
            people_to_process,
            start=1
        ):
            print(
                f"\nUniMelb: processing "
                f"{index}/"
                f"{len(people_to_process)}"
            )

            academic = {
                "name": person["name"],
                "gender": None,

                "academic_position": (
                    person[
                        "academic_position"
                    ]
                ),

                "research_interests": [],

                "areas_of_expertise": [],

                "profile_url": (
                    person[
                        "profile_url"
                    ]
                ),

                "orcid_url": None,

                "university_name": (
                    UNIVERSITY_NAME
                )
            }

            enriched = extract_profile_data(
                page,
                person[
                    "profile_url"
                ]
            )

            if enriched:
                if enriched.get(
                    "name"
                ):
                    academic[
                        "name"
                    ] = enriched[
                        "name"
                    ]

                if enriched.get(
                    "academic_position"
                ):
                    academic[
                        "academic_position"
                    ] = enriched[
                        "academic_position"
                    ]

                academic[
                    "research_interests"
                ] = enriched.get(
                    "research_interests",
                    []
                )

                academic[
                    "areas_of_expertise"
                ] = enriched.get(
                    "areas_of_expertise",
                    []
                )

                academic[
                    "orcid_url"
                ] = enriched.get(
                    "orcid_url"
                )

            # Always keep directory data,
            # even if enrichment fails.
            academics.append(
                academic
            )

            time.sleep(
                REQUEST_DELAY
            )

        browser.close()

    print(
        f"\nUniMelb collected: "
        f"{len(academics)}"
    )

    return academics


if __name__ == "__main__":
    results = collect_unimelb()

    print(
        "\nSAMPLE RESULTS"
    )
    print(
        "=" * 80
    )

    for result in results:
        print(result)