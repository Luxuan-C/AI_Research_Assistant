import time
import requests


API_URL = (
    "https://profiles.uts.edu.au/"
    "api/users/membersOfGroup"
)

PROFILE_BASE_URL = (
    "https://profiles.uts.edu.au/"
)

GROUP_ID = 162

PER_PAGE = 25
REQUEST_DELAY = 1
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
    Builds the UTS School of Computer Science API request.
    """

    return {
        "groupId": GROUP_ID,

        "pagination": {
            "perPage": PER_PAGE,
            "startFrom": start_from
        },

        "sort": "lastNameAsc"
    }


def find_members(data):
    """
    Finds the member list in the UTS API response.
    """

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    possible_keys = [
        "members",
        "users",
        "results",
        "items",
        "profiles",
        "data"
    ]

    for key in possible_keys:

        value = data.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):

            members = find_members(
                value
            )

            if members:
                return members

    for value in data.values():

        if isinstance(value, dict):

            members = find_members(
                value
            )

            if members:
                return members

    return []


def get_value(person, possible_keys):
    """
    Retrieves the first available field.
    """

    for key in possible_keys:

        value = person.get(key)

        if value not in (
            None,
            "",
            []
        ):
            return value

    return None


def build_profile_url(person):
    """
    Attempts to obtain the person's UTS profile URL.
    """

    value = get_value(
        person,
        [
            "profileUrl",
            "profileURL",
            "url",
            "uri",
            "slug"
        ]
    )

    if not value:
        return None

    if value.startswith("http"):
        return value

    return (
        PROFILE_BASE_URL
        + value.lstrip("/")
    )


def normalise_member(person):
    """
    Converts a UTS API member into our common format.
    """

    if not isinstance(person, dict):
        return None

    name = get_value(
        person,
        [
            "displayName",
            "fullName",
            "name"
        ]
    )

    position = get_value(
        person,
        [
            "position",
            "jobTitle",
            "title",
            "academicPosition"
        ]
    )

    return {
        "name": name,
        "gender": None,
        "academic_position": position,
        "research_interests": [],
        "areas_of_expertise": [],
        "profile_url": build_profile_url(person),
        "orcid_url": None,
        "university_name": (
            "University of Technology Sydney"
        )
    }


def collect_uts():
    """
    Collects members of UTS School of Computer Science.
    """

    print("\nCollecting UTS...")

    academics = []

    start_from = 0

    while True:

        print(
            f"UTS: requesting results "
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
                f"UTS request failed: "
                f"{error}"
            )

            break

        try:

            data = response.json()

        except ValueError:

            print(
                "UTS returned invalid JSON."
            )

            break

        members = find_members(
            data
        )

        if not members:

            print(
                "UTS: no more results."
            )

            break

        for person in members:

            academic = normalise_member(
                person
            )

            if academic:
                academics.append(
                    academic
                )

        if len(members) < PER_PAGE:
            break

        start_from += PER_PAGE

        time.sleep(
            REQUEST_DELAY
        )

    print(
        f"UTS collected: "
        f"{len(academics)}"
    )

    return academics


if __name__ == "__main__":

    results = collect_uts()

    for result in results[:5]:
        print(result)