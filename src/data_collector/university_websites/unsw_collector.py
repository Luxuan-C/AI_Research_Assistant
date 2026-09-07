import time
import requests


API_URL = (
    "https://unsw-search.funnelback.squiz.cloud/"
    "s/search.html"
)

DIRECTORY_URL = (
    "https://www.unsw.edu.au/engineering/"
    "about-us/our-people"
)

REQUEST_DELAY = 1
RESULTS_PER_PAGE = 12
TIMEOUT = 20


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": DIRECTORY_URL,
    "Origin": "https://www.unsw.edu.au"
}


def build_params(start_rank):
    """
    Builds the UNSW Funnelback query for Computer Science
    and Engineering staff.
    """

    return {
        "form": "json",
        "collection": "unsw~unsw-search",
        "profile": "profiles",
        "query": "!padrenull",

        "start_rank": start_rank,
        "num_ranks": RESULTS_PER_PAGE,

        "sort": "metastaffLastName",

        "f.School|staffSchool": (
            "Computer Science and Engineering"
        ),

        "gscope1": "engineeringStaff",

        "meta_staffRole_not": (
            "casual adjunct visiting honorary"
        )
    }


def find_results(data):
    """
    Finds Funnelback result records.

    Funnelback responses normally contain result collections
    inside nested response/result structures, so this searches
    recursively for likely result lists.
    """

    if isinstance(data, list):

        # A result list should normally contain dictionaries.

        if (
            data
            and isinstance(data[0], dict)
        ):
            return data

        return []

    if not isinstance(data, dict):
        return []

    preferred_keys = [
        "results",
        "result",
        "documents"
    ]

    for key in preferred_keys:

        value = data.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):

            result = find_results(
                value
            )

            if result:
                return result

    for value in data.values():

        if isinstance(
            value,
            (dict, list)
        ):

            result = find_results(
                value
            )

            if result:
                return result

    return []


def get_value(record, possible_keys):
    """
    Retrieves the first available field.
    """

    for key in possible_keys:

        value = record.get(key)

        if value not in (
            None,
            "",
            []
        ):
            return value

    return None


def normalise_result(record):
    """
    Converts a UNSW Funnelback result into our common format.
    """

    if not isinstance(record, dict):
        return None

    name = get_value(
        record,
        [
            "title",
            "name",
            "displayName",
            "staffName"
        ]
    )

    profile_url = get_value(
        record,
        [
            "liveUrl",
            "url",
            "profileUrl",
            "clickTrackingUrl"
        ]
    )

    position = get_value(
        record,
        [
            "staffRole",
            "position",
            "jobTitle",
            "role"
        ]
    )

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


def collect_unsw():
    """
    Collects UNSW Computer Science and Engineering academics
    through the UNSW Funnelback search endpoint.
    """

    print("\nCollecting UNSW...")

    academics = []

    session = requests.Session()
    session.headers.update(HEADERS)

    # Visit the UNSW directory first so the session can receive
    # any cookies used by the website before calling Funnelback.
    try:
        session.get(
            DIRECTORY_URL,
            timeout=TIMEOUT
        )

    except requests.RequestException as error:
        print(
            f"UNSW directory session failed: "
            f"{error}"
        )

    start_rank = 1

    while True:

        print(
            f"UNSW: requesting from rank "
            f"{start_rank}"
        )

        params = build_params(
            start_rank
        )

        try:
            response = session.get(
                API_URL,
                params=params,
                timeout=TIMEOUT
            )

            response.raise_for_status()

        except requests.RequestException as error:
            print(
                f"UNSW request failed: "
                f"{error}"
            )

            break

        try:
            data = response.json()

        except ValueError:
            print(
                "UNSW returned invalid JSON."
            )
            break

        results = find_results(
            data
        )

        if not results:
            print(
                "UNSW: no more results."
            )
            break

        for record in results:

            academic = normalise_result(
                record
            )

            if academic:
                academics.append(
                    academic
                )

        if len(results) < RESULTS_PER_PAGE:
            break

        start_rank += RESULTS_PER_PAGE

        time.sleep(
            REQUEST_DELAY
        )

    print(
        f"UNSW collected: "
        f"{len(academics)}"
    )

    return academics


if __name__ == "__main__":

    results = collect_unsw()

    for result in results[:5]:
        print(result)