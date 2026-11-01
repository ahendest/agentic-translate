# Agentic translate

This is the book translation part of the Risale translation workshop. It translates Islamic
books from an EPUB file into another language. AI agents do the translation and review it; you
keep control of the religious and technical terms.

## What you supply

- **The book as an EPUB file.** It is the only source of the translation. If your book is a
  PDF or a scan, read [Sources that are not a clean EPUB](docs/source-options.md) first.
- **The source language and the target language**, as short codes. The book must be in
  Turkish (`tr`) or Arabic (`ar`). It can be translated into any language, for example `ro`
  (Romanian), `fr` (French) or `ur` (Urdu).

## How to start

Open an agent in this folder and send one line:

```text
çeviri istegi, kaynak dil: tr, hedef dil: ro, kitabin directory'si: path/to/book.epub
```

The agent prepares the book, divides it into units in book order and translates them one by
one. A second, independent agent reviews each finished unit. Quotations that the book keeps in
another script, for example Arabic verses, are copied exactly as printed.

## What you approve

Some words must not be flattened into a general word: *namaz* is not just "prayer". When the
translation meets such a term for the first time, it asks the terminology part of the workshop,
[punctual-term-translation](https://github.com/ahendest/punctual-term-translation). There you
read two proposals with their short notes and approve the exact wording. Approved wording is
reused in every book of that language. Units that wait for a term are finished after your
approval.

## Where the results appear

- `sources/<book>/overview.md`: what was prepared from the EPUB and anything to check.
- `translations/<language>/<book>/translation/`: the translated units.
- `knowledge/knowledge.jsonl`: every approved term, readable as text.

Books and translations stay on your computer; they are not part of this repository. Building a
printed edition from an EPUB-based translation is a later feature.

## More

- [AGENTS.md](AGENTS.md): the agents' instructions, commands and checks.
- [Knowledge overview](knowledge/overview.md): how approved terms are stored and rebuilt.
- [CHANGELOG.md](CHANGELOG.md) and [LICENSE](LICENSE) (MIT).
