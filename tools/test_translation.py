"""Exercise project routing and read-only source/terminology access in disposable projects."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import knowledge
import translation as t


class TranslationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=knowledge.ROOT / 'knowledge', prefix='.test-translation-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patched = patch.object(t, 'ROOT', self.root)
        patched.start()
        self.addCleanup(patched.stop)
        self.source = self.save('Book-original-sources/book.epub', b'PK-fixture')
        self.segment = self.save('sources/book/segments/001-one.md', '## text/one.xhtml\nNamaz ve saadet-i ebediye.\n')
        self.manifest = self.save('translations/ro/book/project.json', {
            'id': 'ro-book', 'source_language': 'tr', 'target_language': 'ro',
            'sources': [{'path': t.relative(self.source), 'role': 'primary'}],
            'prepared_source': 'sources/book/segments',
            'translation': 'translations/ro/book/translation', 'knowledge': 'knowledge/config.json'})
        config = self.save('knowledge/config.json', {'engine': 'sqlite', 'path': str(self.root / 'knowledge/store.sqlite')})
        self.store = knowledge.Knowledge(config)
        self.store.init()

    def save(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value, encoding='utf-8')
        return path

    def cli(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            result = t.main(list(args))
        return result, json.loads(output.getvalue())

    def prepare(self, **kwargs):
        return t.prepare(t.relative(self.source), 'tr', 'ro', **kwargs)

    def term(self, **changes):
        record = {'id': 'namaz', 'language': 'ro', 'source_form': 'namaz', 'reading_form': 'namaz', 'translation': 'rugăciune rituală',
                  'arabic': 'صَلَاة', 'footnote': 'Exact Romanian note\nwith Unicode: ăîșț and صَلَاة.',
                  'sense': 'Islamic ritual prayer', 'note': None, 'approval': 'Exact fixture wording',
                  'approved_at': '2026-10-24',
                  'placements': [{'book_id': 'book', 'source_path': 'sources/book/segments/001-one.md', 'source_line': 2,
                                  'source_quote': None, 'translation_path': 'target.md',
                                  'translation_line': 2, 'first_expression': None}]}
        record.update(changes)
        with self.store.write() as connection:
            self.store.put_term(connection, record)
            for placement in record['placements']:
                self.store.put_placement(connection, dict(placement, term_id=record['id']))
        return record

    def test_existing_preparation_returns_metadata_without_mutation(self):
        before = {p: t.fingerprint(p) for p in (self.manifest, self.source, self.segment)}
        result = self.prepare(create=True)
        self.assertEqual(result['state'], 'available')
        self.assertEqual(result['unit_count'], 1)
        self.assertNotIn('Namaz', json.dumps(result))
        self.assertEqual(before, {p: t.fingerprint(p) for p in before})

    def test_new_project_derives_identity_and_reports_missing_extraction(self):
        source = self.save('Book-original-sources/İkinci Kitap.epub', b'PK-other')
        result = t.prepare(t.relative(source), 'tr', 'ro', create=True)
        self.assertEqual(result['project'], 'translations/ro/ikinci-kitap/project.json')
        self.assertEqual(result['state'], 'preparation_required')
        self.assertIn('prepared_source', result['needs'])
        data = t.load(self.root / result['project'])
        self.assertEqual(data['knowledge'], 'knowledge/config.json')
        self.assertTrue((self.root / data['prepared_source']).is_dir())
        self.assertEqual(result['preparation_command'], ['python3', '-B', 'tools/prepare_epub.py', '--epub',
                                                         'Book-original-sources/İkinci Kitap.epub', '--book', 'ikinci-kitap'])

    def test_no_create_means_no_files_created(self):
        source = self.save('new.epub', b'PK-new')
        result = t.prepare(t.relative(source), 'tr', 'fr')
        self.assertEqual(result['state'], 'setup_required')
        self.assertFalse((self.root / result['project']).exists())

    def test_source_authority_and_language_mismatch_are_rejected(self):
        before = t.fingerprint(self.manifest)
        source = self.save('other.epub', b'PK-other')
        with self.assertRaisesRegex(ValueError, 'source differs'):
            t.prepare(t.relative(source), 'tr', 'ro', project_path=t.relative(self.manifest), create=True)
        with self.assertRaisesRegex(ValueError, 'Language mismatch'):
            t.prepare(t.relative(self.source), 'ar', 'ro', create=True)
        self.assertEqual(t.fingerprint(self.manifest), before)

    def test_multiple_source_projects_require_explicit_selection(self):
        first = t.load(self.manifest)
        self.manifest.unlink()
        self.save('translations/ro/edition-a/project.json', first)
        self.save('translations/ro/edition-b/project.json', first)
        with self.assertRaisesRegex(ValueError, 'Multiple projects'):
            self.prepare(create=True)
        result = self.prepare(project_path='translations/ro/edition-b/project.json')
        self.assertEqual(result['project'], 'translations/ro/edition-b/project.json')

    def test_shared_source_collision_does_not_create_project(self):
        source = self.save('different/book.epub', b'PK-other-edition')
        with self.assertRaisesRegex(ValueError, 'collision'):
            t.prepare(t.relative(source), 'tr', 'fr', create=True)
        self.assertFalse((self.root / 'translations/fr/book/project.json').exists())

    def test_external_import_preserves_bytes_and_rejects_conflicting_name(self):
        with tempfile.TemporaryDirectory() as external:
            source = Path(external) / 'external.epub'
            source.write_bytes(b'PK-external')
            result = t.prepare(str(source), 'tr', 'ro', create=True)
            imported = self.root / result['source']
            self.assertEqual(imported.read_bytes(), source.read_bytes())
            t.prepare(str(source), 'tr', 'ro', create=True)
            source.write_bytes(b'PK-changed')
            with self.assertRaisesRegex(ValueError, 'different source'):
                t.prepare(str(source), 'tr', 'ro', create=True)
            self.assertEqual(imported.read_bytes(), b'PK-external')

    def test_unsafe_project_path_fails_before_external_copy(self):
        with tempfile.TemporaryDirectory() as external:
            source = Path(external) / 'external.epub'
            source.write_bytes(b'PK-external')
            for path in ('../outside/project.json', 'README.md', 'translations/fr/book/project.json'):
                with self.assertRaises(ValueError):
                    t.prepare(str(source), 'tr', 'ro', project_path=path, create=True)
            self.assertFalse((self.root / 'Book-original-sources/imported').exists())

    def test_only_epub_sources_are_accepted(self):
        source = self.save('Book-original-sources/book.pdf', b'%PDF-fixture')
        with self.assertRaisesRegex(ValueError, 'EPUB'):
            t.prepare(t.relative(source), 'tr', 'ro', create=True)

    def test_units_follow_file_names_and_read_one_unit(self):
        self.save('sources/book/segments/002-two.md', '## text/two.xhtml\nSecond paragraph.\n')
        code, output = self.cli('segments', '--project', t.relative(self.manifest), '--limit', '1')
        self.assertEqual(code, 0)
        self.assertEqual(output['result']['next_cursor'], 1)
        self.assertEqual(output['result']['items'][0]['id'], '001-one')
        self.assertNotIn('Namaz', json.dumps(output))
        _, second = self.cli('segments', '--project', t.relative(self.manifest), '--cursor', '1')
        unit = second['result']['items'][0]
        self.assertEqual(unit, {'id': '002-two', 'path': 'sources/book/segments/002-two.md', 'start_line': 1, 'end_line': 2})
        _, read = self.cli('read', '--project', t.relative(self.manifest), '--unit', unit['id'])
        self.assertIn('Second paragraph', read['result']['text'])
        self.assertNotIn('Namaz', read['result']['text'])

    def test_bad_locations_and_empty_terms_do_not_emit_requests(self):
        for term, at in [('namaz', 'other.md:2'), ('namaz', t.relative(self.segment) + ':99'),
                         ('maz', t.relative(self.segment) + ':2'), ('', t.relative(self.segment) + ':2')]:
            with self.assertRaises(ValueError):
                t.term_request(t.relative(self.manifest), term, at)

    def test_missing_term_request_has_exact_pointer_and_no_sqlite_write(self):
        before = t.fingerprint(self.store.db)
        result = t.term_request(t.relative(self.manifest), 'namaz', t.relative(self.segment) + ':2')
        self.assertEqual(result, {'state': 'request', 'text': 'namaz (sources/book/segments/001-one.md:2)'})
        self.assertEqual(t.fingerprint(self.store.db), before)

    def test_approved_reuse_preserves_whole_note_and_uses_book_placement(self):
        record = self.term()
        before = t.fingerprint(self.store.db)
        result = t.term_request(t.relative(self.manifest), 'Namaz', t.relative(self.segment) + ':2')
        self.assertEqual(result['state'], 'approved')
        approved = result['records'][0]
        self.assertEqual(approved['footnote'], record['footnote'])
        self.assertEqual(approved['language'], 'ro')
        self.assertEqual(approved['placements'], record['placements'])
        self.assertEqual(t.fingerprint(self.store.db), before)

    def test_other_language_terms_are_invisible_to_this_project(self):
        self.term(id='namaz-fr', language='fr', translation='prière', footnote='Note française.', placements=[])
        result = t.term_request(t.relative(self.manifest), 'namaz', t.relative(self.segment) + ':2')
        self.assertEqual(result, {'state': 'request', 'text': 'namaz (sources/book/segments/001-one.md:2)'})
        french = self.save('translations/fr/book/project.json', dict(t.load(self.manifest), id='fr-book', target_language='fr',
                                                                     translation='translations/fr/book/translation'))
        result = t.term_request(t.relative(french), 'namaz', t.relative(self.segment) + ':2')
        self.assertEqual(result['state'], 'approved')
        self.assertEqual(result['records'][0]['id'], 'namaz-fr')
        code, read = self.cli('read', '--project', t.relative(french), '--unit', '001-one')
        self.assertEqual([row['id'] for row in read['result']['known_terms']], ['namaz-fr'])

    def test_cli_rejects_unbounded_listing(self):
        code, result = self.cli('segments', '--project', t.relative(self.manifest), '--limit', '21')
        self.assertEqual(code, 2)
        self.assertFalse(result['ok'])

    def test_read_flags_existing_terms_without_research_or_complete_glossary(self):
        self.term()
        self.term(id='unrelated', source_form='unrelated', sense='Not in the source', placements=[])
        self.segment.write_text('## text/one.xhtml\nNamaz ve namaz.\n', encoding='utf-8')
        before = t.fingerprint(self.store.db)
        code, result = self.cli('read', '--project', t.relative(self.manifest), '--unit', '001-one')
        self.assertEqual(code, 0)
        self.assertEqual(result['result']['known_terms'], [{'id': 'namaz', 'term': 'namaz', 'text': 'Namaz', 'line': 2}])
        self.assertEqual(t.fingerprint(self.store.db), before)

    def test_read_does_not_silently_skip_unavailable_terminology_store(self):
        self.store.db.unlink()
        code, result = self.cli('read', '--project', t.relative(self.manifest), '--unit', '001-one')
        self.assertEqual(code, 2)
        self.assertFalse(result['ok'])

    def test_failed_authority_check_does_not_import_an_external_file(self):
        with tempfile.TemporaryDirectory() as external:
            source = Path(external) / 'wrong.epub'
            source.write_bytes(b'PK-other-edition')
            with self.assertRaisesRegex(ValueError, 'source differs'):
                t.prepare(str(source), 'tr', 'ro', project_path=t.relative(self.manifest), create=True)
            self.assertFalse((self.root / 'Book-original-sources/imported').exists())

    def test_corrupt_store_is_a_structured_error_without_source_output(self):
        self.store.db.write_bytes(b'not a SQLite database')
        code, result = self.cli('read', '--project', t.relative(self.manifest), '--unit', '001-one')
        self.assertEqual(code, 2)
        self.assertFalse(result['ok'])
        self.assertNotIn('Namaz', json.dumps(result))



if __name__ == '__main__':
    unittest.main()
