---
name: prepare-translation-source
description: Prepare a book's EPUB source once with tools/prepare_epub.py, check the result against the EPUB, fix only evidenced defects and report. Reuse readable, correctly routed prepared sources.
---

# Prepare source

You are a fresh preparation agent started by the coordinator when tools/translation.py
prepare reports `preparation_required`. Prepare the source, then stop and report. Do not
translate, start agents or create review reports, workflow state or terminology.

## Run the tool

Run the `preparation_command` that prepare returned, from the repository root:

```bash
python3 -B tools/prepare_epub.py --epub "SOURCE_EPUB" --book BOOK_ID
```

It writes `sources/<book-id>/segments/NNN-<name>.md`, one unit per spine document in spine
order, split at headings when a document is long, and `sources/<book-id>/overview.md` with the
title, the unit list, the documents it did not convert and the defects it found. Each unit
starts with a level-2 heading naming its spine document; locators are `segment.md:line`.
Author notes follow their unit as Markdown footnotes, each body once at its call, also when
the EPUB keeps it in the same document. Text in every script is copied exactly.
A rerun on the same EPUB reproduces the same files; the tool refuses to overwrite a prepared
source that differs, because changing segmentation needs approval.

The supplied EPUB is the only source of truth. Use no other file, edition or web text unless
the user names it.

## Check

1. Read the overview. For each document listed as not converted, confirm in the EPUB that it
   is navigation, a cover or publisher material; report any that holds book text.
2. Compare a sample of units (beginning, middle, end, and every unit named under defects)
   with the matching EPUB documents: order, headings, paragraphs and author notes with their
   calls. Text in other scripts, such as Arabic, is copied exactly by the tool; do not check
   it by hand.
3. A long unit without headings stays one unit; never split unlocated text by length. List
   such units in the report.
4. Fix a unit only for a defect the EPUB itself proves, by editing that file with the
   smallest change. Record the fix in the overview under Defects. If meaning, negation,
   number, proper name, quotation or theology remains uncertain, hold that passage and report
   it.

## Project routes

prepare writes project.json. Add only real values: `verbatim_script` with the Unicode
script name (for example `Arabic`) when the source quotes another script and the translation
keeps those quotations as printed; omit it when the whole source is written in that script.
Omit progress, release, approval, history or segment status.

## Report

Return to the coordinator: project path, unit count, documents not converted, long units
without headings, fixes made and passages held.
