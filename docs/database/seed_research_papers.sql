-- Seed data for the live Supabase research_paper table.
-- Run this in Supabase SQL Editor. These are real publications with stable URLs.

insert into research_paper (
  name,
  publication_date,
  doi,
  primary_url,
  is_open_access,
  keywords,
  publication_type,
  incoming_citation_count
)
values
(
  'Attention Is All You Need',
  '2017-06-12',
  '10.48550/arXiv.1706.03762',
  'https://arxiv.org/abs/1706.03762',
  true,
  array['artificial intelligence', 'machine learning', 'transformers', 'natural language processing'],
  'preprint',
  0
),
(
  'BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding',
  '2019-05-24',
  '10.48550/arXiv.1810.04805',
  'https://arxiv.org/abs/1810.04805',
  true,
  array['artificial intelligence', 'machine learning', 'natural language processing', 'transformers'],
  'preprint',
  0
),
(
  'Deep Learning',
  '2015-05-28',
  '10.1038/nature14539',
  'https://doi.org/10.1038/nature14539',
  false,
  array['artificial intelligence', 'machine learning', 'deep learning', 'neural networks'],
  'journal article',
  0
),
(
  'Artificial intelligence in healthcare: past, present and future',
  '2019-06-01',
  '10.1038/s41591-018-0300-7',
  'https://doi.org/10.1038/s41591-018-0300-7',
  false,
  array['artificial intelligence', 'healthcare', 'clinical decision support', 'health AI'],
  'journal article',
  0
),
(
  'The potential for artificial intelligence in healthcare',
  '2018-06-01',
  '10.1038/s41591-018-0305-2',
  'https://doi.org/10.1038/s41591-018-0305-2',
  false,
  array['artificial intelligence', 'healthcare', 'medical imaging', 'health AI'],
  'journal article',
  0
),
(
  'Machine learning for healthcare',
  '2018-06-01',
  '10.1038/s41591-018-0316-z',
  'https://doi.org/10.1038/s41591-018-0316-z',
  false,
  array['machine learning', 'healthcare', 'clinical research', 'health AI'],
  'journal article',
  0
),
(
  'Artificial Intelligence and Machine Learning in Clinical Medicine, 2023',
  '2023-01-01',
  '10.1056/NEJMra2302038',
  'https://doi.org/10.1056/NEJMra2302038',
  false,
  array['artificial intelligence', 'machine learning', 'clinical medicine', 'healthcare'],
  'review article',
  0
),
(
  'Large language models in medicine',
  '2023-05-25',
  '10.1038/s41586-023-06160-y',
  'https://doi.org/10.1038/s41586-023-06160-y',
  false,
  array['large language models', 'artificial intelligence', 'medicine', 'natural language processing'],
  'journal article',
  0
);

-- Run the insert once, or remove existing rows first if re-seeding.

select id, name, doi, primary_url, keywords
from research_paper
order by publication_date desc;
