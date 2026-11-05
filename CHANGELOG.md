# Changelog

## Unreleased

- CI pins `actions/checkout` v7.0.1 and `actions/setup-python` v7.1.0 by commit (Node.js 24),
  with a read-only token that the checkout does not keep.
- `word_prefixes` in `knowledge/config.json` lists, per source language, the prefixes attached
  to the front of a word. Term lookup, `scan` and `term-request` accept them, so a record of an
  Arabic word also finds the word with an attached article or particle.
- Each user's term store is their own and starts empty. `knowledge/knowledge.jsonl` is a local,
  untracked text copy and backup; `knowledge/sources/legacy-records.json` is no longer shipped.
- Store schema 11: `lugat` names each entry's `dictionary`. `import-lisan` imports the Lisan
  al-Arab text (Arabic, by root) that the workshop downloads; `lugat search` and `lugat get`
  return the dictionary name; `integrity` counts entries per dictionary. Search ignores tatweel.
- Store schema 10: every term records its `source_language`. Lookups, `scan` and the validator
  use only records of the book's source language, so an Arabic book no longer receives wording
  approved for Turkish books. `terms find` needs `--source-language`; `terms list` accepts it.
  The existing records are from Turkish books and carry `tr`. Rebuild an older store from
  `knowledge/knowledge.jsonl` (the workshop's `workshop.py` does this).
- Agent instructions carry no source- or target-language example words; only the
  terminology area writes terms.
- The tools write their output as UTF-8 and read the store schema as UTF-8 on every system;
  on Windows they failed on non-ASCII text in piped output. The checks run on Linux, Windows
  and macOS. Paths in tool output and project files use `/` on every system.
- The coordinator appends missing terms to `punctual-term-translation/results/requested-terms.md`.
- Segment translators request a concept only when no ordinary target-language word carries its
  full meaning in the paragraph; in doubt they request it.
- Store schema 9: `reading_form` and `translation` may be null and `later_use` records whether
  later uses repeat the equivalent or keep the original alone; a record may hold only a note.
  Term IDs are the plain term slug, without a prefix or language; the validator recognizes a
  term note by its ID in the store. Rebuild an older store from `knowledge/knowledge.jsonl`.

- Store schema 8: `footnote` may be null for a term approved without a note; every use of such
  a term reads `term equivalent`. Rebuild an older store from `knowledge/knowledge.jsonl`.
- Translators request every religious or technical concept without an approved record; later
  uses place the equivalent directly after the term. The validator collapses whitespace in
  verbatim runs and ignores waiting placeholders outside the scope and term IDs inside note calls. In the target text it keeps letter diacritics, and an inflected
  reading form of three letters or fewer counts only before its equivalent. A kept title is
  written `_Title_`; terms inside it are not term uses.
- Store schema 7 holds the dictionary and approved terms only. The `placements` table, the
  `place`, `check` and `migrate` commands and `first_expression` are removed; a store of another
  schema is rebuilt from `knowledge/knowledge.jsonl`, which no longer lists placements. `scan`
  takes `--project` and `--units`; `lugat get` follows "Bak:" references one step.
- A term's first-use note is read from the translation: in book order, the first retained
  occurrence carries `[^TERM_ID]`, defined once with the exact approved footnote in the same unit.
- `knowledge/config.json` lists the accepted source languages (`source_languages`: Arabic and
  Turkish); `prepare` refuses another. The target language is free.
- `term-request` reuses only an exact original; a prefix match or an approved term inside a
  compound is returned as `candidates` for a context decision. Matching ignores the apostrophe
  form and vowel signs (Arabic harakat).
- Only the first use carries the parenthetical: `Rahman (cel mai milostiv)[^term-ro-rahman]`,
  later `Rahman cel mai milostiv`. The validator rejects empty units, changed author notes, a
  first use without its parenthetical or note and a later use with a parenthetical. The success
  line names what was checked.
- The preparation agent and the reviewer no longer check Arabic quotations by hand; the
  validator's verbatim check covers them.
- `prepare` always creates or reuses `translations/<target>/<book>/project.json`; `--create`
  and `--project` are removed. Units list their line count only.
- EPUB preparation emits a same-document EPUB 3 note body once, at its call, and keeps the
  source list numbers (`<ol start>`, `<li value>`).

## 0.1.0 (2026-10-25)

First public release.

- The source of a book is its EPUB file. `tools/prepare_epub.py` turns it into located units,
  one per spine document in spine order, split at headings when long, with author notes and
  text in every script copied exactly. Reruns are byte-identical.
- Arabic is ordinary text. There is no Arabic index, placeholder or crop. A project may declare
  `verbatim_script`; the shared validator then checks that every quotation in that script is
  copied exactly.
- Locators are `segment.md:line`. The shared store is schema 6: placements record the source
  line and the translation line of the footnote call. Page and PDF routes are removed.
- One shared validator, `tools/validate_translation.py`, with unit scope (`--units 001-010`).
- Books are no longer tracked. The earlier PDF-based books moved out of the repository.
- MIT licence and CI.
