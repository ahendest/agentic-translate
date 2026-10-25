# Book translation

For translation, follow the Voice section and the requested language's
`translations/<language>/SOUL.md` when it exists. Use only the requested project's context.
Maintenance requests do not start translation. Never add language-specific rules to tools or
to these instructions.

## Voice

This instruction tells you about only the nuance and style of writing not how to translate. Write as the author wrote. Keep the original
author's nuance, style of writing, register, rhythm, tone and voice.

## Workflow

Require source language, target language and an existing EPUB file:
`çeviri istegi, kaynak dil: tr, hedef dil: ro, kitabin directory'si: path/book.epub`
Ask for missing fields. The supplied EPUB is the only source of truth; use no other edition
unless the user names it. Derive the book ID from the filename. Without narrower scope,
proceed through the book in order, preserving accepted translation.

Run from this repository. Replace uppercase arguments with request values or returned IDs/paths.

The agent that receives the request coordinates. It runs the commands below, starts fresh
agents and keeps only their short reports; it does not read or translate book text itself.
Every fresh agent starts without inherited history, with this file and the paths it needs.

1. Prepare routes without loading book text:

   ```bash
   python3 -B tools/translation.py prepare --source "SOURCE_FILE" --source-language SOURCE_LANG --target-language TARGET_LANG --create
   ```

   Reuse existing preparation; external originals are imported unchanged. Resolve multiple
   matches with `--project PROJECT_JSON`. For `preparation_required`, start a preparation
   agent of your own model with the
   [prepare-translation-source skill](.agents/skills/prepare-translation-source/SKILL.md),
   the returned `preparation_command` and the project path, then rerun prepare. `available`
   confirms existence, not extraction quality.
2. List the units with cursor continuation:

   ```bash
   python3 -B tools/translation.py segments --project PROJECT_JSON --limit 10
   ```

   Translate in book order. Give each unit to a fresh segment translator of your own model,
   one unit at a time, so earlier renderings exist when the next unit starts. While a unit is
   translated, give the previous finished segment to a fresh reviewer of your own model with
   the [translation-reviewer skill](.agents/skills/translation-reviewer/SKILL.md) and the
   project, source and target locations; pass no translator reasoning or prior verdicts.
   Segments with term placeholders wait for their terms.
3. Collect the missing terms from the translators' reports and give the list to the user;
   the terminology area resolves it. When approved wording arrives, start a fresh segment
   translator for each waiting segment to complete it, then its reviewer.
4. Collect reviews; run the manifest's validator after final changes, with the unit range as
   scope (`--units 001-010`).
   Check coverage before terminology; fix target_integrity failures. Report scope, checks and
   unresolved passages/placements; do not finalize passages awaiting terminology or placement.

## Segment translation

This section is for the segment translator. Translate only the assigned unit and write only
its target file, `<translation>/<unit id>.<target language>.md` with the unit's headings and
lines in the same order; do not start agents.

1. Read the unit:

   ```bash
   python3 -B tools/translation.py read --project PROJECT_JSON --unit UNIT_ID
   ```

   Retrieve the exact approved wording of every returned known term before drafting.
2. Check terms that need special treatment:

   ```bash
   python3 -B tools/translation.py term-request --project PROJECT_JSON --term "TERM" --at "SOURCE_SEGMENT.md:LINE"
   ```

   Apply each matching approved record: its reading form, translation and footnote. A
   record's note guides context-dependent terms; choose by sense and do not force one
   rendering. For a missing term, keep `{{TERM:source form}}` as a placeholder and collect the
   request text `term (source-segment.md:line)`. The validator rejects any `{{TERM:`
   placeholder inside the requested scope.
3. Understand the full unit, translate it and compare each target paragraph against its
   source. For recurring titles, formulas and names, search the earlier translated segments
   and reuse their rendering.
4. When completing a waiting segment, replace each placeholder with the approved term and
   parenthetical, insert the exact footnote at the first conceptual occurrence in the book
   and record the placement.
5. Report only the target file, the missing term requests and unresolved passages.

## Terminology

Retain religious/technical terms whose distinct cultural meaning a direct expression would
lose: namaz cannot become generic prayer. Arabic origin alone requires no research;
saadet-i ebediye is directly translatable. Existing approvals remain binding.
Proposals, historical evidence and lexical matches do not approve wording.

Use the approved reading form and note of the record. Inflect the retained term and its
parenthetical as the sentence requires; do not keep the original form blindly. Repeat the
term with its parenthetical consistently; place the exact explanatory note only at the first
conceptual book occurrence. Verify earlier source, translation, headings and notes against stored
placements. Reserve first use in untranslated material; never move the note later. Without
earlier source, do not claim book-wide first use.

Derived words, plurals and spelling variants of an approved term (rahmâniye of Rahmân,
nüfûs-u emmâre of nefs-i emmâre) follow that term: translate them in harmony with its approved
equivalent, without a separate term request. If you keep such a word in its original form, it
is an occurrence of the term: give it the parenthetical, and the footnote when it comes first
in the book. The check reports a possible earlier occurrence for this decision.

For note insertion and placement updates, follow [knowledge operations](knowledge/overview.md#placements).
Only placements may change here; wording and approval belong to punctual-term-translation.

## Always do

- Preserve meaning, logic, negation, modality, referents, ambiguity, theology, imagery,
  tone, repetition and quantities in natural prose; add no explanation or certainty.
- Preserve accepted text, boundaries, format, names, headings and author notes. Copy
  quotations in the project's `verbatim_script` exactly as the source prints them; a source
  written in that script is translated. Do not restore excluded publisher material or
  editorial references.
- Check source readability/locators while translating. Resolve defects from visible source,
  references and context. Hold only unresolved passages; global blocking requires substantial
  unreadability or uncertain completeness.
- Use bounded retrieval for large technical output. Requested editions go under
  `output/<language>/`.

## Ask first

- Change source authority, edition or segmentation.
- Edit accepted text outside scope or settle material ambiguity unresolved by evidence.
- Build publications, commit, push or release, unless already requested.

## Never do

- Alter verbatim quotations, invent terminology/footnotes, collect term approval here or
  silently fall back when the shared store fails.
- Bulk-index book text, databases or agent reasoning into technical caches.
- Create copied glossaries, another database, routine reports, mandatory segment notes,
  hooks, dashboards, validation frameworks or extra quality agents.
- Hard-code a language, a model or a vendor in tools, schemas or instructions.

## Checks

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
python3 -B tools/knowledge.py --config knowledge/config.json terms list --language ro
```

Run affected book validators when their code/inputs change; do not build publications for maintenance.

A fresh clone has no store. Rebuild it from the tracked text before any other command; the
rebuild leaves `knowledge/knowledge.jsonl` unchanged:

```bash
python3 -B tools/knowledge.py --config knowledge/config.json init
python3 -B tools/knowledge.py --config knowledge/config.json import-terms --input knowledge/knowledge.jsonl
python3 -B tools/knowledge.py --config knowledge/config.json import-lugat --input knowledge/sources/db_lugat.sql
```
