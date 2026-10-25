# Changelog

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
