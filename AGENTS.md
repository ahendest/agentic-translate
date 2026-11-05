# Book translation

The agent that receives a translation request follows the
[translation-coordinator skill](.agents/skills/translation-coordinator/SKILL.md); a fresh agent
follows the skill it is given. Use only the requested project's context. Maintenance requests
do not start translation.

## Voice

Write as the author wrote: keep the author's nuance, register, rhythm, tone and voice. This
section governs style only, not terminology.

## Terminology

Request a religious or technical concept that has no approved record unless an ordinary
target-language word carries its full meaning in the paragraph: the name of a ritual act of
worship is not a generic word, but common words of thought or knowledge translate directly.
Arabic origin alone does not make a word a term. The user decides requested terms in the
terminology area. Existing approvals remain binding. Proposals, historical evidence and
lexical matches do not approve wording. Name God as Allah, not with the target language's
generic word for God.

Use the approved reading form and note of the record. Inflect the retained term and its
equivalent as the sentence requires; do not keep the original form blindly. At the first use
in the book write `term (equivalent)[^TERM_ID]` and define the exact note in the same unit; at
every later use place the equivalent directly after the term, as an apposition (`term
equivalent`). The translation is made in book order, so the earlier translated units show
whether the note already exists.

A record may lack parts by the user's decision; apply it as stored:

- no footnote: write every use like a later use;
- no translation: keep the original alone, with `[^TERM_ID]` at the first use when it has a footnote;
- no reading form: write the translation alone, by meaning;
- `later_use: original`: the first use reads `term (equivalent)`, later uses the term alone;
- only a note: translate by meaning as the note says.

Derived words, plurals and spelling variants of an approved term follow that term: translate
them in harmony with its approved equivalent, without a separate term request. If you keep
such a word in its original form, it is an occurrence of the term and is written in the same
way.

## Always do

- Preserve meaning, logic, negation, modality, referents, ambiguity, theology, imagery,
  tone, repetition and quantities in natural prose; add no explanation or certainty.
- Preserve accepted text, boundaries, format, names, headings and author notes. Copy
  quotations in the project's `verbatim_script` exactly as the source prints them; a source
  written in that script is translated. Do not restore excluded publisher material or
  editorial references.
- Write a book or treatise title kept in its original form in italics, `_Title_`; the
  validator reads it as a name, not as a term use.
- Check source readability/locators while translating. Resolve defects from visible source,
  references and context. Hold only unresolved passages; global blocking requires substantial
  unreadability or uncertain completeness.
- Use bounded retrieval for large technical output.
- Add a user's own decision about a term, such as "translate by meaning" or "keep the
  original", to its request line as `user: DECISION`.

## Ask first

- Change source authority, edition or segmentation.
- Edit accepted text outside scope or settle material ambiguity unresolved by evidence.
- Build publications, unless already requested.

## Never do

- Alter verbatim quotations, invent terminology/footnotes, collect term approval here or
  silently fall back when the shared store fails.
- Bulk-index book text, databases or agent reasoning into technical caches.
- Create routine reports, mandatory segment notes, hooks, dashboards, validation frameworks
  or extra quality agents.

## Checks

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
python3 -B tools/knowledge.py --config knowledge/config.json integrity
```

Run affected book validators when their code/inputs change; do not build publications for maintenance.
