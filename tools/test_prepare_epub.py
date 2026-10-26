"""EPUB preparation on a small EPUB built in the test: order, notes, splits, Arabic and reruns."""
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import prepare_epub as p

ARABIC = 'بِسْمِ اللّهِ الرَّحْمٰنِ الرَّحِيمِ'
PAGE = '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>x</title></head><body>{}</body></html>'
OPF = '''<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test Book</dc:title></metadata>
<manifest>
<item id="notes" href="text/notes.xhtml" media-type="application/xhtml+xml"/>
<item id="b" href="text/b.xhtml" media-type="application/xhtml+xml"/>
<item id="a" href="text/a.xhtml" media-type="application/xhtml+xml"/>
<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine><itemref idref="cover"/><itemref idref="a"/><itemref idref="b"/><itemref idref="notes" linear="no"/></spine>
<guide><reference type="cover" href="text/cover.xhtml"/></guide></package>'''


def build(path, b_body='<h1>Second</h1><p>Plain&nbsp;text.</p>'):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip')
        z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        z.writestr('OEBPS/content.opf', OPF)
        z.writestr('OEBPS/text/cover.xhtml', PAGE.format('<p>Publisher cover</p>'))
        z.writestr('OEBPS/text/a.xhtml', PAGE.format(
            f'<h1><strong>First </strong></h1><p class="center">{ARABIC}</p>'
            '<p>Text with <strong>bold </strong>and a note<a href="notes.xhtml#fn-1"><sup>1</sup></a>.</p>'
            '<h2>Part two</h2><p>More<br/>lines.</p>'))
        z.writestr('OEBPS/text/b.xhtml', PAGE.format(b_body))
        z.writestr('OEBPS/text/notes.xhtml', PAGE.format(
            '<div id="fn-1">1) <p>Author note.<a href="a.xhtml#back-1">&#x21B5;</a></p><p>Second paragraph.</p></div>'))


class PrepareEpubTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.epub = self.root / 'book.epub'
        build(self.epub)

    def files(self):
        return {path.name: path.read_text(encoding='utf-8') for path in sorted((self.root / 'sources/book/segments').glob('*.md'))}

    def test_spine_order_notes_and_arabic(self):
        result = p.write(self.epub, 'book', self.root)
        self.assertEqual(result['units'], 2)
        files = self.files()
        self.assertEqual(list(files), ['001-a.md', '002-b.md'])
        first = files['001-a.md']
        self.assertTrue(first.startswith('## OEBPS/text/a.xhtml\n\n### First\n\n'))
        self.assertIn('\n' + ARABIC + '\n', first)
        self.assertIn('Text with **bold** and a note[^1].', first)
        self.assertIn('More\nlines.', first)
        self.assertTrue(first.endswith('[^1]: Author note.\n\n    Second paragraph.\n'))
        self.assertIn('Plain\xa0text.', files['002-b.md'])
        overview = (self.root / 'sources/book/overview.md').read_text(encoding='utf-8')
        self.assertIn('`OEBPS/text/cover.xhtml`: marked cover in the EPUB guide', overview)
        self.assertIn('`OEBPS/text/notes.xhtml`: non-linear spine item', overview)
        self.assertNotIn('Publisher cover', ''.join(files.values()))

    def test_same_document_note_is_emitted_once_at_its_call(self):
        build(self.epub, '<p>Text<a epub:type="noteref" href="#n2">2</a>.</p>'
                         '<aside id="n2" epub:type="footnote"><p>Local note.</p></aside><p>After.</p>')
        p.write(self.epub, 'book', self.root)
        second = self.files()['002-b.md']
        self.assertEqual(second, '## OEBPS/text/b.xhtml\n\nText[^2].\n\nAfter.\n\n[^2]: Local note.\n')
        self.assertTrue(self.files()['001-a.md'].endswith('[^1]: Author note.\n\n    Second paragraph.\n'))

    def test_list_numbers_follow_the_source(self):
        build(self.epub, '<ol start="5"><li>Fifth</li><li value="9">Ninth</li><li>Tenth</li></ol><ul><li>Item</li></ul>')
        p.write(self.epub, 'book', self.root)
        self.assertIn('5. Fifth\n\n9. Ninth\n\n10. Tenth\n\n- Item', self.files()['002-b.md'])

    def test_long_document_splits_at_headings_only(self):
        with patch.object(p, 'LONG', 40):
            p.write(self.epub, 'book', self.root)
        files = self.files()
        self.assertEqual(list(files), ['001-a.md', '002-a.md', '003-b.md'])
        self.assertTrue(files['002-a.md'].startswith('## OEBPS/text/a.xhtml (2/2)\n\n#### Part two'))
        self.assertIn('[^1]: Author note.', files['001-a.md'])
        self.assertNotIn('[^1]', files['002-a.md'])

    def test_rerun_is_byte_identical_and_changed_source_is_refused(self):
        p.write(self.epub, 'book', self.root)
        before = self.files()
        p.write(self.epub, 'book', self.root)
        self.assertEqual(self.files(), before)
        build(self.epub, '<p>Different text.</p>')
        with self.assertRaisesRegex(ValueError, 'needs approval'):
            p.write(self.epub, 'book', self.root)
        self.assertEqual(self.files(), before)


if __name__ == '__main__':
    unittest.main()
