# Shared knowledge

The manifest's knowledge route selects knowledge/config.json and the single
knowledge/knowledge.sqlite. The store does two jobs: dictionary search and approved
terminology. Routine translation follows [AGENTS.md](../AGENTS.md); use this reference for
auditing and rebuild.

## Tables

Schema 7. Each table has one writer.

| Table | Content | Writer |
| --- | --- | --- |
| `lugat`, `lugat_fts` | Source dictionary and its search index | Import only, from `sources/db_lugat.sql` |
| `terms` | One approved term: `language`, `source_form` (as in the source), `reading_form` (as printed in the book), `translation` (the parenthetical), `arabic`, `footnote`, `sense`, optional `note`, `approval`, `approved_at` | punctual-term-translation, after human approval |

Term IDs are `term-<language>-<slug>` and are also the footnote IDs in book text. A source
form without Latin letters or digits gets `u` and a hash of its folded form as slug. Queries
are scoped by the project's target language: one language never sees another's wording.
`note` guides translators for context-dependent terms; it does not force one rendering.

`knowledge/config.json` lists the accepted source languages in `source_languages`; `prepare`
refuses a book of another source language.

Inflections are not stored. Tools recognize a term by its words in any inflection: the source
by `source_form`, the book by `reading_form`. Matching ignores case, diacritics, vowel signs
(nonspacing marks such as Arabic harakat) and the apostrophe form (’ or '). `terms find` marks a
word-prefix hit as `inflection` and an approved term inside a compound request as
`contained`; both are candidates for a context decision, not an approval of the requested word.

Every term write rewrites `knowledge/knowledge.jsonl`, one approved term per line. It is the
tracked text copy; the SQLite file is not tracked. `knowledge/sources/legacy-records.json`
preserves the user-supplied terminology files that the first ten approvals came from.

## First-use notes

A term's note lives in the translation, not in the store: the first retained occurrence of
the term in book order carries the native footnote `[^TERM_ID]`, defined with the exact approved
footnote in the same unit. Preserve author note IDs, bodies and numbering without collisions.
Exclude generated contents and verbatim quotations from replacement. The book validator checks
the note's place and wording.

## Audit

Open the store read-only; never edit it by hand, because direct edits skip validation and
the text export. Changes to approved terminology are visible in Git history:

```bash
git log -p knowledge/knowledge.jsonl
sqlite3 -readonly knowledge/knowledge.sqlite
```

```sql
.mode box
SELECT id, reading_form, translation, arabic, footnote FROM terms WHERE language = 'LANG';
SELECT id, sense FROM terms WHERE sense LIKE '%WORD%';
```

## Retrieve records

Run from the repository root; replace uppercase arguments. Lists and searches are paginated
with `--limit 1–20` and `--cursor`.

```bash
python3 -B tools/knowledge.py --config knowledge/config.json integrity
python3 -B tools/knowledge.py --config knowledge/config.json terms list --language LANG
python3 -B tools/knowledge.py --config knowledge/config.json terms find --query "TEXT" --language LANG
python3 -B tools/knowledge.py --config knowledge/config.json terms get --id TERM_ID
python3 -B tools/knowledge.py --config knowledge/config.json scan --project PROJECT_JSON --units 001-010
python3 -B tools/knowledge.py --config knowledge/config.json lugat search --query "TEXT"
python3 -B tools/knowledge.py --config knowledge/config.json lugat get --id LUGAT_ID
```

`scan` lists the approved terms in a book's source units; without `--units` it covers the whole
book. `lugat get` names the entries that the entry's "Bak:" references point to. Dictionary
entries explain source meaning; they do not approve target wording.

## Rebuild

A fresh clone rebuilds the store from text. The rebuild leaves `knowledge.jsonl` unchanged.

```bash
python3 -B tools/knowledge.py --config knowledge/config.json init
python3 -B tools/knowledge.py --config knowledge/config.json import-terms --input knowledge/knowledge.jsonl
python3 -B tools/knowledge.py --config knowledge/config.json import-lugat --input knowledge/sources/db_lugat.sql
```

Import requires an empty terms table and grants no new approval. `export-terms --output PATH`
writes the same text copy to another location. A damaged store, or a store of another schema
version, is replaced by moving it out of `knowledge/` and running the rebuild; no binary backup
is needed.
