# Changelog

## Unreleased

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
- The validator rejects empty units, changed author notes, a retained term without its
  parenthetical and a first use without its note. The success line names what was checked.
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
