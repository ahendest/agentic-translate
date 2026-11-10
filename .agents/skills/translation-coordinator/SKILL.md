---
name: translation-coordinator
description: Coordinate a book translation. Prepare the source, give each unit to a fresh segment translator and the previous unit to a fresh reviewer, collect missing terms and validate.
---

# Coordinate the translation

Require the source language, the target language and an existing EPUB file; ask for missing
fields. The source language must be one of `source_languages` in
`knowledge/config.json`; the target language is free. The supplied EPUB is the only source of
truth; use no other edition unless the user names it. Derive the book ID from the filename.
Without narrower scope, proceed through the book in order, preserving accepted translation.

Run from agentic-translate. Replace uppercase arguments with request values or returned
IDs/paths. When the user gives a lasting style decision for the target language, add it as one
short line to `translations/TARGET_LANG/SOUL.md`.

The agent that receives the request coordinates. It runs the commands below, starts fresh
agents and keeps only their short reports; it does not read or translate book text itself.
Every fresh agent starts without inherited history, with AGENTS.md, its skill and the paths it needs.
When an agent is refused or stops before its report, start it once more with the same task
in a shorter prompt of one unit; only a second refusal goes to the user.

1. Prepare routes without loading book text:

   ```bash
   python3 -B tools/translation.py prepare --source "SOURCE_FILE" --source-language SOURCE_LANG --target-language TARGET_LANG
   ```

   It creates or reuses `translations/TARGET_LANG/BOOK_ID/project.json`; external originals
   are imported unchanged. For `preparation_required`, start a preparation
   agent of your own model with the
   [prepare-translation-source skill](../prepare-translation-source/SKILL.md),
   the returned `preparation_command` and the project path, then rerun prepare. `available`
   confirms existence, not extraction quality.
2. List the units with cursor continuation:

   ```bash
   python3 -B tools/translation.py segments --project PROJECT_JSON --limit 10
   ```

   Translate in book order. Give each unit to a fresh segment translator of your own model with the
   [segment-translator skill](../segment-translator/SKILL.md),
   one unit at a time, so earlier renderings exist when the next unit starts. While a unit is
   translated, give the previous finished segment to a fresh reviewer of your own model with
   the [translation-reviewer skill](../translation-reviewer/SKILL.md) and the
   project, source and target locations; pass no translator reasoning or prior verdicts.
   Segments with term placeholders wait for their terms.
3. Append the term requests from the translators' reports, one `term (source-segment.md:line)`
   per line, with its `translated: WORD` when reported, to
   `../punctual-term-translation/results/requested-terms.md`; the terminology
   area resolves it. When approved wording arrives, start a fresh segment
   translator for each waiting segment to complete it, then its reviewer; complete waiting
   segments and corrections in book order. When the approved
   wording differs from a translated word, give the units that hold the word to a fresh
   reviewer with that correction as scope.
4. Collect reviews; run the manifest's validator after final changes, with the unit range as
   scope (`--units 001-010`).
   Check coverage before terminology; fix target_integrity failures. The validator also rejects
   empty units, author notes whose calls or definitions differ from the source, a first use
   without `term (equivalent)[^TERM_ID]` and a later use with a parenthetical. In book order,
   the first retained occurrence of an approved term is the first use; the book defines its
   exact note once, in the same unit. Report scope, checks and unresolved passages; do not
   finalize passages awaiting terminology.
