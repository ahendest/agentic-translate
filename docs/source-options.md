# Sources that are not a clean EPUB

The workshop reads one kind of source: an EPUB file. This note is for people who have a book in
another form. It explains how to turn it into something the workshop can use. The agents do not
read this note, and nothing here changes how the workshop works.

## The easiest path: make an EPUB first

If you have a PDF or a word-processor file, convert it to EPUB outside the workshop, then start
a normal translation request with the EPUB. Free tools such as Calibre or Pandoc can do this.
After the conversion, open the EPUB and check that:

- the chapters are in the right order,
- headings are real headings (not just bold text), so long chapters can be divided,
- footnotes are linked to the place where they are called,
- quotations in other scripts (for example Arabic) are readable and complete.

Whatever the EPUB says is what will be translated, so fix problems in the EPUB, not later.

## A PDF with Arabic and Latin text

PDFs of Islamic books often mix Latin text with Arabic quotations. The text layer of such a PDF
is frequently damaged: Arabic letters come out in the wrong order, vowel marks are lost, or the
text is not there at all. Before you convert, choose one of these ways to get reliable Arabic:

1. **Repair the text layer.** Sometimes the PDF's font has a broken character map. A tool that
   decodes the font's character map can then recover the real letters. Try this before any
   reading by machine, because it gives the printed text itself.
2. **Use an Arabic-capable OCR model** (OCR: optical character recognition) on the whole page.
   "Nuqta 0.8B" is one candidate that was suggested for this kind of work. Check its output on
   a few pages against the printed book.
3. **Crop each Arabic passage** on your own computer and give the crops to a small model that
   can read images. Have two independent readings made for every passage and compare them;
   where they differ, look at the printed page and decide.

Then put the text together in reading order and convert it to EPUB.

## A scanned book

A scanned book is a set of page images with no text. Run OCR first, for the Latin and the
Arabic parts as described above. Check the result page by page, then build an EPUB with real
headings and linked footnotes.

## A book written entirely in Arabic

When the whole source is Arabic, there are no "Arabic quotations" to keep: the Arabic text is
the text to translate. Do not ask for the Arabic to be kept as printed. Technical and religious
terms are handled by the terminology area like any other term: the book prints the original
term with its approved translation, and a short note explains it at its first use.

## Before you start a request

- Use one file: the EPUB you checked. The workshop uses no other edition or web text unless you
  name it.
- Keep your original PDF or scans; they are your evidence when a passage is unclear.
