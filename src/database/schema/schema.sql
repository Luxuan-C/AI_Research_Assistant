CREATE TABLE university (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  country_code VARCHAR,
  ror_url VARCHAR,
  type VARCHAR 
);

CREATE TABLE faculty (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL
);

CREATE TABLE discipline (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  faculty_id UUID REFERENCES faculty(id) 
);

CREATE TABLE field (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  discipline_id UUID REFERENCES discipline(id)
);

CREATE TABLE publisher (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL 
);

CREATE TABLE journal (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  type VARCHAR,
  issn VARCHAR,
  publisher_id UUID REFERENCES publisher(id) 
);

CREATE TABLE academic (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  gender VARCHAR,
  academic_position VARCHAR,
  research_interests TEXT[] DEFAULT '{}',
  areas_of_expertise TEXT[] DEFAULT '{}',
  profile_url VARCHAR,
  orcid_url VARCHAR,
  research_paper_ids UUID[] DEFAULT '{}',
  university_ids UUID[] DEFAULT '{}',
  discipline_ids UUID[] DEFAULT '{}',
  field_ids UUID[] DEFAULT '{}'
);

CREATE TABLE research_paper (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  publication_date DATE,
  volume INTEGER,
  issue INTEGER,
  page_numbers VARCHAR,
  doi VARCHAR,
  is_open_access BOOLEAN,
  open_access_url VARCHAR,
  primary_url VARCHAR,
  publication_type VARCHAR,
  incoming_citation_count INTEGER DEFAULT 0,
  keywords VARCHAR[] DEFAULT '{}',
  outgoing_citations UUID[] DEFAULT '{}',
  publisher_id UUID REFERENCES publisher(id),
  journal_id UUID REFERENCES journal(id),
  university_ids UUID[] DEFAULT '{}',
  faculty_ids UUID[] DEFAULT '{}',
  academic_ids UUID[] DEFAULT '{}'
);

CREATE TABLE score (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_authority_score FLOAT,
  academic_authority_score FLOAT,
  publisher_authority_score FLOAT,
  journal_authenticity_score FLOAT,
  research_paper_id UUID REFERENCES research_paper(id),
  academic_ids UUID[] DEFAULT '{}',
  publisher_id UUID REFERENCES publisher(id),
  journal_id UUID REFERENCES journal(id)
)