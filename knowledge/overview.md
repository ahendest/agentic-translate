# Shared knowledge

The manifest's knowledge route selects knowledge/config.json and the single
knowledge/knowledge.sqlite. The store does three jobs: dictionary search, approved
terminology and the first-use placement of each term in each book. Routine translation
follows [AGENTS.md](../AGENTS.md); use this reference for auditing, placements and rebuild.

## Tables

Schema 6. Each table has one writer.

| Table | Content | Writer |
| --- | --- | --- |
| `lugat`, `lugat_fts` | Source dictionary and its search index | Import only, from `sources/db_lugat.sql` |
| `terms` | One approved term: `language`, `source_form` (as in the source), `reading_form` (as printed in the book), `translation` (the parenthetical), `arabic`, `footnote`, `sense`, optional `note`, `approval`, `approved_at` | punctual-term-translation, after human approval |
| `placements` | Source unit and line with a quotation, translation file and line of the footnote call of a term's first use in one book | agentic-translate |

Term IDs are `term-<language>-<slug>` and are also the footnote IDs in book text. Queries
are scoped by the project's target language: one language never sees another's wording.
`note` guides translators for context-dependent terms; it does not force one rendering.

Inflections are not stored. Tools recognize a term by its words in any inflection: the source
by `source_form`, the book by `reading_form` (case and diacritics ignored). Such matches can
include derived words, so an earlier source match is reported as a warning to check.

Every term or placement write rewrites `knowledge/knowledge.jsonl`: one approved term per
line with its placements. It is the tracked text copy; the SQLite file is not
tracked. `knowledge/sources/legacy-records.json` preserves the user-supplied terminology
files that the first ten approvals came from.

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
SELECT term_id, book_id, source_path, source_line, translation_path, translation_line FROM placements;
```

## Retrieve records

Run from the repository root; replace uppercase arguments. Lists and searches are paginated
with `--limit 1–20` and `--cursor`.

```bash
python3 -B tools/knowledge.py --config knowledge/config.json integrity
python3 -B tools/knowledge.py --config knowledge/config.json terms list --language LANG
python3 -B tools/knowledge.py --config knowledge/config.json terms find --query "TEXT" --language LANG
python3 -B tools/knowledge.py --config knowledge/config.json terms get --id TERM_ID --book BOOK_ID
python3 -B tools/knowledge.py --config knowledge/config.json lugat search --query "TEXT"
python3 -B tools/knowledge.py --config knowledge/config.json lugat get --id LUGAT_ID
```

Dictionary entries explain source meaning; they do not approve target wording.

## Placements

Before inserting a first-use note, verify its source quotation, target locator and footnote
ID against the files. Use native footnotes whose ID is the term ID; preserve author note IDs,
bodies and numbering without collisions. Exclude generated contents and verbatim quotations
from replacement. For contextual notes, store the exact phrase before the note call in
`first_expression`. Lines are one-based: `source_line` is the line of the source unit that
holds the first use, `translation_line` the line of the translation file that holds the
footnote call.

Write one placement as JSON outside the repository, run the dry run, then save it:

```json
{"term_id": "TERM_ID", "book_id": "BOOK_ID", "source_path": "sources/BOOK_ID/segments/FILE.md",
 "source_line": 12, "source_quote": "exact source words", "translation_path": "translation/FILE.LANG.md",
 "translation_line": 12, "first_expression": null}
```

```bash
python3 -B tools/knowledge.py --config knowledge/config.json place --input PLACEMENT_JSON --dry-run
python3 -B tools/knowledge.py --config knowledge/config.json place --input PLACEMENT_JSON
python3 -B tools/knowledge.py --config knowledge/config.json check --case CASE_JSON
```

CASE_JSON identifies a repository-relative project and, optionally, a unit range by the
number that starts each unit filename; without `units` the check covers the whole book:

```json
{"project":"translations/LANG/BOOK_ID/project.json","units":"001-010"}
```

Placement never changes wording or approval; those belong to punctual-term-translation.
Run the affected book validator after placement or translation changes.

## Rebuild

A fresh clone rebuilds the store from text. The rebuild leaves `knowledge.jsonl` unchanged.

```bash
python3 -B tools/knowledge.py --config knowledge/config.json init
python3 -B tools/knowledge.py --config knowledge/config.json import-terms --input knowledge/knowledge.jsonl
python3 -B tools/knowledge.py --config knowledge/config.json import-lugat --input knowledge/sources/db_lugat.sql
```

Import requires an empty terms table and grants no new approval. `export-terms --output PATH`
writes the same text copy to another location. A damaged store is replaced by moving it out
of `knowledge/` and running the rebuild; no binary backup is needed.
