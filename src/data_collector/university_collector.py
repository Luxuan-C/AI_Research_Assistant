import json
import os
import re
import time
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


# =================================================== #
#                     SETTINGS                        #
# =================================================== #

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "data")

OUTPUT_FILE = "university_academics.json"

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


# =================================================== #
#               UNIVERSITY DIRECTORIES                #
# =================================================== #

UNIVERSITIES = [

    {
        "name": "University of Sydney",
        "directory_url": "https://profiles.sydney.edu.au/",
        "allowed_domains": [
            "profiles.sydney.edu.au"
        ],
        "profile_patterns": [
            "profiles.sydney.edu.au/"
        ]
    },

    {
        "name": "UNSW Sydney",
        "directory_url": (
            "https://www.unsw.edu.au/engineering/"
            "our-schools/computer-science-and-engineering/about-us"
        ),
        "allowed_domains": [
            "www.unsw.edu.au"
        ],
        "profile_patterns": [
            "/staff/"
        ]
    },

    {
        "name": "University of Technology Sydney",
        "directory_url": "https://profiles.uts.edu.au/",
        "allowed_domains": [
            "profiles.uts.edu.au"
        ],
        "profile_patterns": [
            "profiles.uts.edu.au/"
        ]
    },

    {
        "name": "University of Melbourne",
        "directory_url": (
            "https://findanexpert.unimelb.edu.au/profile/"
        ),
        "allowed_domains": [
            "findanexpert.unimelb.edu.au"
        ],
        "profile_patterns": [
            "/profile/"
        ]
    },

    {
        "name": "Macquarie University",
        "directory_url": (
            "https://researchers.mq.edu.au/en/"
            "organisations/school-of-computing/persons/"
        ),
        "allowed_domains": [
            "researchers.mq.edu.au"
        ],
        "profile_patterns": [
            "/en/persons/"
        ]
    },

    {
        "name": "Monash University",
        "directory_url": (
            "https://research.monash.edu/en/"
            "organisations/faculty-of-information-technology/persons/"
        ),
        "allowed_domains": [
            "research.monash.edu"
        ],
        "profile_patterns": [
            "/en/persons/"
        ]
    },

    {
        "name": "RMIT University",
        "directory_url": (
            "https://www.rmit.edu.au/about/"
            "schools-colleges/computing-technologies/people"
        ),
        "allowed_domains": [
            "www.rmit.edu.au"
        ],
        "profile_patterns": [
            "/profiles/"
        ]
    },

    {
        "name": "University of Queensland",
        "directory_url": (
            "https://eecs.uq.edu.au/about/our-people"
        ),
        "allowed_domains": [
            "eecs.uq.edu.au"
        ],
        "profile_patterns": [
            "/profile/"
        ]
    },

    {
        "name": "Australian National University",
        "directory_url": (
            "https://comp.anu.edu.au/people/"
        ),
        "allowed_domains": [
            "comp.anu.edu.au"
        ],
        "profile_patterns": [
            "/people/"
        ]
    }
]


# =================================================== #
#               ACADEMIC ROLE FILTERS                 #
# =================================================== #

ACADEMIC_KEYWORDS = [
    "professor",
    "associate professor",
    "assistant professor",
    "senior lecturer",
    "lecturer",
    "research fellow",
    "senior research fellow",
    "postdoctoral research fellow",
    "future fellow",
    "dean",
    "director"
]


EXCLUDED_KEYWORDS = [
    "phd student",
    "phd candidate",
    "hdr candidate",
    "student",
    "administrator",
    "administration",
    "project officer",
    "executive assistant",
    "school manager",
    "operations manager",
    "finance",
    "technical officer",
    "systems officer"
]


# =================================================== #
#                REQUEST FUNCTIONS                    #
# =================================================== #

def get_soup(url):
    """
    Downloads a webpage and returns a BeautifulSoup
    object.
    """

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def clean_text(element):
    """
    Returns cleaned text from a BeautifulSoup element.
    """

    if element is None:
        return None

    text = element.get_text(
        " ",
        strip=True
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =================================================== #
#                  URL FUNCTIONS                      #
# =================================================== #

def normalise_url(base_url, href):
    """
    Converts relative links into absolute URLs and
    removes fragments.
    """

    if not href:
        return None

    url = urljoin(
        base_url,
        href
    )

    url = url.split("#")[0]

    return url


def domain_allowed(url, allowed_domains):
    """
    Checks whether a URL belongs to an allowed
    university domain.
    """

    domain = urlparse(
        url
    ).netloc.lower()

    return any(
        allowed in domain
        for allowed in allowed_domains
    )


def matches_profile_pattern(
    url,
    profile_patterns
):
    """
    Checks whether a URL looks like an academic profile.
    """

    url_lower = url.lower()

    return any(
        pattern.lower() in url_lower
        for pattern in profile_patterns
    )


# =================================================== #
#              DISCOVER PROFILE URLS                  #
# =================================================== #

def discover_profile_urls(university):
    """
    Visits a university directory page and extracts
    likely academic profile URLs.
    """

    directory_url = university[
        "directory_url"
    ]

    print(
        f"\nDiscovering profiles for "
        f"{university['name']}"
    )

    print(
        f"Directory: {directory_url}"
    )


    try:

        soup = get_soup(
            directory_url
        )

    except requests.RequestException as error:

        print(
            f"Could not access directory: {error}"
        )

        return []


    profile_urls = set()


    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href"
        )

        url = normalise_url(
            directory_url,
            href
        )


        if not url:
            continue


        if not domain_allowed(
            url,
            university[
                "allowed_domains"
            ]
        ):
            continue


        if not matches_profile_pattern(
            url,
            university[
                "profile_patterns"
            ]
        ):
            continue


        # Avoid storing the directory page itself
        if (
            url.rstrip("/")
            == directory_url.rstrip("/")
        ):
            continue


        profile_urls.add(
            url
        )


    print(
        f"Found {len(profile_urls)} "
        f"possible profile URLs."
    )


    return sorted(
        profile_urls
    )


# =================================================== #
#                    NAME                             #
# =================================================== #

def extract_name(soup):
    """
    Extracts the academic's name.
    """

    heading = soup.find(
        "h1"
    )

    if heading:

        name = clean_text(
            heading
        )

        if name:

            name = re.sub(
                r"Profile\s*page",
                "",
                name,
                flags=re.IGNORECASE
            )

            return name.strip()


    # fallback to meta title

    title = soup.find(
        "title"
    )

    if title:

        text = clean_text(
            title
        )

        if text:

            parts = re.split(
                r"\||-|–",
                text
            )

            if parts:
                return parts[0].strip()


    return None


# =================================================== #
#                    ORCID                            #
# =================================================== #

def extract_orcid(soup):
    """
    Extracts ORCID and returns the full ORCID URL.
    """

    pattern = (
        r"\d{4}-\d{4}-\d{4}-[\dX]{4}"
    )


    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href",
            ""
        )

        if "orcid.org" in href.lower():

            match = re.search(
                pattern,
                href
            )

            if match:

                return (
                    "https://orcid.org/"
                    + match.group(0)
                )


    page_text = soup.get_text(
        " ",
        strip=True
    )

    match = re.search(
        pattern,
        page_text
    )


    if match:

        return (
            "https://orcid.org/"
            + match.group(0)
        )


    return None


# =================================================== #
#               ACADEMIC POSITION                     #
# =================================================== #

def extract_academic_position(soup):
    """
    Attempts to identify the person's academic role.
    """

    lines = list(
        soup.stripped_strings
    )


    for line in lines:

        cleaned = line.strip()


        if len(cleaned) > 150:
            continue


        lowered = cleaned.lower()


        for excluded in EXCLUDED_KEYWORDS:

            if excluded in lowered:
                break

        else:

            for keyword in ACADEMIC_KEYWORDS:

                if keyword in lowered:

                    return cleaned


    return None


# =================================================== #
#                SECTION EXTRACTION                   #
# =================================================== #

def extract_section(
    soup,
    section_names
):
    """
    Finds text beneath headings such as:
    Research Interests
    Expertise
    Research
    Fields of Research
    """

    section_names = [
        value.lower()
        for value in section_names
    ]


    headings = soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5"
        ]
    )


    for heading in headings:

        heading_text = clean_text(
            heading
        )


        if not heading_text:
            continue


        lowered = (
            heading_text.lower()
        )


        if not any(
            section in lowered
            for section in section_names
        ):
            continue


        collected = []


        current = (
            heading.find_next_sibling()
        )


        while current:

            if current.name in [
                "h1",
                "h2",
                "h3",
                "h4",
                "h5"
            ]:
                break


            text = clean_text(
                current
            )


            if text:
                collected.append(
                    text
                )


            current = (
                current.find_next_sibling()
            )


        if collected:

            return " ".join(
                collected
            )


    return None


def extract_list_section(
    soup,
    section_names
):
    """
    Extracts list items from a named section.
    """

    section_names = [
        value.lower()
        for value in section_names
    ]


    headings = soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5"
        ]
    )


    for heading in headings:

        heading_text = clean_text(
            heading
        )


        if not heading_text:
            continue


        lowered = (
            heading_text.lower()
        )


        if not any(
            section in lowered
            for section in section_names
        ):
            continue


        values = []


        current = (
            heading.find_next_sibling()
        )


        while current:

            if current.name in [
                "h1",
                "h2",
                "h3",
                "h4",
                "h5"
            ]:
                break


            for item in current.find_all(
                "li"
            ):

                value = clean_text(
                    item
                )


                if (
                    value
                    and value not in values
                ):

                    values.append(
                        value
                    )


            current = (
                current.find_next_sibling()
            )


        if values:
            return values


    return []


def text_to_list(text):
    """
    Converts extracted research/expertise text to
    a Python list.
    """

    if not text:
        return []


    values = re.split(
        r"[;\n•|]",
        text
    )


    result = []


    for value in values:

        cleaned = value.strip()


        if (
            cleaned
            and cleaned not in result
        ):

            result.append(
                cleaned
            )


    return result


# =================================================== #
#               PROFILE VALIDATION                    #
# =================================================== #

def is_likely_academic(profile):
    """
    Removes obvious students and professional staff.
    """

    position = (
        profile.get(
            "academic_position"
        )
        or ""
    ).lower()


    if not position:

        # Some university pages do not expose the
        # position clearly, so do not immediately
        # reject them.
        return True


    for excluded in EXCLUDED_KEYWORDS:

        if excluded in position:
            return False


    return True


# =================================================== #
#                 PROFILE TEMPLATE                    #
# =================================================== #

def create_profile(
    url,
    university
):
    """
    Output structure based on fields in the academic
    table that university websites can provide.
    """

    return {
        "name": None,
        "gender": None,
        "academic_position": None,
        "research_interests": [],
        "areas_of_expertise": [],
        "profile_url": url,
        "orcid_url": None,
        "university_name": university
    }


# =================================================== #
#                SCRAPE ONE PROFILE                   #
# =================================================== #

def scrape_profile(
    url,
    university
):
    """
    Scrapes one academic profile page.
    """

    soup = get_soup(
        url
    )


    profile = create_profile(
        url,
        university
    )


    profile["name"] = (
        extract_name(
            soup
        )
    )


    profile[
        "academic_position"
    ] = extract_academic_position(
        soup
    )


    profile[
        "orcid_url"
    ] = extract_orcid(
        soup
    )


    # Research interests

    research_titles = [
        "research interests",
        "research areas",
        "research",
        "research profile",
        "research activities"
    ]


    research_list = (
        extract_list_section(
            soup,
            research_titles
        )
    )


    if research_list:

        profile[
            "research_interests"
        ] = research_list

    else:

        research_text = (
            extract_section(
                soup,
                research_titles
            )
        )


        profile[
            "research_interests"
        ] = text_to_list(
            research_text
        )


    # Expertise

    expertise_titles = [
        "areas of expertise",
        "expertise",
        "fields of research",
        "research expertise",
        "disciplines"
    ]


    expertise_list = (
        extract_list_section(
            soup,
            expertise_titles
        )
    )


    if expertise_list:

        profile[
            "areas_of_expertise"
        ] = expertise_list

    else:

        expertise_text = (
            extract_section(
                soup,
                expertise_titles
            )
        )


        profile[
            "areas_of_expertise"
        ] = text_to_list(
            expertise_text
        )


    return profile


# =================================================== #
#          COLLECT ONE UNIVERSITY'S ACADEMICS         #
# =================================================== #

def collect_university(
    university
):
    """
    Discovers profile links and collects academics for
    one university.
    """

    profile_urls = (
        discover_profile_urls(
            university
        )
    )


    results = []


    total = len(
        profile_urls
    )


    for index, url in enumerate(
        profile_urls,
        start=1
    ):

        print(
            f"[{index}/{total}] "
            f"{url}"
        )


        try:

            profile = scrape_profile(
                url,
                university[
                    "name"
                ]
            )


            if not profile[
                "name"
            ]:

                print(
                    "  Skipped: "
                    "name could not be extracted"
                )

                continue


            if not is_likely_academic(
                profile
            ):

                print(
                    "  Skipped: "
                    "not academic staff"
                )

                continue


            results.append(
                profile
            )


            print(
                f"  Collected: "
                f"{profile['name']}"
            )


        except requests.HTTPError as error:

            print(
                f"  HTTP error: "
                f"{error}"
            )


        except requests.ConnectionError as error:

            print(
                f"  Connection error: "
                f"{error}"
            )


        except requests.Timeout:

            print(
                "  Request timed out"
            )


        except Exception as error:

            print(
                f"  Error: {error}"
            )


        time.sleep(
            REQUEST_DELAY
        )


    return results


# =================================================== #
#                   DUPLICATES                        #
# =================================================== #

def remove_duplicates(
    profiles
):
    """
    Removes duplicate profiles using ORCID first,
    otherwise profile URL.
    """

    unique = {}

    for profile in profiles:

        if profile[
            "orcid_url"
        ]:

            key = (
                "orcid:",
                profile[
                    "orcid_url"
                ]
            )

        else:

            key = (
                "url:",
                profile[
                    "profile_url"
                ]
            )


        unique[key] = (
            profile
        )


    return list(
        unique.values()
    )


# =================================================== #
#                  WRITE OUTPUT                       #
# =================================================== #

def write_json(
    filename,
    data
):
    """
    Saves JSON inside src/data_collector/data/.
    """

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )


    filepath = os.path.join(
        OUTPUT_DIR,
        filename
    )


    with open(
        filepath,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )


    print(
        f"\nSaved to: {filepath}"
    )


# =================================================== #
#                      MAIN                           #
# =================================================== #

if __name__ == "__main__":

    all_profiles = []


    print(
        "Starting university website collection..."
    )


    for university in UNIVERSITIES:

        print(
            "\n====================================="
        )

        print(
            university["name"]
        )

        print(
            "====================================="
        )


        try:

            university_profiles = (
                collect_university(
                    university
                )
            )


            all_profiles.extend(
                university_profiles
            )


        except Exception as error:

            print(
                f"Failed collecting "
                f"{university['name']}: "
                f"{error}"
            )


    # Remove duplicate profiles

    all_profiles = (
        remove_duplicates(
            all_profiles
        )
    )


    # Save final result

    write_json(
        OUTPUT_FILE,
        all_profiles
    )


    print(
        "\nCollection complete."
    )

    print(
        f"Total academics collected: "
        f"{len(all_profiles)}"
    )