import json
import os

from university_websites.usyd_collector import collect_usyd
from university_websites.unsw_collector import collect_unsw
from university_websites.uts_collector import collect_uts
from university_websites.unimelb_collector import collect_unimelb
from university_websites.rmit_collector import collect_rmit
from university_websites.uq_collector import collect_uq
from university_websites.anu_collector import collect_anu

# We can add these again once they work reliably:
# from university_websites.macquarie_collector import collect_macquarie
# from university_websites.monash_collector import collect_monash


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

OUTPUT_DIR = os.path.join(
    BASE_DIR,
    "data"
)

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "university_academics.json"
)


def normalise_academic(academic):
    """
    Ensures every university collector produces
    the same academic structure.
    """

    return {
        "name": academic.get("name"),
        "gender": academic.get("gender"),
        "academic_position": academic.get(
            "academic_position"
        ),
        "research_interests": academic.get(
            "research_interests",
            []
        ) or [],
        "areas_of_expertise": academic.get(
            "areas_of_expertise",
            []
        ) or [],
        "profile_url": academic.get(
            "profile_url"
        ),
        "orcid_url": academic.get(
            "orcid_url"
        ),
        "university_name": academic.get(
            "university_name"
        )
    }


def deduplicate_academics(academics):
    """
    Removes duplicate academics.

    Primary key:
        profile URL

    Fallback:
        name + university
    """

    unique = {}

    for academic in academics:

        academic = normalise_academic(
            academic
        )

        profile_url = academic.get(
            "profile_url"
        )

        name = academic.get(
            "name"
        )

        university = academic.get(
            "university_name"
        )

        if profile_url:
            key = (
                "profile",
                profile_url.lower().strip()
            )

        elif name and university:
            key = (
                "name_university",
                name.lower().strip(),
                university.lower().strip()
            )

        else:
            # If we cannot identify the academic,
            # skip the record.
            continue

        if key not in unique:
            unique[key] = academic
            continue

        # Merge information if the duplicate
        # contains fields missing from the first copy.
        existing = unique[key]

        if (
            not existing["academic_position"]
            and academic["academic_position"]
        ):
            existing[
                "academic_position"
            ] = academic[
                "academic_position"
            ]

        if (
            not existing["orcid_url"]
            and academic["orcid_url"]
        ):
            existing[
                "orcid_url"
            ] = academic[
                "orcid_url"
            ]

        existing[
            "research_interests"
        ] = merge_lists(
            existing[
                "research_interests"
            ],
            academic[
                "research_interests"
            ]
        )

        existing[
            "areas_of_expertise"
        ] = merge_lists(
            existing[
                "areas_of_expertise"
            ],
            academic[
                "areas_of_expertise"
            ]
        )

    return list(
        unique.values()
    )


def merge_lists(first, second):
    """
    Combines two lists while removing
    case-insensitive duplicates.
    """

    combined = []

    for item in first + second:

        if not item:
            continue

        item = str(
            item
        ).strip()

        if not item:
            continue

        if any(
            item.lower()
            == existing.lower()
            for existing in combined
        ):
            continue

        combined.append(
            item
        )

    return combined


def run_collector(
    university_name,
    collector_function
):
    """
    Runs one university collector safely.

    If one university fails, the other
    collectors will still continue.
    """

    print(
        "\n"
        "========================================"
    )

    print(
        f"Starting {university_name}"
    )

    print(
        "========================================"
    )

    try:
        results = collector_function()

        if not results:
            print(
                f"{university_name}: "
                f"0 academics returned."
            )

            return []

        print(
            f"{university_name}: "
            f"{len(results)} academics returned."
        )

        return results

    except Exception as error:

        print(
            f"{university_name} collector failed:"
        )

        print(
            error
        )

        return []


def collect_all_universities():
    """
    Runs all available university website collectors.
    """

    all_academics = []

    collectors = [
        (
            "University of Sydney",
            collect_usyd
        ),
        (
            "UNSW Sydney",
            collect_unsw
        ),
        (
            "University of Technology Sydney",
            collect_uts
        ),
        (
            "University of Melbourne",
            collect_unimelb
        ),
        (
            "RMIT University",
            collect_rmit
        ),
        (
            "The University of Queensland",
            collect_uq
        ),
        (
            "Australian National University",
            collect_anu
        ),

        # Currently blocked / unfinished:
        #
        # (
        #     "Macquarie University",
        #     collect_macquarie
        # ),
        #
        # (
        #     "Monash University",
        #     collect_monash
        # ),
    ]

    university_counts = {}

    for (
        university_name,
        collector_function
    ) in collectors:

        results = run_collector(
            university_name,
            collector_function
        )

        university_counts[
            university_name
        ] = len(
            results
        )

        all_academics.extend(
            results
        )

    print(
        "\nDeduplicating academics..."
    )

    all_academics = (
        deduplicate_academics(
            all_academics
        )
    )

    print(
        f"Total unique academics: "
        f"{len(all_academics)}"
    )

    return (
        all_academics,
        university_counts
    )


def save_results(
    academics
):
    """
    Saves the combined university website
    collection to JSON.
    """

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            academics,
            file,
            indent=4,
            ensure_ascii=False
        )

    print(
        f"\nSaved results to:"
    )

    print(
        OUTPUT_FILE
    )


def print_summary(
    counts,
    total
):
    """
    Prints collection statistics.
    """

    print(
        "\n"
        "========================================"
    )

    print(
        "UNIVERSITY COLLECTION SUMMARY"
    )

    print(
        "========================================"
    )

    for (
        university,
        count
    ) in counts.items():

        print(
            f"{university}: {count}"
        )

    print(
        "----------------------------------------"
    )

    print(
        f"Total unique academics: {total}"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    academics, counts = (
        collect_all_universities()
    )

    save_results(
        academics
    )

    print_summary(
        counts,
        len(academics)
    )