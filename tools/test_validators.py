"""The shared book validator on a disposable two-unit project: coverage, author notes, waiting terms, verbatim script, terms."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import knowledge
import validate_translation

ROOT = Path(__file__).resolve().parents[1]
QUOTE = 'بِسْمِ اللّهِ الرَّحْمٰنِ'
NOTE = 'Namaz (arab. ṣalāt, صَلَاة): rugăciunea rituală.'
FIRST = f'## a\nNamazul (rugăciunea)[^term-ro-namaz] începe cu {QUOTE}.\n\n[^term-ro-namaz]: {NOTE}\n'
SECOND = '## b\nNamazurile (rugăciunea) urmează.\n'


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'knowledge', prefix='.test-validators-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        relative = lambda path: str(path.relative_to(ROOT))
        self.save('segments/001-a.md', f'## a\nNamaz {QUOTE} ile başlar.\n')
        self.save('segments/002-b.md', '## b\nNamazlar devam eder.\n')
        self.save('translation/001-a.ro.md', FIRST)
        self.save('translation/002-b.ro.md', SECOND)
        config = self.save('config.json', json.dumps({'engine': 'sqlite', 'path': str(self.root / 'store.sqlite')}))
        self.store = store = knowledge.Knowledge(config)
        store.init()
        with store.write() as connection:
            store.put_term(connection, {'id': 'term-ro-namaz', 'language': 'ro', 'source_form': 'namaz', 'reading_form': 'namaz',
                                        'translation': 'rugăciune', 'arabic': 'صَلَاة', 'footnote': NOTE, 'sense': 'ritual prayer',
                                        'note': None, 'approval': 'Fixture', 'approved_at': '2026-10-25'})
        self.project = self.save('project.json', json.dumps({
            'id': 'ro-book', 'target_language': 'ro', 'prepared_source': relative(self.root / 'segments'),
            'translation': relative(self.root / 'translation'), 'knowledge': relative(config), 'verbatim_script': 'Arabic'}))

    def save(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def run_scope(self, units):
        with redirect_stdout(io.StringIO()):
            return validate_translation.main(['--project', str(self.project), '--units', units])

    def test_complete_book_passes(self):
        self.assertEqual(self.run_scope('001-002'), 0)

    def test_waiting_placeholder_fails_inside_scope_only(self):
        self.save('translation/002-b.ro.md', SECOND + '\nText {{TERM:audit}}.\n')
        self.assertEqual(self.run_scope('001-001'), 0)
        with self.assertRaisesRegex(RuntimeError, 'Waiting terminology placeholder'):
            self.run_scope('001-002')

    def test_coverage_needs_every_unit_and_no_strays(self):
        (self.root / 'translation/002-b.ro.md').unlink()
        self.assertEqual(self.run_scope('001-001'), 0)
        with self.assertRaisesRegex(RuntimeError, 'coverage failed'):
            self.run_scope('001-002')
        self.save('translation/003-c.ro.md', 'Stray.\n')
        with self.assertRaisesRegex(RuntimeError, 'without a source unit'):
            self.run_scope('001-001')

    def test_verbatim_script_is_copied_exactly(self):
        self.save('translation/001-a.ro.md', FIRST.replace(QUOTE, QUOTE.replace('ٰ', 'ا')))
        with self.assertRaisesRegex(RuntimeError, 'Verbatim Arabic text changed'):
            self.run_scope('001-001')
        # Arabic in a term footnote never stands in for the quotation.
        self.save('segments/001-a.md', '## a\nNamaz صَلَاة.\n')
        self.save('translation/001-a.ro.md', FIRST.replace(QUOTE, ''))
        with self.assertRaisesRegex(RuntimeError, 'Verbatim Arabic text changed'):
            self.run_scope('001-001')

    def test_retained_terms_inflect_freely_but_keep_their_parenthetical(self):
        self.save('translation/002-b.ro.md', SECOND.replace(' (rugăciunea)', ''))
        with self.assertRaisesRegex(RuntimeError, 'Missing parenthetical equivalent for Namazurile'):
            self.run_scope('001-002')

    def test_empty_unit_fails(self):
        self.save('translation/002-b.ro.md', ' \n\n')
        with self.assertRaisesRegex(RuntimeError, 'Empty translation unit: 002-b.ro.md'):
            self.run_scope('001-002')

    def test_author_notes_keep_their_identifiers(self):
        self.save('segments/002-b.md', '## b\nNamazlar[^1] devam eder.\n\n[^1]: Yazar notu.\n')
        with self.assertRaisesRegex(RuntimeError, 'Author notes differ from the source in 002-b.ro.md'):
            self.run_scope('001-002')
        self.save('translation/002-b.ro.md', '## b\nNamazurile (rugăciunea)[^2] urmează.\n\n[^2]: Nota autorului.\n')
        with self.assertRaisesRegex(RuntimeError, 'Author notes differ'):
            self.run_scope('001-002')
        self.save('translation/002-b.ro.md', '## b\nNamazurile (rugăciunea)[^1] urmează.\n\n[^1]: Nota autorului.\n')
        self.assertEqual(self.run_scope('001-002'), 0)

    def test_first_retained_occurrence_in_book_order_carries_the_note(self):
        self.save('translation/001-a.ro.md', '## a\nNamazul (rugăciunea) mai întâi.\n' + FIRST[5:])
        with self.assertRaisesRegex(RuntimeError, 'Missing footnote at first term occurrence: term-ro-namaz in 001-a.ro.md'):
            self.run_scope('001-002')
        self.save('translation/001-a.ro.md', f'## a\nNamazul (rugăciunea) începe cu {QUOTE}.\n')
        self.save('translation/002-b.ro.md', f'## b\nNamazurile (rugăciunea)[^term-ro-namaz] urmează.\n\n[^term-ro-namaz]: {NOTE}\n')
        with self.assertRaisesRegex(RuntimeError, 'Missing footnote at first term occurrence: term-ro-namaz in 001-a.ro.md'):
            self.run_scope('001-002')

    def test_note_is_exact_once_and_in_its_unit(self):
        self.save('translation/001-a.ro.md', FIRST.replace(NOTE, NOTE + ' Extra.'))
        with self.assertRaisesRegex(RuntimeError, 'Unapproved or altered editorial footnote'):
            self.run_scope('001-002')
        self.save('translation/001-a.ro.md', FIRST)
        self.save('translation/002-b.ro.md', f'## b\nNamazurile (rugăciunea)[^term-ro-namaz] urmează.\n\n[^term-ro-namaz]: {NOTE}\n')
        with self.assertRaisesRegex(RuntimeError, 'defined and called once in the book: term-ro-namaz'):
            self.run_scope('001-002')
        self.save('translation/001-a.ro.md', FIRST.split('\n\n')[0] + '\n')
        self.save('translation/002-b.ro.md', SECOND + f'\n[^term-ro-namaz]: {NOTE}\n')
        with self.assertRaisesRegex(RuntimeError, 'called and defined in the same unit: 001-a.ro.md'):
            self.run_scope('001-002')

if __name__ == '__main__':
    unittest.main()
