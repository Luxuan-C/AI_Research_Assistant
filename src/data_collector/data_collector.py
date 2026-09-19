import json
import os
import sys
import pandas as pd
import requests


TARGET_UNIVERSITY_IDS = {
    "I165779595",  # University of Melbourne
    "I129604602",  # University of Sydney
    "I31746571",   # UNSW Sydney
    "I114017466",  # University of Technology Sydney
    "I99043593",   # Macquarie University
    "I56590836",   # Monash University
    "I82951845",   # RMIT University
    "I165143802",  # University of Queensland
    "I118347636",  # Australian National University
}

RESULTS_PER_PAGE = 100
RESEARCH_PAPERS_PER_UNI = 100

# Keep your existing OpenAlex API key here.
OPENALEX_API = "y5MdFVQSKhClXHd0aoWGWP"


def retrieve_data(uni_code: str):
    """
    Retrieves research papers from the OpenAlex API.
    """

    COMPUTER_SCIENCE_ID = 17

    cursor = "*"
    url = "https://api.openalex.org/works"

    params = {
        "api_key": OPENALEX_API,
        "filter": (
            f"institutions.id:{uni_code}"
            f"&primary_topic.field.id:{COMPUTER_SCIENCE_ID}"
        ),
        "per-page": RESULTS_PER_PAGE,
        "cursor": cursor,
    }

    data = []

    while (
        len(data) < RESEARCH_PAPERS_PER_UNI
        and cursor is not None
    ):
        params["cursor"] = cursor

        response = requests.get(
            url,
            params=params
        )

        response.raise_for_status()

        json_res = response.json()

        data.extend(
            json_res["results"]
        )

        cursor = json_res["meta"]["next_cursor"]

    return data[:RESEARCH_PAPERS_PER_UNI]


def extract_required_data(data):
    """
    Extracts all data required for the database.
    """

    universities = {}
    faculties = {}
    disciplines = {}
    fields = {}
    publishers = {}
    journals = {}
    research_papers = {}
    academics = {}
    scores = {}

    # Iterate through each research paper.
    for item in data:

        rp_unis = []
        rp_academics = []
        rp_journal = None

        research_paper_id = len(research_papers)


        # ===================================================
        # UNIVERSITY
        # ===================================================

        for author in item.get("authorships", []):

            for institution in author.get(
                "institutions",
                []
            ):
                name = institution["display_name"]

                # Already encountered university.
                if name in universities:

                    rp_unis.append(
                        universities[name]["id"]
                    )

                    continue

                # Encountering new university.
                university_id = len(universities)

                universities[name] = {
                    "id": university_id,
                    "openalex_id": institution.get("id"),
                    "name": institution.get(
                        "display_name"
                    ),
                    "country_code": institution.get(
                        "country_code"
                    ),
                    "ror_url": institution.get("ror"),
                    "type": institution.get("type")
                }

                rp_unis.append(
                    university_id
                )


        # ===================================================
        # FACULTY / DISCIPLINE / FIELD
        # ===================================================

        topic = item.get("primary_topic") or {}

        domain = topic.get("domain") or {}
        field = topic.get("field") or {}
        subfield = topic.get("subfield") or {}

        faculty_name = domain.get(
            "display_name"
        )

        discipline_name = field.get(
            "display_name"
        )

        field_name = subfield.get(
            "display_name"
        )


        # FACULTY

        if faculty_name not in faculties:

            faculty_id = len(faculties)

            faculties[faculty_name] = {
                "id": faculty_id,
                "name": faculty_name
            }

        else:
            faculty_id = faculties[
                faculty_name
            ]["id"]


        # DISCIPLINE

        if discipline_name not in disciplines:

            discipline_id = len(disciplines)

            disciplines[discipline_name] = {
                "id": discipline_id,
                "name": discipline_name,
                "faculty_id": faculty_id
            }

        else:
            discipline_id = disciplines[
                discipline_name
            ]["id"]


        # FIELD

        if field_name not in fields:

            field_id = len(fields)

            fields[field_name] = {
                "id": field_id,
                "name": field_name,
                "discipline_id": discipline_id
            }

        else:
            field_id = fields[
                field_name
            ]["id"]


        # ===================================================
        # PUBLISHER
        # ===================================================

        # TODO


        # ===================================================
        # JOURNAL
        # ===================================================

        primary_location = (
            item.get("primary_location")
            or {}
        )

        source = primary_location.get(
            "source"
        )

        if source and source.get("issn_l"):

            journal_key = source["issn_l"]

            # Create a journal only the first time
            # this ISSN is encountered.
            if journal_key not in journals:

                journal_id = len(journals)

                journals[journal_key] = {
                    "id": journal_id,
                    "name": source.get(
                        "display_name"
                    ),
                    "type": source.get(
                        "type"
                    ),
                    "issn": journal_key,
                    "publisher_id": -1
                }

            # Reuse the same journal ID every time
            # this ISSN appears again.
            rp_journal = journals[
                journal_key
            ]["id"]


        # ===================================================
        # ACADEMIC
        # ===================================================

        for author in item.get(
            "authorships",
            []
        ):

            author_data = (
                author.get("author")
                or {}
            )

            author_key = (
                author_data.get("orcid")
                or author_data.get("display_name")
            )

            if not author_key:
                continue

            discipline_id = disciplines[
                discipline_name
            ]["id"]

            field_id = fields[
                field_name
            ]["id"]

            uni_ids = []

            for institution in author.get(
                "institutions",
                []
            ):

                institution_name = (
                    institution.get(
                        "display_name"
                    )
                )

                if institution_name in universities:

                    uni_ids.append(
                        universities[
                            institution_name
                        ]["id"]
                    )

            # Remove duplicate university IDs.
            uni_ids = list(
                dict.fromkeys(uni_ids)
            )


            if author_key not in academics:

                academic_id = len(academics)

                academics[author_key] = {
                    "id": academic_id,
                    "name": author_data.get(
                        "display_name"
                    ),
                    "gender": None,
                    "academic_position": None,
                    "profile_url": None,
                    "orcid_url": author_data.get(
                        "orcid"
                    ),
                    "research_paper_ids": [
                        research_paper_id
                    ],
                    "university_ids": uni_ids,
                    "discipline_ids": [
                        discipline_id
                    ],
                    "field_ids": [
                        field_id
                    ]
                }

                rp_academics.append(
                    academic_id
                )

            else:

                academic = academics[
                    author_key
                ]

                rp_academics.append(
                    academic["id"]
                )

                academic[
                    "research_paper_ids"
                ].append(
                    research_paper_id
                )

                academic[
                    "discipline_ids"
                ].append(
                    discipline_id
                )

                academic[
                    "field_ids"
                ].append(
                    field_id
                )

                academic[
                    "university_ids"
                ] = list(
                    dict.fromkeys(
                        academic[
                            "university_ids"
                        ] + uni_ids
                    )
                )


        # ===================================================
        # RESEARCH PAPER
        # ===================================================

        keywords = [
            keyword["display_name"]
            for keyword in item.get(
                "keywords",
                []
            )
            if keyword.get("display_name")
        ]

        bibliography = (
            item.get("biblio")
            or {}
        )

        open_access = (
            item.get("open_access")
            or {}
        )

        ids = (
            item.get("ids")
            or {}
        )

        first_page = bibliography.get(
            "first_page"
        )

        last_page = bibliography.get(
            "last_page"
        )

        if (
            first_page is not None
            and last_page is not None
        ):
            page_numbers = (
                f"{first_page}-{last_page}"
            )

        elif first_page is not None:
            page_numbers = str(first_page)

        else:
            page_numbers = None


        research_papers[
            research_paper_id
        ] = {

            "id": research_paper_id,

            "openalex_id": item.get("id"),

            "name": item.get("title"),

            "publication_date": item.get(
                "publication_date"
            ),

            "volume": bibliography.get(
                "volume"
            ),

            "issue": bibliography.get(
                "issue"
            ),

            "page_numbers": page_numbers,

            "doi": ids.get("doi"),

            "is_open_access": open_access.get(
                "is_oa"
            ),

            "open_access_url": open_access.get(
                "oa_url"
            ),

            "primary_url": primary_location.get(
                "pdf_url"
            ),

            "publication_type": (
                primary_location.get(
                    "raw_type"
                )
            ),

            "incoming_citation_count": (
                item.get(
                    "cited_by_count"
                )
            ),

            "keywords": keywords,

            "outgoing_citations": item.get(
                "referenced_works",
                []
            ),

            "publisher_id": -1,

            "journal_id": rp_journal,

            "university_ids": list(
                dict.fromkeys(
                    rp_unis
                )
            ),

            "faculty_ids": [
                faculty_id
            ],

            "academic_ids": list(
                dict.fromkeys(
                    rp_academics
                )
            )
        }


        # ===================================================
        # SCORE
        # ===================================================

        score_id = len(scores)

        scores[score_id] = {
            "id": score_id,
            "research_paper_id": (
                research_paper_id
            ),
            "academics_ids": list(
                dict.fromkeys(
                    rp_academics
                )
            ),
            "publisher_id": -1,
            "journal_id": rp_journal,
            "paper_authority_score": 0.99,
            "academic_authority_score": 0.99,
            "publisher_authority_score": 0.99,
            "journal_authenticity_score": 0.99,
        }


    return {
        "universities": universities,
        "faculties": faculties,
        "disciplines": disciplines,
        "fields": fields,
        "publishers": publishers,
        "journals": journals,
        "research_papers": research_papers,
        "academics": academics,
        "scores": scores,
    }


def write_json(
    file_prefix: str,
    data
) -> None:

    with open(
        f"./data/raw/{file_prefix}.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


def read_json(
    file_prefix: str
):

    with open(
        f"{file_prefix}.json",
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def write_csv(
    file_prefix: str,
    data
) -> None:

    df = pd.DataFrame(data)

    df.to_csv(
        f"./data/{file_prefix}.csv",
        index=False
    )


if __name__ == "__main__":

    CREATE_CSV = False

    if (
        len(sys.argv) > 1
        and sys.argv[1] == "--csv"
    ):
        CREATE_CSV = True


    aus_unis = read_json(
        "aus_unis"
    )


    if not os.path.isdir(
        "./data/raw/"
    ):
        os.makedirs(
            "./data/raw/",
            exist_ok=True
        )


    data = []

    seen_work_ids = set()


    for uni in aus_unis:

        if (
            uni["id"]
            not in TARGET_UNIVERSITY_IDS
        ):
            continue

        uni_code = uni["id"]

        print(
            f"Collecting papers for "
            f"{uni['name']}..."
        )

        university_papers = (
            retrieve_data(
                uni_code
            )
        )

        for paper in university_papers:

            work_id = paper["id"]

            if (
                work_id
                not in seen_work_ids
            ):

                seen_work_ids.add(
                    work_id
                )

                data.append(
                    paper
                )


    print(
        f"Total unique research papers "
        f"collected: {len(data)}"
    )


    # Extract all required information.
    data_by_table = (
        extract_required_data(
            data
        )
    )


    # Write table information to JSON.
    for (
        table_name,
        table_data
    ) in data_by_table.items():

        json_data = list(
            table_data.values()
        )

        write_json(
            table_name,
            json_data
        )

        # Create CSV files if requested.
        if CREATE_CSV:

            write_csv(
                table_name,
                json_data
            )