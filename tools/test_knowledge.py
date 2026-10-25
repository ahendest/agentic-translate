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
        self.case=self.save('case.json',{'project':str(self.project),'units':'001-001'})
        self.term={'id':'term-namaz','language':'ro','source_form':'namaz','reading_form':'namaz','translation':'rugăciune','arabic':'صَلَاة',
                   'footnote':'Text exact\ncu „Unicode” şi نَفْس.','sense':'ritual prayer','note':None,
                   'approval':'User-supplied exact text','approved_at':'2026-10-24',
                   'placements':[{'book_id':'book','source_path':str(self.source),'source_line':2,'source_quote':None,
                                  'translation_path':'translation/first.md','translation_line':2,'first_expression':None}]}
        self.terms=[self.term]
    def save(self,name,data):
        p=self.root/name; p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8'); return p
    def lines(self,name,records):
        p=self.root/name; p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8'); return p
    def import_data(self,store=None): (store or self.store).import_terms(self.lines('terms.jsonl',self.terms))
    def target(self,body):
        directory=self.root/'translation'; directory.mkdir(exist_ok=True); target=directory/'first.md'
        target.write_text(body,encoding='utf-8'); return target
    def test_inline_markdown_note_ends_before_ordinary_paragraph(self):
        note=self.term['footnote'].replace('\n','\n    ')
        target=self.target('## one\nNamaz[^term-namaz].\n\n[^term-namaz]: '+note+'\n\nOrdinary paragraph after the note.\n')
        self.import_data(); self.assertEqual(self.store.check(self.case)[0]['warnings'],[])
        self.assertEqual(list(k.note_blocks(target.read_text()))[0][3],self.term['footnote'])
    def test_scan_and_cli_pagination(self):
        from contextlib import redirect_stdout
        import io
        self.source.write_text('## text/one.xhtml\n'+'Namaz '*12+'\n\nNamaz.')
        self.import_data()
        self.assertEqual({k:v for k,v in self.store.scan(self.case)[0].items() if k!='path'},{'id':'term-namaz','text':'Namaz','line':2})
        self.assertEqual(self.store.scan(self.case)[-1]['line'],4)
        captured=io.StringIO()
        with redirect_stdout(captured): code=k.main(['--config',str(self.config),'scan','--case',str(self.case)])
        output=json.loads(captured.getvalue()); self.assertEqual(code,0)
        self.assertEqual(len(output['items']),10); self.assertEqual(output['next_cursor'],10)
    def test_languages_are_isolated_and_listed(self):
        self.terms.append(dict(self.term,id='term-fr-namaz',language='fr',translation='prière',footnote='Note française.',placements=[]))
        self.import_data()
        self.assertEqual([r['id'] for r in self.store.find('namaz','ro')],['term-namaz'])
        self.assertEqual([r['id'] for r in self.store.find('namaz','fr')],['term-fr-namaz'])
        self.assertEqual({hit['id'] for hit in self.store.scan(self.case)},{'term-namaz'})
        with self.assertRaises(k.KnowledgeError) as caught: self.store.term_get('term-fr-namaz','ro')
        self.assertEqual(caught.exception.code,'not_found')
        self.assertEqual([(r['id'],r['translation'],r['footnote']) for r in self.store.terms_list('fr')],[('term-fr-namaz','prière','Note française.')])
    def test_find_matches_the_original_and_its_inflections_only(self):
        self.terms.append(dict(self.term,id='term-nefs-i-emmare',source_form='nefs-i emmâre',reading_form='nefs poruncitor',placements=[]))
        self.terms.append(dict(self.term,id='term-nefs',source_form='nefs',reading_form='nefs',placements=[]))
        self.import_data()
        self.assertEqual([(r['id'],r['match_type']) for r in self.store.find('NAMAZA','ro')],[('term-namaz','inflection')])
        self.assertEqual([r['id'] for r in self.store.find('Nefs-i emmâre','ro')],['term-nefs-i-emmare'])
        self.assertEqual([r['id'] for r in self.store.find('nefsim','ro')],['term-nefs'])
        for query in ('ritual','namaz kılmak','" OR missing *',''):
            self.assertEqual(self.store.find(query,'ro'),[])
    def test_export_follows_term_and_placement_writes_but_not_lugat(self):
        exported=self.root/'exporting.jsonl'
        store=k.Knowledge(self.save('exporting.json',{'engine':'sqlite','path':str(self.root/'exporting.sqlite'),'export':str(exported)})); store.init()
        self.import_data(store)
        self.assertEqual([json.loads(line)['id'] for line in exported.read_text().splitlines()],['term-namaz'])
        placement=dict(self.term['placements'][0],term_id='term-namaz',source_line=4)
        store.place(self.save('place.json',placement),dry_run=True)
        self.assertEqual(json.loads(exported.read_text())['placements'][0]['source_line'],2)
        store.place(self.save('place.json',placement))
        self.assertEqual(json.loads(exported.read_text())['placements'][0]['source_line'],4)
        before=exported.read_bytes(); p=self.root/'lugat.sql'
        p.write_text("INSERT INTO db_lugat (id,indeks,kelime,kirpilmis,anlam) VALUES (1,'A','a','a','a');")
        store.import_lugat(p); self.assertEqual(exported.read_bytes(),before)
    def test_empty_store_never_replaces_populated_export(self):
        exported=self.root/'populated.jsonl'; exported.write_text('{"id":"kept"}\n')
        store=k.Knowledge(self.save('empty.json',{'engine':'sqlite','path':str(self.root/'empty.sqlite'),'export':str(exported)})); store.init()
        store._refresh_export(exported); self.assertEqual(exported.read_text(),'{"id":"kept"}\n')
    def adapter_project(self):
        return {'id':'ro-book','target_language':'ro','translation':str(self.root/'translation'),'knowledge':str(self.config)}
    def test_concurrent_placement_writes_export_the_final_state(self):
        from concurrent.futures import ThreadPoolExecutor
        exported=self.root/'concurrent.jsonl'
        config=self.save('concurrent.json',{'engine':'sqlite','path':str(self.root/'concurrent.sqlite'),'export':str(exported)})
        store=k.Knowledge(config); store.init(); self.import_data(store)
        def write(n):
            worker=k.Knowledge(config)
            with worker.write() as c: worker.put_placement(c,dict(self.term['placements'][0],term_id='term-namaz',book_id=f'book-{n}'))
        with ThreadPoolExecutor(6) as pool: list(pool.map(write,range(12)))
        self.assertEqual(len(json.loads(exported.read_text())['placements']),13)
        self.assertFalse(exported.with_name(exported.name+'.tmp').exists())
    def test_validator_adapter_exact_note_and_reading_form(self):
        self.term['reading_form']='Namaz'; self.import_data()
        record=k.load_project_terms(self.adapter_project(),k.ROOT)['term-namaz']
        self.assertEqual((record['body'],record['reading'],record['gloss']),(self.term['footnote'],'Namaz','rugăciune'))
        self.assertEqual(record['path'],self.root/'translation'/'first.md')
        self.assertEqual(record['line'],2)
        self.assertTrue(re.fullmatch(k.stem_pattern('nefs poruncitor'),k.fold('Nefsului poruncitor')))
    def test_validator_adapter_missing_store_no_legacy_fallback(self):
        project=self.adapter_project(); project['terminology']='existing-legacy.md'; del project['knowledge']
        with self.assertRaises(k.KnowledgeError) as caught: k.load_project_terms(project,k.ROOT)
        self.assertEqual(caught.exception.code,'missing_knowledge_route')
        project['knowledge']=str(self.save('missingconfig.json',{'engine':'sqlite','path':str(self.root/'absent.sqlite')}))
        with self.assertRaises(k.KnowledgeError) as caught: k.load_project_terms(project,k.ROOT)
        self.assertEqual(caught.exception.code,'missing_store'); self.assertFalse((self.root/'absent.sqlite').exists())
    def test_validator_adapter_other_books_excluded(self):
        self.import_data()
        project=self.adapter_project(); project['id']='ro-other-book'
        self.assertEqual(k.load_project_terms(project,k.ROOT),{})
    def test_unit_scope_and_directory_source(self):
        self.import_data()
        (self.source.parent/'002-two.md').write_text('## text/two.xhtml\nNamaz.\n',encoding='utf-8')
        self.assertEqual([u['file'].name for u in self.store.case(self.case)['units']],['001-one.md'])
        whole=self.save('whole.json',{'project':str(self.project)})
        self.assertEqual([u['file'].name for u in self.store.case(whole)['units']],['001-one.md','002-two.md'])
        self.assertEqual(self.store.scan(whole)[-1]['line'],2)
        single=self.save('single.json',{'id':'ro-book','target_language':'ro','prepared_source':str(self.source),'translation':str(self.root/'translation')})
        with self.assertRaises(k.KnowledgeError) as caught: self.store.case(self.save('singlecase.json',{'project':str(single)}))
        self.assertEqual(caught.exception.code,'missing_source')
    def test_new_database_wal(self):
        with closing(self.store.read()) as c: self.assertEqual(c.execute('PRAGMA journal_mode').fetchone()[0],'wal')
    def test_search_index_mismatch_detected(self):
        p=self.root/'lugat.sql'; p.write_text("INSERT INTO db_lugat (id,indeks,kelime,kirpilmis,anlam) VALUES (1,'A','a','a','a');")
        self.import_data(); self.store.import_lugat(p)
        with self.store.write() as c: c.execute('DELETE FROM lugat_fts WHERE id=1')
        with self.assertRaises(k.KnowledgeError) as caught: self.store.check(self.case)
        self.assertEqual(caught.exception.code,'integrity')
    def test_first_source_and_order_verified(self):
        self.term['placements'][0]['source_line']=4
        self.import_data()
        with self.assertRaises(k.KnowledgeError) as caught: self.store.check(self.case)
        self.assertEqual(caught.exception.code,'first_use_form_missing')
    def test_earlier_inflected_or_derived_match_is_reported(self):
        self.source.write_text(self.source.read_text().replace('Nefs-i emmâre','Namazı. Nefs-i emmâre'))
        later=self.source.parent/'002-two.md'; later.write_text('## text/two.xhtml\nNamaz.\n',encoding='utf-8')
        self.term['placements'][0].update(source_path=str(later),source_line=2)
        self.import_data()
        warnings=self.store.check(self.save('whole.json',{'project':str(self.project)}))[0]['warnings']
        self.assertIn({'id':'term-namaz','issue':'possible_earlier_occurrence','at':str(self.source.relative_to(k.ROOT))+':2','text':'Namaz'},warnings)
        self.term['placements'][0].update(source_path=str(self.source),source_line=4)
        self.store=k.Knowledge(self.config); self.store.db.unlink(); self.store.init(); self.import_data()
        warnings=self.store.check(self.case)[0]['warnings']
        self.assertIn({'id':'term-namaz','issue':'possible_earlier_occurrence','at':str(self.source.relative_to(k.ROOT))+':2','text':'Namaz'},warnings)
    def test_untranslated_first_use_is_a_warning(self):
        self.import_data()
        self.assertIn('first_translation_untranslated',[x['issue'] for x in self.store.check(self.case)[0]['warnings']])
    def test_translation_first_note_and_exact_body(self):
        text='## one\nNamaz (rugăciune)[^term-namaz].\n\n[^term-namaz]: '+self.term['footnote'].replace('\n','\n    ')
        target=self.target(text)
        self.import_data(); self.assertEqual(self.store.check(self.case)[0]['warnings'],[])
        target.write_text(text.replace('[^term-namaz]:','[^term-namaz]: changed '))
        with self.assertRaises(k.KnowledgeError) as caught: self.store.check(self.case)
        self.assertEqual(caught.exception.code,'footnote_body_mismatch')
        target.write_text(text.replace('## one\n','## one\n\n'))
        with self.assertRaises(k.KnowledgeError) as caught: self.store.check(self.case)
        self.assertEqual(caught.exception.code,'first_note_reference_missing')
    def test_translation_path_escape_rejected(self):
        self.term['placements'][0]['translation_path']=str(self.root/'outside.md')
        self.import_data()
        with self.assertRaises(k.KnowledgeError) as caught: self.store.check(self.case)
        self.assertEqual(caught.exception.code,'translation_path_escape')
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
    def test_bak_cycles_missing_and_ambiguous(self):
        p=self.root/'refs.sql'
        p.write_text("INSERT INTO db_lugat (id,indeks,kelime,kirpilmis,anlam) VALUES (1,'A','A','a','Bak: B'),(2,'B','B','b','Bak: A'),(3,'C','C','c','Bak: missing'),(4,'D','D','d','Bak: B'),(5,'B','B','b','duplicate');")
        self.store.import_lugat(p)
        self.assertEqual(self.store.lugat_get(1)['references'][0]['issue'],'ambiguous_target')
        self.assertEqual(self.store.lugat_get(3)['references'][0]['issue'],'missing_target')
        with self.store.write() as c:
            c.execute('DELETE FROM lugat WHERE id=5'); c.execute('DELETE FROM lugat_fts WHERE id=5')
        self.assertEqual(self.store.lugat_get(1)['references'][-1]['issue'],'reference_cycle')
    def test_bad_dump_rollback(self):
        p=self.root/'bad.sql'; p.write_text("INSERT INTO db_lugat (id,indeks,kelime,kirpilmis,anlam) VALUES (1,'A','a',NULL,'a'),(2,'A','b',NULL,FUNCTION());")
        with self.assertRaises(k.KnowledgeError): self.store.import_lugat(p)
        with closing(self.store.read()) as c: self.assertEqual(c.execute('SELECT count(*) FROM lugat').fetchone()[0],0)
    def test_read_connection_cannot_write(self):
        self.import_data()
        with closing(self.store.read()) as c:
            with self.assertRaises(sqlite3.OperationalError): c.execute('DELETE FROM terms')
        self.assertEqual(self.store.term_get('term-namaz')['footnote'],self.term['footnote'])
    def test_import_is_atomic_and_needs_an_empty_table(self):
        bad=dict(self.term,id='term-other',placements=[dict(self.term['placements'][0],source_line=0)])
        self.terms.append(bad)
        with self.assertRaises(k.KnowledgeError): self.import_data()
        self.assertEqual(self.store.terms_list('ro'),[])
        self.terms.pop(); self.import_data()
        with self.assertRaises(k.KnowledgeError) as caught: self.import_data()
        self.assertEqual(caught.exception.code,'import_conflict')
    def test_put_term_keeps_placements_and_language(self):
        self.import_data()
        with self.store.write() as c: self.store.put_term(c,dict(self.term,translation='rugăciune rituală'))
        record=self.store.term_get('term-namaz')
        self.assertEqual(record['translation'],'rugăciune rituală'); self.assertEqual(len(record['placements']),1)
        with self.assertRaises(k.KnowledgeError) as caught:
            with self.store.write() as c: self.store.put_term(c,dict(self.term,language='fr'))
        self.assertEqual(caught.exception.code,'language_conflict')
        for bad in (dict(self.term,status='approved'),{f:v for f,v in self.term.items() if f!='reading_form'}):
            with self.assertRaises(k.KnowledgeError):
                with self.store.write() as c: self.store.put_term(c,bad)
    def test_placement_needs_known_term(self):
        with self.assertRaises(k.KnowledgeError) as caught: self.store.place(self.save('p.json',dict(self.term['placements'][0],term_id='missing')))
        self.assertEqual(caught.exception.code,'not_found')
    def test_jsonl_roundtrip(self):
        self.import_data(); out=self.root/'transfer.jsonl'; self.store.export_terms(out)
        other=k.Knowledge(self.save('config2.json',{'engine':'sqlite','path':str(self.root/'other.sqlite')})); other.init(); other.import_terms(out)
        second=self.root/'second.jsonl'; other.export_terms(second)
        self.assertEqual(out.read_bytes(),second.read_bytes())
        self.assertEqual(json.loads(out.read_text()),self.term)
    def test_scope_mismatch_and_path_boundary(self):
        with self.assertRaises(k.KnowledgeError) as caught: self.store.case(self.save('wrong.json',{'project':str(self.project),'units':'005-006'}))
        self.assertEqual(caught.exception.code,'missing_scope')
        with self.assertRaises(k.KnowledgeError): self.store.case(self.save('wrong.json',{'project':str(self.project),'units':'003-001'}))
        with self.assertRaises(k.KnowledgeError): k.path('/tmp/not-authorized.sqlite',write=True)
        with self.assertRaises(k.KnowledgeError): k.path('knowledge/../outside.sqlite',write=True)

if __name__=='__main__': unittest.main()
