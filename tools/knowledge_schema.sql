PRAGMA foreign_keys = ON;
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO meta VALUES ('schema_version','6');

-- Source dictionary. Read-only after import from knowledge/sources/db_lugat.sql.
CREATE TABLE lugat (id INTEGER PRIMARY KEY, indeks TEXT, kelime TEXT, kirpilmis TEXT, anlam TEXT, search_key TEXT NOT NULL);
CREATE INDEX lugat_search ON lugat(search_key);
CREATE VIRTUAL TABLE lugat_fts USING fts5(id UNINDEXED, body, tokenize='unicode61 remove_diacritics 2');

-- Approved terminology. Written only by punctual-term-translation after human approval.
-- The term ID is also the footnote ID in book text.
CREATE TABLE terms (
  id TEXT PRIMARY KEY,
  language TEXT NOT NULL,
  source_form TEXT NOT NULL,
  reading_form TEXT NOT NULL,
  translation TEXT NOT NULL,
  arabic TEXT,
  footnote TEXT NOT NULL,
  sense TEXT NOT NULL,
  note TEXT,
  approval TEXT NOT NULL,
  approved_at TEXT NOT NULL
);
CREATE INDEX terms_language ON terms(language);

-- First-use footnote of a term in one book: the source unit line and the translation line of the
-- footnote call. Written only by agentic-translate.
CREATE TABLE placements (
  term_id TEXT NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
  book_id TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_line INTEGER NOT NULL,
  source_quote TEXT,
  translation_path TEXT NOT NULL,
  translation_line INTEGER NOT NULL,
  first_expression TEXT,
  PRIMARY KEY (term_id, book_id)
);
