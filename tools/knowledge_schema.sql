CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO meta VALUES ('schema_version','9');

-- Source dictionary. Read-only after import from knowledge/sources/db_lugat.sql.
CREATE TABLE lugat (id INTEGER PRIMARY KEY, indeks TEXT, kelime TEXT, kirpilmis TEXT, anlam TEXT, search_key TEXT NOT NULL);
CREATE INDEX lugat_search ON lugat(search_key);
CREATE VIRTUAL TABLE lugat_fts USING fts5(id UNINDEXED, body, tokenize='unicode61 remove_diacritics 2');

-- Approved terminology. Written only by punctual-term-translation after human approval.
-- The term ID is also the footnote ID in book text. NULL reading_form: the original is not kept,
-- only the equivalent is written. NULL translation: the original is kept alone. NULL footnote:
-- no note. later_use: after the first use, 'equivalent' writes the term followed by its
-- equivalent, 'original' writes the term alone.
CREATE TABLE terms (
  id TEXT PRIMARY KEY,
  language TEXT NOT NULL,
  source_form TEXT NOT NULL,
  reading_form TEXT,
  translation TEXT,
  arabic TEXT,
  footnote TEXT,
  later_use TEXT NOT NULL DEFAULT 'equivalent' CHECK (later_use IN ('equivalent','original')),
  sense TEXT NOT NULL,
  note TEXT,
  approval TEXT NOT NULL,
  approved_at TEXT NOT NULL
);
CREATE INDEX terms_language ON terms(language);
