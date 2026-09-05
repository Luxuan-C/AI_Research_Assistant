-- View all universities
SELECT * 
FROM university
ORDER BY name;

-- View all academics
SELECT * 
FROM academic
ORDER BY name;

-- Search academics by keyword
SELECT *
FROM academic 
WHERE 
  name ILIKE '%smith%'
  OR EXISTS (
    SELECT 1
    FROM unnest(research_interests) AS interest
    WHERE interest ILIKE '%artificial intelligence%' 
  )
  OR EXISTS (
    SELECT 1
    FROM unnest(areas_of_expertise) AS expertise 
    WHERE expertise ILIKE '%artificial intelligence%'
  );

-- Find academics from a university
SELECT a.*
FROM academic a
JOIN university u 
  ON u.id = ANY(a.university_ids)
WHERE u.name ILIKE '%University of Sydney%';

-- Find academics in a discipline
SELECT a.*
FROM academic a 
JOIN discipline d 
  ON d.id = ANY(a.discipline_ids)
WHERE d.name ILIKE '%Computer Science%';

-- Find academics in a field 
SELECT a.*
FROM academic a 
JOIN field f 
  ON f.id = ANY(a.field_ids)
WHERE f.name ILIKE '%Artificial Intelligence';

-- Get all research papers 
SELECT *
FROM research_paper 
ORDER BY publication_date DESC;

-- Search research paper by title or keyword
SELECT *
FROM research_paper
WHERE 
 name ILIKE '%artificial intelligence%'
 OR EXISTS (
  SELECT 1
  FROM unnest(keywords) AS keyword
  WHERE keyword ILIKE '%machine learning%'
 );

 -- Find papers written by an academic 
 SELECT rp.*
 FROM research_paper rp 
 JOIN academic a 
  ON a.id = ANY(rp.academic_ids)
WHERE a.name ILIKE '%Jane Smith%';

-- Find academics who contributed to a paper 
SELECT a.*
FROM academic a 
JOIN research_paper rp 
  ON a.id = ANY(rp.academic_ids)
WHERE rp.name ILIKE '%Artificial Intelligence%';

-- Find papers from a university 
SELECT rp.*
FROM research_paper rp 
JOIN university u 
  ON u.id = ANY(rp.university_ids)
WHERE u.name ILIKE '%University of Sydney%';

-- Find papers from a faculty 
SELECT rp.*
FROM research_paper rp 
JOIN faculty f 
  ON f.id = ANY(rp.faculty_ids)
WHERE f.name ILIKE '%Engineering%';

-- Find papers published in a journal 
SELECT rp.*
FROM research_paper rp 
JOIN journal j 
  ON rp.journal_id = j.id 
WHERE j.name ILIKE '%Artificial Intelligence%';

-- Find papers from a publisher 
SELECT rp.*
FROM research_paper rp 
JOIN publisher p 
  ON rp.publisher_id = p.id 
WHERE p.name ILIKE '%John Smith%';

-- Show paper with journal + publisher 
SELECT 
  rp.name AS paper_name,
  rp.publication_date,
  rp.doi,
  j.name AS journal_name,
  p.name AS publisher_name
FROM research_paper rp 
LEFT JOIN journal j 
  ON rp.journal_id = j.id 
LEFT JOIN publisher p  
  ON rp.publisher_id = p.id 
ORDER BY rp.publication_date DESC;

-- Show academic with university 
SELECT 
  a.name AS academic_name,
  a.academic_position,
  u.name AS university_name
FROM academic a 
JOIN university u 
  ON u.id = ANY(a.university_ids)
ORDER BY a.name;

-- Show academic with discipline 
SELECT 
  a.name AS academic_name,
  d.name AS discipline_name
FROM academic a 
JOIN discipline d 
  ON d.id = ANY(a.discipline_ids)
ORDER BY a.name;

-- Most cited papers 
SELECT 
  name,
  publication_date,
  incoming_citation_count
FROM research_paper 
ORDER BY incoming_citation_count DESC;

-- Open access papers 
SELECT 
  name,
  publication_date,
  open_access_url 
FROM research_paper 
WHERE is_open_access = TRUE;

-- Search for a research topic
SELECT DISTINCT 
  a.id,
  a.name,
  a.academic_position,
  a.research_interests,
  a.areas_of_expertise,
  a.profile_url
FROM academic a 
WHERE 
  EXISTS (
    SELECT 1 
    FROM unnest(a.research_interests) AS interest 
    WHERE interest ILIKE '%artificial intelligence%'
  )
  OR EXISTS (
    SELECT 1
    FROM unnest(a.areas_of_expertise) AS expertise 
    WHERE expertise ILIKE '%artificial intelligence%'
  );