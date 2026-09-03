```mermaid
erDiagram

    discipline      |{--}| faculty : belongs_to
    field           |{--}| discipline : belongs_to
    journal         |{--|{ publisher : has
    research_paper  |{--|{ research_paper : references
    research_paper  |{--|{ publisher : published_by
    research_paper  |{--|{ journal : published_in
    research_paper  |{--|{ university : has
    research_paper  |{--|{ faculty : has
    research_paper  |{--|{ academic : has
    research_paper  ||--|| score : has_score
    academic        |{--|{ research_paper : contributed_to
    academic        |{--|{ university : works_for
    academic        |{--|{ discipline : works_for
    academic        |{--|{ field : works_for
    score           o{--|| academic : associated_with
    score           o{--|| publisher : associated_with
    score           o{--|| journal : associated_with

    university {
        uuid id PK
        varchar name
        varchar country_code
        varchar ror_url
        varchar type
    }

    faculty {
        uuid id PK
        varchar name
    }

    discipline {
        uuid id PK
        varchar name
        uuid faculty_id FK
    }

    field {
        uuid id PK
        varchar name
        uuid discipline_id FK
    }

    publisher {
        uuid id PK
        varchar name
    }

    journal {
        uuid id PK
        varchar name
        varchar type
        varchar issn
        uuid publisher_id FK
    }

    research_paper {
        uuid id PK
        varchar name
        datetime publication_date
        int volume
        int issue
        varchar page_numbers
        varchar doi
        bool is_open_access
        varchar open_access_url
        varchar primary_url
        varchar publication_type
        int incoming_citation_count
        varchar[] keywords
        uuid[] outgoing_citations FK
        uuid publisher_id FK
        uuid journal_id FK
        uuid[] university_ids FK
        uuid[] faculty_ids FK
        uuid[] academic_ids FK
    }

    academic {
        uuid id PK
        varchar name
        varchar gender
        varchar academic_position
        text[] research_interests
        text[] areas_of_expertise
        varchar profile_url
        varchar orcid_url
        uuid[] research_paper_ids FK
        uuid[] university_ids FK
        uuid[] discipline_ids FK            %% areas of expertise
        uuid[] field_ids FK                 %% research interests
    }

    score {
        uuid id PK
        float paper_authority_score
        float academic_authority_score
        float publisher_authority_score
        float journal_authenticity_score
        uuid research_paper_id FK
        uuid[] academic_ids FK
        uuid publisher_id FK
        uuid journal_id FK
    }


```
