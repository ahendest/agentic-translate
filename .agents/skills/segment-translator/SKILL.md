---
name: segment-translator
description: Translate one assigned unit of a book into its target file, apply approved terms and collect missing ones.
---

# Translate the assigned unit

You are a fresh agent started by the coordinator. Follow the Voice and Terminology sections
of AGENTS.md and the language's SOUL.md when present. Translate only the assigned unit and write only
its target file, `<translation>/<unit id>.<target language>.md` with the unit's headings and
lines in the same order; do not start agents.

1. Read the unit:

   ```bash
   python3 -B tools/translation.py read --project PROJECT_JSON --unit UNIT_ID
   ```

   Retrieve the exact approved wording of every returned known term before drafting with
   `term-request` (step 2) for its original form.
2. Check terms that need special treatment:

   ```bash
   python3 -B tools/translation.py term-request --project PROJECT_JSON --term "TERM" --at "SOURCE_SEGMENT.md:LINE"
   ```

   Write TERM without the attached prefixes that `word_prefixes` in `knowledge/config.json`
   lists for the source language. Apply each matching approved record: its reading form, translation and footnote. A
   record's note guides context-dependent terms; choose by sense and do not force one
   rendering. `candidates` are approved terms whose original is only a word prefix of the
   request or a part of a compound request: apply one only when the paragraph shows a derived or inflected word of that
   concept; otherwise treat the term as missing. For a missing term, keep
   `{{TERM:source form}}` as a placeholder and collect the returned request text
   `term (source-segment.md:line)`. The validator rejects any `{{TERM:`
   placeholder inside the requested scope.
3. Understand the full unit, translate it and compare each target paragraph against its
   source. For recurring titles, formulas and names, search the earlier translated segments
   and reuse their rendering.
4. When completing a waiting segment, replace each placeholder with the approved term and
   its equivalent. If no earlier unit holds the note (`grep -l "^\[\^TERM_ID\]:" TRANSLATION_DIR/*.md`),
   its first occurrence in this unit is the first use.
5. Report only the target file, the missing term requests and unresolved passages.
