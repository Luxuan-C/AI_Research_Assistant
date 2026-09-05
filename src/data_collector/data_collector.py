import json
import os
import sys
import pandas as pd
import requests


UNI_COUNT = 1
RESULTS_PER_PAGE = 100
RESEARCH_PAPERS_PER_UNI = 100

OPENALEX_API = "y5MdFVQSKhClXHd0aoWGWP"


def retrieve_data(uni_code: str):
    """
    Retrieves data from the OpenAlex API.
    """
    COMPUTER_SCIENCE_ID = 17

    cursor = "*"
    url = "https://api.openalex.org/works"
    params = {
        "api_key": OPENALEX_API,
        "filter": f"institutions.id:{uni_code}&primary_topic.field.id:{COMPUTER_SCIENCE_ID}",
        "per-page": RESULTS_PER_PAGE,
        "cursor": cursor,
    }

    data = []

    i = 0
    while i < RESEARCH_PAPERS_PER_UNI / RESULTS_PER_PAGE and cursor is not None:
        response = requests.get(url, params=params)
        response.raise_for_status()
        json_res = response.json()

        data += json_res["results"]
        cursor = json_res["meta"]["next_cursor"]

        i += 1

    return data

def extract_required_data(data):
    """
    Extracts all data which is required for the database.
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


    # iterate through each research paper
    for item in data:
        rp_unis = []
        rp_academics = []
        rp_journal = None

        research_paper_id = len(research_papers)

        # =============================== #
        #           UNIVERSITY            #
        # =============================== #
        for author in item.get("authorships", []):
            for institution in author.get("institutions"):
                name = institution["display_name"]

                # already encountered university
                if name in universities:
                    rp_unis.append(universities[name]["id"])
                    continue

                # encountering new university
                rp_unis.append(len(universities))
                universities[name] = {
                    "id": len(universities),
                    "name": institution["display_name"],
                    "country_code": institution["country_code"],
                    "ror_url": institution["ror"],
                    "type": institution["type"]
                }


        # =================================================== #
        #            FACULTY / DISCIPLINE / FIELD             #
        # =================================================== #
        topic = item.get("primary_topic") or {}
        
        domain = topic.get("domain") or {}
        field = topic.get("field") or {}
        subfield = topic.get("subfield") or {}

        faculty_name = domain.get("display_name")
        discipline_name = field.get("display_name")
        field_name = subfield.get("display_name")

        faculty_id = len(faculties)
        discipline_id = len(disciplines)
        field_id = len(fields)

        # FACULTY
        if faculty_name not in faculties:
            faculties[faculty_name] = {
                "id": faculty_id,
                "name": faculty_name
            }

        # DISCIPLINE
        if discipline_name not in disciplines:
            disciplines[discipline_name] = {
                "id": discipline_id,
                "name": discipline_name,
                "faculty_id": faculty_id
            }

        # FIELD
        if field_name not in fields:
            fields[field_name] = {
                "id": field_id,
                "name": field_name,
                "discipline_id": discipline_id
            }


        # =============================== #
        #            PUBLISHER            #
        # =============================== #
        # TODO:


        # =============================== #
        #             JOURNAL             #
        # =============================== #
        source = item.get("primary_location").get("source")
        if source and source["issn_l"]:
            rp_journal = len(journals)

            journals[source["issn_l"]] = {
                "id": len(journals),
                "name": source["display_name"],
                "type": source["type"],
                "issn": source["issn_l"],
                "publisher_id": -1
            }


        # =============================== #
        #            ACADEMIC             #
        # =============================== #
        for author in item["authorships"]:
            author_data = author["author"]
            author_key = author_data["orcid"] or author_data["display_name"]
            discipline_id = disciplines[discipline_name]["id"]
            field_id = fields[field_name]["id"]

            uni_ids = [universities[institution["display_name"]]["id"] for institution in author["institutions"]]

            if author_key not in academics:
                academic_id = len(academics)

                academics[author_key] = {
                    "id": academic_id,
                    "name": author_data["display_name"],
                    "gender": None,
                    "academic_position": None,
                    "profile_url": None,
                    "orcid_url": author_data["orcid"],
                    "research_paper_ids": [research_paper_id],
                    "university_ids": uni_ids,
                    "discipline_ids": [discipline_id],
                    "field_ids": [field_id]
                }

                rp_academics.append(academic_id)

            else:
                academic = academics[author_key]

                rp_academics.append(academic["id"])
                academic["research_paper_ids"].append(research_paper_id)
                academic["discipline_ids"].append(discipline_id)
                academic["field_ids"].append(field_id)
                academic["university_ids"] = list(set(uni_ids + academic["university_ids"]))


        # =============================== #
        #         RESEARCH PAPER          #
        # =============================== #
        keywords = [keyword["display_name"] for keyword in item["keywords"]]
        bibliography = item["biblio"]

        research_papers[research_paper_id] = {
            "id": research_paper_id,
            "name": item["title"],
            "publication_date": item["publication_date"],
            "volume": bibliography["volume"],
            "issue": bibliography["issue"],
            "page_numbers": f"{bibliography["first_page"]}-{bibliography["last_page"]}",
            "doi": item["ids"].get("doi"),
            "is_open_access": item["open_access"]["is_oa"],
            "open_access_url": item["open_access"]["oa_url"],
            "primary_url": item["primary_location"]["pdf_url"],
            "publication_type": item["primary_location"]["raw_type"],
            "incoming_citation_count": item["cited_by_count"],
            "keywords": keywords,
            "outgoing_citations": None,
            "publisher_id": -1,
            "journal_id": rp_journal,
            "university_ids": rp_unis,
            "faculty_ids": [faculties[item["primary_topic"]["domain"]["display_name"]]["id"]],
            "academics_ids": rp_academics
        }
            

        # =============================== #
        #              SCORE              #
        # =============================== #
        score_id = len(scores)
        scores[score_id] = {
            "id": score_id,
            "research_paper_id": research_paper_id,
            "academics_ids": rp_academics,
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

def write_json(file_prefix: str, data) -> None:
    with open(f"./data/{file_prefix}.json", "w") as f:
        json.dump(data, f, indent=2)

def read_json(file_prefix: str):
    with open(f"{file_prefix}.json", "r") as f:
        return json.load(f)

def write_csv(file_prefix: str, data) -> None:
    df = pd.DataFrame(data)
    df.to_csv(f"./data/{file_prefix}.csv", index=False)


if __name__ == "__main__":
    CREATE_CSV = False
    if len(sys.argv) > 1 and sys.argv[1] == "--csv":
        CREATE_CSV = True

    aus_unis = read_json("aus_unis")
    if not os.path.isdir("./data/"): os.mkdir("./data/")

    data = []

    # retrieve data from each uni
    for i, uni in enumerate(aus_unis):
        if i >= UNI_COUNT:
            break

        uni_name = uni["name"].replace(" ", "_").lower()
        uni_code = uni["id"]

        data += retrieve_data(uni_code)

    # extract all required information
    data_by_table = extract_required_data(data)

    # write table information to json
    for table_name, table_data in data_by_table.items():
        json_data = list(table_data.values())
        write_json(table_name, json_data)

        # create .csv files
        if CREATE_CSV:
            write_csv(table_name, json_data)


