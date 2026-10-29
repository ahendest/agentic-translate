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
FIRST = f'## a\nNamazul (rugăciunea)[^namaz] începe cu {QUOTE}.\n\n[^namaz]: {NOTE}\n'
# A later use carries the equivalent without parentheses.
SECOND = '## b\nNamazurile rugăciunii urmează.\n'


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
            store.put_term(connection, {'id': 'namaz', 'language': 'ro', 'source_form': 'namaz', 'reading_form': 'namaz',
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

    def test_verbatim_paragraphs_separated_by_a_blank_line_pass(self):
        self.save('segments/001-a.md', f'## a\n{QUOTE}\n\n{QUOTE}\n')
        self.save('translation/001-a.ro.md', f'## a\n{QUOTE}\n\n{QUOTE}\n')
        self.save('segments/002-b.md', '## b\nText.\n')
        self.save('translation/002-b.ro.md', '## b\nText.\n')
        self.assertEqual(self.run_scope('001-001'), 0)

    def test_waiting_unit_outside_scope_does_not_count_as_a_first_use(self):
        self.save('segments/001-a.md', f'## a\nMetin {QUOTE}.\n')
        self.save('translation/001-a.ro.md', f'## a\nText {QUOTE}.\n')
        self.save('translation/002-b.ro.md', '## b\n{{TERM:namaz}} urmează.\n')
        self.assertEqual(self.run_scope('001-001'), 0)
        with self.assertRaisesRegex(RuntimeError, 'Waiting terminology placeholder'):
            self.run_scope('001-002')

    def test_term_without_footnote_is_written_as_a_later_use_everywhere(self):
        with self.store.write() as connection:
            self.store.put_term(connection, {'id': 'evliya', 'language': 'ro', 'source_form': 'evliya', 'reading_form': 'evliya',
                                             'translation': 'prieteni', 'arabic': None, 'footnote': None, 'sense': 'saints',
                                             'note': None, 'approval': 'Fixture', 'approved_at': '2026-10-28'})
        self.save('translation/002-b.ro.md', SECOND.replace('urmează', 'și evliya prieteni urmează'))
        self.assertEqual(self.run_scope('001-002'), 0)
        self.save('translation/002-b.ro.md', SECOND.replace('urmează', 'și evliya (prieteni) urmează'))
        with self.assertRaisesRegex(RuntimeError, 'Parenthetical after the first use of evliya'):
            self.run_scope('001-002')
        self.save('translation/002-b.ro.md', SECOND.replace('urmează', 'și evliya urmează') + '\n[^evliya]: Nota.\n')
        with self.assertRaisesRegex(RuntimeError, 'Unapproved or altered editorial footnote evliya'):
            self.run_scope('001-002')

    def test_note_call_holding_another_term_id_is_not_a_term_use(self):
        with self.store.write() as connection:
            self.store.put_term(connection, {'id': 'namaz-i-cuma', 'language': 'ro', 'source_form': 'namaz-ı cuma',
                                             'reading_form': 'namaz-i cuma', 'translation': 'rugăciunea de vineri', 'arabic': None,
                                             'footnote': 'Nota.', 'sense': 'Friday prayer', 'note': None,
                                             'approval': 'Fixture', 'approved_at': '2026-10-30'})
        self.save('translation/001-a.ro.md', FIRST.replace(
            'Namazul (rugăciunea)[^namaz]', 'Namaz-i cuma (rugăciunea de vineri)[^namaz-i-cuma], apoi Namazul (rugăciunea)[^namaz]')
            + '[^namaz-i-cuma]: Nota.\n')
        self.assertEqual(self.run_scope('001-002'), 0)

    def test_only_the_first_use_has_the_parenthetical(self):
        self.save('translation/001-a.ro.md', FIRST.replace('Namazul (rugăciunea)', 'Namazul'))
        with self.assertRaisesRegex(RuntimeError, 'Missing parenthetical equivalent at the first use of Namazul'):
            self.run_scope('001-002')
        self.save('translation/001-a.ro.md', FIRST)
        self.save('translation/002-b.ro.md', '## b\nNamazurile (rugăciunea) urmează.\n')
        with self.assertRaisesRegex(RuntimeError, r'Parenthetical after the first use of namaz: Namazurile \(rugăciunea\) in 002-b.ro.md'):
            self.run_scope('001-002')

    def test_empty_unit_fails(self):
        self.save('translation/002-b.ro.md', ' \n\n')
        with self.assertRaisesRegex(RuntimeError, 'Empty translation unit: 002-b.ro.md'):
            self.run_scope('001-002')

    def test_author_notes_keep_their_identifiers(self):
        self.save('segments/002-b.md', '## b\nNamazlar[^1] devam eder.\n\n[^1]: Yazar notu.\n')
        with self.assertRaisesRegex(RuntimeError, 'Author notes differ from the source in 002-b.ro.md'):
            self.run_scope('001-002')
        self.save('translation/002-b.ro.md', '## b\nNamazurile rugăciunii[^2] urmează.\n\n[^2]: Nota autorului.\n')
        with self.assertRaisesRegex(RuntimeError, 'Author notes differ'):
            self.run_scope('001-002')
        self.save('translation/002-b.ro.md', '## b\nNamazurile rugăciunii[^1] urmează.\n\n[^1]: Nota autorului.\n')
        self.assertEqual(self.run_scope('001-002'), 0)

    def test_first_retained_occurrence_in_book_order_carries_the_note(self):
        self.save('translation/001-a.ro.md', '## a\nNamazul (rugăciunea) mai întâi.\n' + FIRST[5:])
        with self.assertRaisesRegex(RuntimeError, 'Missing footnote at first term occurrence: namaz in 001-a.ro.md'):
            self.run_scope('001-002')
        self.save('translation/001-a.ro.md', f'## a\nNamazul (rugăciunea) începe cu {QUOTE}.\n')
        self.save('translation/002-b.ro.md', f'## b\nNamazurile (rugăciunea)[^namaz] urmează.\n\n[^namaz]: {NOTE}\n')
        with self.assertRaisesRegex(RuntimeError, 'Missing footnote at first term occurrence: namaz in 001-a.ro.md'):
            self.run_scope('001-002')

    def test_note_is_exact_once_and_in_its_unit(self):
        self.save('translation/001-a.ro.md', FIRST.replace(NOTE, NOTE + ' Extra.'))
        with self.assertRaisesRegex(RuntimeError, 'Unapproved or altered editorial footnote'):
            self.run_scope('001-002')
        # A repeated first-use form is refused at the later use.
        self.save('translation/001-a.ro.md', FIRST)
        self.save('translation/002-b.ro.md', f'## b\nNamazurile (rugăciunea)[^namaz] urmează.\n\n[^namaz]: {NOTE}\n')
        with self.assertRaisesRegex(RuntimeError, 'Parenthetical after the first use of namaz'):
            self.run_scope('001-002')
        self.save('translation/001-a.ro.md', FIRST.split('\n\n')[0] + '\n')
        self.save('translation/002-b.ro.md', SECOND + f'\n[^namaz]: {NOTE}\n')
        with self.assertRaisesRegex(RuntimeError, 'called and defined in the same unit: 001-a.ro.md'):
            self.run_scope('001-002')

    def test_missing_parts_are_decisions(self):
        """Gloss once, then the original alone; a note without an equivalent; an equivalent without the original."""
        mehdi = 'Mehdi (arab. mahdī, مَهْدِيّ): cel călăuzit.'
        fixture = {'language': 'ro', 'arabic': None, 'footnote': None, 'sense': 's', 'note': None,
                   'approval': 'Fixture', 'approved_at': '2026-10-30'}
        with self.store.write() as connection:
            for record in ({'id': 'ummet', 'source_form': 'ümmet', 'reading_form': 'ummet', 'translation': 'comunitate', 'later_use': 'original'},
                           {'id': 'mehdi', 'source_form': 'mehdi', 'reading_form': 'mehdi', 'translation': None, 'footnote': mehdi},
                           {'id': 'aktab', 'source_form': 'aktab', 'reading_form': None, 'translation': 'poli spirituali'}):
                self.store.put_term(connection, dict(fixture, **record))
        self.save('translation/001-a.ro.md', FIRST.replace('începe', 'ummetului (comunitatea), lui mehdi[^mehdi] și polilor spirituali începe')
                  + f'\n[^mehdi]: {mehdi}\n')
        self.save('translation/002-b.ro.md', '## b\nNamazurile rugăciunii ummetului și ale lui mehdi urmează.\n')
        self.assertEqual(self.run_scope('001-002'), 0)
        self.save('translation/002-b.ro.md', '## b\nNamazurile rugăciunii ummetului (comunitatea) urmează.\n')
        with self.assertRaisesRegex(RuntimeError, 'Parenthetical after the first use of ummet'):
            self.run_scope('001-002')

if __name__ == '__main__':
    unittest.main()
