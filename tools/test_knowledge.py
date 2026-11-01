"""Data integrity tests; generated files stay in disposable knowledge directories."""
import re
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import knowledge as k

class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=k.ROOT/'knowledge',prefix='.test-knowledge-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config=self.save('config.json',{'engine':'sqlite','path':str(self.root/'store.sqlite')})
        self.store=k.Knowledge(self.config); self.store.init()
        source=self.root/'source'; source.mkdir()
        self.source=source/'001-one.md'
        self.source.write_text('## text/one.xhtml\nNamaz ve nefs.\n\nNefs-i emmâre ve nefs.\n',encoding='utf-8')
        self.project=self.save('project.json',{'id':'ro-book','target_language':'ro','prepared_source':str(source),'translation':str(self.root/'translation')})
        self.term={'id':'namaz','language':'ro','source_form':'namaz','reading_form':'namaz','translation':'rugăciune','arabic':'صَلَاة',
                   'footnote':'Text exact\ncu „Unicode” şi نَفْس.','later_use':'equivalent','sense':'ritual prayer','note':None,
                   'approval':'User-supplied exact text','approved_at':'2026-10-24'}
        self.terms=[self.term]
    def save(self,name,data):
        p=self.root/name; p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8'); return p
    def lines(self,name,records):
        p=self.root/name; p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8'); return p
    def import_data(self,store=None): (store or self.store).import_terms(self.lines('terms.jsonl',self.terms))
    def test_scan_and_cli_pagination(self):
        from contextlib import redirect_stdout
        import io
        self.source.write_text('## text/one.xhtml\n'+'Namaz '*12+'\n\nNamaz.')
        self.import_data()
        self.assertEqual({k:v for k,v in self.store.scan(self.project,'001-001')[0].items() if k!='path'},{'id':'namaz','term':'namaz','text':'Namaz','line':2})
        self.assertEqual(self.store.scan(self.project)[-1]['line'],4)
        captured=io.StringIO()
        with redirect_stdout(captured): code=k.main(['--config',str(self.config),'scan','--project',str(self.project),'--units','001-001'])
        output=json.loads(captured.getvalue()); self.assertEqual(code,0)
        self.assertEqual(len(output['items']),10); self.assertEqual(output['next_cursor'],10)
    def test_languages_are_isolated_and_listed(self):
        self.terms.append(dict(self.term,id='fr-namaz',language='fr',translation='prière',footnote='Note française.'))
        self.import_data()
        self.assertEqual([r['id'] for r in self.store.find('namaz','ro')],['namaz'])
        self.assertEqual([r['id'] for r in self.store.find('namaz','fr')],['fr-namaz'])
        self.assertEqual({hit['id'] for hit in self.store.scan(self.project)},{'namaz'})
        self.assertEqual([(r['id'],r['translation'],r['footnote']) for r in self.store.terms_list('fr')],[('fr-namaz','prière','Note française.')])
    def test_find_matches_the_original_and_its_inflections_only(self):
        self.terms.append(dict(self.term,id='nefs-i-emmare',source_form='nefs-i emmâre',reading_form='nefs poruncitor'))
        self.terms.append(dict(self.term,id='nefs',source_form='nefs',reading_form='nefs'))
        self.import_data()
        self.assertEqual([(r['id'],r['match_type']) for r in self.store.find('NAMAZA','ro')],[('namaz','inflection')])
        self.assertEqual([(r['id'],r['match_type']) for r in self.store.find('Nefs-i emmâre','ro')],[('nefs-i-emmare','exact'),('nefs','contained')])
        self.assertEqual([r['id'] for r in self.store.find('nefsim','ro')],['nefs'])
        # An approved term inside a compound is a candidate too.
        self.assertEqual([(r['id'],r['match_type']) for r in self.store.find('namaz kılmak','ro')],[('namaz','contained')])
        self.assertEqual([(r['id'],r['match_type']) for r in self.store.find('seyahat-ı nefsiye','ro')],[('nefs','contained')])
        self.assertEqual(k.fold('Mün’im'),k.fold("Mün'im"))
        for query in ('ritual','nam','" OR missing *',''):
            self.assertEqual(self.store.find(query,'ro'),[])
    def test_prefix_of_another_word_is_only_an_inflection_candidate(self):
        self.terms.append(dict(self.term,id='hak',source_form='hak',reading_form='hak'))
        self.import_data()
        self.assertEqual([(r['id'],r['match_type']) for r in self.store.find('hakikat','ro')],[('hak','inflection')])
        self.assertEqual([(r['id'],r['match_type']) for r in self.store.find('Hak','ro')],[('hak','exact')])
    def test_vowel_signs_do_not_change_a_form(self):
        with self.store.write() as c: self.store.put_term(c,dict(self.term,id='rahma',source_form='رحمة'))
        self.assertEqual([(r['id'],r['match_type']) for r in self.store.find('رَحْمَةٌ','ro')],[('rahma','exact')])
    def test_other_schema_asks_for_a_rebuild(self):
        with self.store.write(export=False) as c: c.execute("UPDATE meta SET value='6' WHERE key='schema_version'")
        with self.assertRaisesRegex(k.KnowledgeError,'rebuild the store') as caught: self.store.integrity()
        self.assertEqual(caught.exception.code,'schema_version')
    def test_export_follows_term_writes_but_not_lugat(self):
        exported=self.root/'exporting.jsonl'
        store=k.Knowledge(self.save('exporting.json',{'engine':'sqlite','path':str(self.root/'exporting.sqlite'),'export':str(exported)})); store.init()
        self.import_data(store)
        self.assertEqual([json.loads(line)['id'] for line in exported.read_text(encoding='utf-8').splitlines()],['namaz'])
        with store.write(dry_run=True) as c: store.put_term(c,dict(self.term,translation='rugăciune rituală'))
        self.assertEqual(json.loads(exported.read_text(encoding='utf-8'))['translation'],'rugăciune')
        with store.write() as c: store.put_term(c,dict(self.term,translation='rugăciune rituală'))
        self.assertEqual(json.loads(exported.read_text(encoding='utf-8'))['translation'],'rugăciune rituală')
        before=exported.read_bytes(); p=self.root/'lugat.sql'
        p.write_text("INSERT INTO db_lugat (id,indeks,kelime,kirpilmis,anlam) VALUES (1,'A','a','a','a');")
        store.import_lugat(p); self.assertEqual(exported.read_bytes(),before)
    def test_empty_store_never_replaces_populated_export(self):
        exported=self.root/'populated.jsonl'; exported.write_text('{"id":"kept"}\n')
        store=k.Knowledge(self.save('empty.json',{'engine':'sqlite','path':str(self.root/'empty.sqlite'),'export':str(exported)})); store.init()
        store._refresh_export(exported); self.assertEqual(exported.read_text(encoding='utf-8'),'{"id":"kept"}\n')
    def test_concurrent_writes_export_the_final_state(self):
        from concurrent.futures import ThreadPoolExecutor
        exported=self.root/'concurrent.jsonl'
        config=self.save('concurrent.json',{'engine':'sqlite','path':str(self.root/'concurrent.sqlite'),'export':str(exported)})
        store=k.Knowledge(config); store.init(); self.import_data(store)
        def write(n):
            worker=k.Knowledge(config)
            with worker.write() as c: worker.put_term(c,dict(self.term,id=f'namaz-{n}'))
        with ThreadPoolExecutor(6) as pool: list(pool.map(write,range(12)))
        self.assertEqual(len(exported.read_text(encoding='utf-8').splitlines()),13)
        self.assertFalse(exported.with_name(exported.name+'.tmp').exists())
    def adapter_project(self):
        return {'id':'ro-book','target_language':'ro','translation':str(self.root/'translation'),'knowledge':str(self.config)}
    def test_validator_adapter_exact_note_and_reading_form(self):
        self.term['reading_form']='Namaz'
        self.terms.append(dict(self.term,id='fr-namaz',language='fr'))
        self.import_data()
        terms=k.load_project_terms(self.adapter_project(),k.ROOT)
        self.assertEqual(terms,{'namaz':{'reading':'Namaz','gloss':'rugăciune','body':self.term['footnote'],'later':'equivalent'}})
        self.assertTrue(re.fullmatch(k.stem_pattern('nefs poruncitor'),k.fold('Nefsului poruncitor')))
    def test_validator_adapter_missing_store_no_legacy_fallback(self):
        project=self.adapter_project(); project['terminology']='existing-legacy.md'; del project['knowledge']
        with self.assertRaises(k.KnowledgeError) as caught: k.load_project_terms(project,k.ROOT)
        self.assertEqual(caught.exception.code,'missing_knowledge_route')
        project['knowledge']=str(self.save('missingconfig.json',{'engine':'sqlite','path':str(self.root/'absent.sqlite')}))
        with self.assertRaises(k.KnowledgeError) as caught: k.load_project_terms(project,k.ROOT)
        self.assertEqual(caught.exception.code,'missing_store'); self.assertFalse((self.root/'absent.sqlite').exists())
    def test_unit_scope_and_directory_source(self):
        self.import_data()
        (self.source.parent/'002-two.md').write_text('## text/two.xhtml\nNamaz.\n',encoding='utf-8')
        self.assertEqual({Path(hit['path']).name for hit in self.store.scan(self.project,'001-001')},{'001-one.md'})
        self.assertEqual(self.store.scan(self.project)[-1]['path'],(self.source.parent.relative_to(k.ROOT)/'002-two.md').as_posix())
        single=self.save('single.json',{'id':'ro-book','target_language':'ro','prepared_source':str(self.source),'translation':str(self.root/'translation')})
        with self.assertRaises(k.KnowledgeError) as caught: self.store.scan(single)
        self.assertEqual(caught.exception.code,'missing_source')
    def test_new_database_wal(self):
        with closing(self.store.read()) as c: self.assertEqual(c.execute('PRAGMA journal_mode').fetchone()[0],'wal')
    def test_search_index_mismatch_detected(self):
        p=self.root/'lugat.sql'; p.write_text("INSERT INTO db_lugat (id,indeks,kelime,kirpilmis,anlam) VALUES (1,'A','a','a','a');")
        self.import_data(); self.store.import_lugat(p)
        with self.store.write() as c: c.execute('DELETE FROM lugat_fts WHERE id=1')
        with self.assertRaises(k.KnowledgeError) as caught: self.store.integrity()
        self.assertEqual(caught.exception.code,'integrity')
    def test_sql_parser_escapes_null_unicode_duplicates(self):
        text=r"INSERT INTO `db_lugat` (`id`, `indeks`, `kelime`, `kirpilmis`, `anlam`) VALUES (1,'A0','şî','si','a\n\'b\\c\t'),(2,'A0','şî',NULL,'it''s نَفْس');"
        rows=list(k.parse_lugat(text))
        self.assertEqual(rows[0]['anlam'],"a\n'b\\c\t")
        self.assertIsNone(rows[1]['kirpilmis']); self.assertEqual(rows[1]['anlam'],"it's نَفْس")
        p=self.root/'lugat.sql'; p.write_text(text,encoding='utf-8')
        self.store.import_lugat(p); self.assertTrue(self.store.import_lugat(p)['unchanged'])
        self.assertEqual(len(self.store.lugat_search('SI')),2)
        self.assertEqual(self.store.lugat_get(2)['anlam'],"it's نَفْس")
        self.assertEqual(self.store.lugat_search('" OR missing *'),[])
        p.write_text(text.replace('it','that'),encoding='utf-8')
        with self.assertRaises(k.KnowledgeError) as caught: self.store.import_lugat(p)
        self.assertEqual(caught.exception.code,'import_conflict')
    def test_bak_references_name_their_entries(self):
        p=self.root/'refs.sql'
        p.write_text("INSERT INTO db_lugat (id,indeks,kelime,kirpilmis,anlam) VALUES (1,'A','A','a','Bak: B'),(2,'B','B','b','x'),(3,'C','C','c','Bak: missing'),(5,'B','B','b','duplicate');")
        self.store.import_lugat(p)
        self.assertEqual(self.store.lugat_get(1)['references'],[{'query':'B','target_ids':[2,5]}])
        self.assertEqual(self.store.lugat_get(3)['references'],[{'query':'missing','target_ids':[]}])
    def test_bad_dump_rollback(self):
        p=self.root/'bad.sql'; p.write_text("INSERT INTO db_lugat (id,indeks,kelime,kirpilmis,anlam) VALUES (1,'A','a',NULL,'a'),(2,'A','b',NULL,FUNCTION());")
        with self.assertRaises(k.KnowledgeError): self.store.import_lugat(p)
        with closing(self.store.read()) as c: self.assertEqual(c.execute('SELECT count(*) FROM lugat').fetchone()[0],0)
    def test_read_connection_cannot_write(self):
        self.import_data()
        with closing(self.store.read()) as c:
            with self.assertRaises(sqlite3.OperationalError): c.execute('DELETE FROM terms')
        self.assertEqual(self.store.term_get('namaz')['footnote'],self.term['footnote'])
    def test_import_is_atomic_and_needs_an_empty_table(self):
        self.terms.append(dict(self.term,id='other',status='approved'))
        with self.assertRaises(k.KnowledgeError): self.import_data()
        self.assertEqual(self.store.terms_list('ro'),[])
        self.terms.pop(); self.import_data()
        with self.assertRaises(k.KnowledgeError) as caught: self.import_data()
        self.assertEqual(caught.exception.code,'import_conflict')
    def test_put_term_keeps_language(self):
        self.import_data()
        with self.store.write() as c: self.store.put_term(c,dict(self.term,translation='rugăciune rituală'))
        self.assertEqual(self.store.term_get('namaz')['translation'],'rugăciune rituală')
        with self.assertRaises(k.KnowledgeError) as caught:
            with self.store.write() as c: self.store.put_term(c,dict(self.term,language='fr'))
        self.assertEqual(caught.exception.code,'language_conflict')
        for bad in (dict(self.term,status='approved'),{f:v for f,v in self.term.items() if f!='reading_form'},dict(self.term,footnote=' ')):
            with self.assertRaises(k.KnowledgeError):
                with self.store.write() as c: self.store.put_term(c,bad)
        # A term without a note stores footnote null.
        with self.store.write() as c: self.store.put_term(c,dict(self.term,footnote=None))
        self.assertIsNone(self.store.term_get('namaz')['footnote'])
    def test_jsonl_roundtrip(self):
        self.import_data(); out=self.root/'transfer.jsonl'; self.store.export_terms(out)
        other=k.Knowledge(self.save('config2.json',{'engine':'sqlite','path':str(self.root/'other.sqlite')})); other.init(); other.import_terms(out)
        second=self.root/'second.jsonl'; other.export_terms(second)
        self.assertEqual(out.read_bytes(),second.read_bytes())
        self.assertEqual(json.loads(out.read_text(encoding='utf-8')),self.term)
    def test_scope_mismatch_and_path_boundary(self):
        with self.assertRaises(k.KnowledgeError) as caught: self.store.scan(self.project,'005-006')
        self.assertEqual(caught.exception.code,'missing_scope')
        with self.assertRaises(k.KnowledgeError): self.store.scan(self.project,'003-001')
        with self.assertRaises(k.KnowledgeError): k.path('/tmp/not-authorized.sqlite',write=True)
        with self.assertRaises(k.KnowledgeError): k.path('knowledge/../outside.sqlite',write=True)

if __name__=='__main__': unittest.main()
