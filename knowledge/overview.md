# Shared knowledge

The manifest's knowledge route selects knowledge/config.json; the manifest's source language
selects the store `knowledge/SOURCE_LANG.sqlite`, for example `knowledge/ar.sqlite`. Each
source language has its own store with two jobs: dictionary search in that language and the
terms approved for its books, in any target language. `dictionaries` in the config names the
dictionaries of each store. Routine translation follows [AGENTS.md](../AGENTS.md); use this
reference for auditing and rebuild.

## Tables

Schema 12. Each table has one writer. Each user's stores are their own: they start without terms.

| Table | Content | Writer |
| --- | --- | --- |
| `lugat`, `lugat_fts` | Source dictionaries and their search index; `dictionary` names each entry's dictionary | Import only: `lugat` (Ottoman Turkish) from `sources/db_lugat.sql`, `lisan-al-arab` from the Lisan al-Arab text that `workshop.py` downloads (headwords are Arabic roots) |
| `terms` | One approved term: `language` (target), `source_language`, `source_form` (as in the source), `reading_form` (as printed in the book; null: only the equivalent is written), `translation` (the equivalent; null: the original stays alone), `arabic`, `footnote` (null: no note), `sense`, optional `note`, `approval`, `approved_at` | punctual-term-translation, after human approval |

A term ID is the plain slug of the source form and is also the footnote ID in book text. A
source form without Latin letters or digits gets `u` and a hash of its folded form as slug. A book reads
only the store of its source language and only the records of its target language.
`note` guides translators for context-dependent terms; it does not force one rendering.

`knowledge/config.json` lists the accepted source languages in `source_languages`; `prepare`
refuses a book of another source language.

Inflections are not stored. Tools recognize a term by its words in any inflection: the source
by `source_form`, the book by `reading_form`. Matching ignores case, diacritics, vowel signs
(nonspacing marks such as Arabic harakat) and the apostrophe form (’ or '). In the source, the
first word may also carry one of the prefixes that `word_prefixes` in `knowledge/config.json`
lists for the source language, such as an attached article; a record therefore holds the form
without them. `terms find` marks a
word-prefix hit as `inflection` and an approved term inside a compound request as
`contained`; both are candidates for a context decision, not an approval of the requested word.

Every term write rewrites the store's text copy `knowledge/SOURCE_LANG.jsonl`, one approved term
per line: the user's local backup. Git tracks neither it nor the SQLite file.

## First-use notes

A term's note lives in the translation, not in the store: the first retained occurrence of
the term in book order reads `term (equivalent)[^TERM_ID]`, with the native footnote defined
by the exact approved footnote in the same unit; later uses are the term alone. A record may
lack a reading form, a translation or a footnote; each is a user
decision that [AGENTS.md](../AGENTS.md#terminology) applies. A footnote ID is a term note
when it names an approved term. Preserve author note IDs, bodies and numbering without collisions.
Exclude generated contents and verbatim quotations from replacement. The book validator checks
the note's place and wording.

## Audit

Open the store read-only; never edit it by hand, because direct edits skip validation and
the text export. Each record keeps the user's approval text and date.

```bash
sqlite3 -readonly knowledge/SOURCE_LANG.sqlite
```

```sql
.mode box
SELECT id, reading_form, translation, arabic, footnote FROM terms WHERE language = 'LANG';
SELECT id, sense FROM terms WHERE sense LIKE '%WORD%';
```

## Retrieve records

Run from the repository root; replace uppercase arguments. Every command names its store with
`--source-language`. Lists and searches are paginated with `--limit 1–20` and `--cursor`.

```bash
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG integrity
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG terms list --language LANG
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG terms find --query "TEXT" --language LANG
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG terms get --id TERM_ID
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG scan --project PROJECT_JSON --units 001-010
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG lugat search --query "TEXT"
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG lugat get --id LUGAT_ID
```

`scan` lists the approved terms in a book's source units; without `--units` it covers the whole
book. `lugat get` names the entries that the entry's "Bak:" references point to. Dictionary
entries explain source meaning; they do not approve target wording.

## Rebuild

The workshop's `workshop.py` builds a store for each source language: its terms from the local
text copy when it exists, otherwise none, and its dictionaries. By hand:

```bash
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG init
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG import-terms --input knowledge/SOURCE_LANG.jsonl
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG import-lugat --input knowledge/sources/db_lugat.sql
python3 -B tools/knowledge.py --config knowledge/config.json --source-language SOURCE_LANG import-lisan --input knowledge/sources/downloads/lisan-al-arab
```

Run `import-terms` only when the text copy exists, and only the imports of the store's
dictionaries. A store refuses terms of another source language.

Import requires an empty terms table and grants no new approval. `export-terms --output PATH`
writes the same text copy to another location. A damaged store, or a store of another schema
version, is replaced by moving it out of `knowledge/` and running the rebuild; no binary backup
is needed.
