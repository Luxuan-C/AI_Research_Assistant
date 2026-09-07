import time
import requests


API_URL = "https://profiles.sydney.edu.au/api/users"

PROFILE_BASE_URL = "https://profiles.sydney.edu.au/"

REQUEST_DELAY = 1
PER_PAGE = 25
TIMEOUT = 20


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Content-Type": "application/json"
}


def build_payload(start_from):
    """
    Creates the Sydney Profiles API request.

    Filters results to:
    - Faculty of Engineering
    - School of Computer Science
    """

    return {
        "params": {
            "by": "text",
            "category": "user"
        },

        "filters": [
            {
                "name": "customFilterOne",
                "matchDocsWithMissingValues": False,
                "useValuesToFilter": True,
                "values": [
                    "School of Computer Science"
                ]
            },
            {
                "name": "tags",
                "matchDocsWithMissingValues": True,
                "useValuesToFilter": False
            },
            {
                "name": "customFilterTwo",
                "matchDocsWithMissingValues": True,
                "useValuesToFilter": False
            },
            {
                "name": "customFilterThree",
                "matchDocsWithMissingValues": True,
                "useValuesToFilter": False
            },
            {
                "name": "department",
                "matchDocsWithMissingValues": False,
                "useValuesToFilter": True,
                "values": [
                    "Faculty of Engineering"
                ]
            },
            {
                "name": "customFilterFour",
                "matchDocsWithMissingValues": True,
                "useValuesToFilter": False
            }
        ],

        "pagination": {
            "startFrom": start_from,
            "perPage": PER_PAGE
        },

        "sort": "lastNameAsc"
    }


def find_result_list(data):
    """
    Returns the list of academic profiles from
    the University of Sydney API response.
    """

    if not isinstance(data, dict):
        return []

    resource = data.get("resource")

    if isinstance(resource, list):
        return resource

    return []

def get_value(person, possible_keys):
    """
    Returns the first non-empty value from a set of possible keys.
    """

    for key in possible_keys:

        value = person.get(key)

        if value not in (None, "", []):
            return value

    return None


def build_profile_url(person):
    """
    Builds the University of Sydney profile URL.
    """

    discovery_url_id = person.get("discoveryUrlId")

    if not discovery_url_id:
        return None

    return (
        "https://profiles.sydney.edu.au/"
        + discovery_url_id
    )


def normalise_person(person):
    """
    Converts a Sydney Profiles API result into
    our common academic format.
    """

    if not isinstance(person, dict):
        return None

    name = person.get("firstNameLastName")

    # Fallback if firstNameLastName is missing
    if not name:
        first_name = person.get("firstName", "")
        last_name = person.get("lastName", "")

        name = f"{first_name} {last_name}".strip()

    if not name:
        return None

    return {
        "name": name,
        "gender": None,
        "academic_position": person.get("title"),
        "research_interests": [],
        "areas_of_expertise": [],
        "profile_url": build_profile_url(person),
        "orcid_url": None,
        "university_name": "University of Sydney"
    }

def collect_usyd():
    """
    Collects University of Sydney School of Computer Science
    academics using the Sydney Profiles API.
    """

    print("\nCollecting University of Sydney...")

    academics = []

    start_from = 0

    while True:

        print(
            f"USyd: requesting results "
            f"{start_from + 1}-"
            f"{start_from + PER_PAGE}"
        )

        payload = build_payload(
            start_from
        )

        try:

            response = requests.post(
                API_URL,
                headers=HEADERS,
                json=payload,
                timeout=TIMEOUT
            )

            response.raise_for_status()

        except requests.RequestException as error:

            print(
                f"USyd request failed: {error}"
            )

            break

        try:

            data = response.json() 

        except ValueError:

            print(
                "USyd returned a response that "
                "was not valid JSON."
            )

            break

        people = find_result_list(
            data
        )
    
        if not people:

            print(
                "USyd: no more results."
            )

            break

        for person in people:

            academic = normalise_person(
                person
            )

            if academic:
                academics.append(
                    academic
                )

        # If fewer than 25 came back,
        # this should be the final page.

        if len(people) < PER_PAGE:
            break

        start_from += PER_PAGE

        time.sleep(
            REQUEST_DELAY
        )

    print(
        f"USyd collected: "
        f"{len(academics)}"
    )

    return academics


if __name__ == "__main__":

    results = collect_usyd()

    for result in results[:5]:
        print(result)