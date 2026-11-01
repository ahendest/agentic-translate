#!/usr/bin/env python3
"""Shared SQLite store: source dictionary and approved terminology. Python standard library."""
import argparse
import contextlib
import functools
import hashlib
import os
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITE_ROOTS = (ROOT / 'knowledge',)
SCHEMA_VERSION = 9
LANGUAGE = r'[a-z]{2,3}(?:-[a-z0-9]+)*'
TERM_FIELDS = ('id','language','source_form','reading_form','translation','arabic','footnote','later_use','sense','note','approval','approved_at')
UNIT = re.compile(r'(\d+)-')

class KnowledgeError(Exception):
    def __init__(self, code, message, exit_code=3):
        super().__init__(message)
        self.code, self.exit_code = code, exit_code

def fail(code, message, exit_code=3):
    raise KnowledgeError(code, message, exit_code)

def path(value, write=False):
    p = Path(value)
    p = (ROOT / p).resolve() if not p.is_absolute() else p.resolve()
    if write and not any(p.is_relative_to(root.resolve()) for root in WRITE_ROOTS):
        fail('outside_authorized_store', f'Write path must stay in knowledge/: {p}', 2)
    return p

def load_json(value):
    return json.loads(path(value).read_text(encoding='utf-8'))

def digest(p):
    return hashlib.sha256(path(p).read_bytes()).hexdigest()

def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def key(value):
    text = (value or '').casefold().replace('ı','i')
    return ''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c))

APOSTROPHES = str.maketrans('’‘ʼ', "'''")

def fold(text):
    """Case-, diacritic- and apostrophe-insensitive form of text with the same length, so match offsets stay valid."""
    return ''.join((key(c) or c)[:1] for c in text.translate(APOSTROPHES))

@functools.cache
def marks():
    """Every nonspacing mark (vowel signs such as Arabic harakat, accents) as regex class ranges."""
    codes=[i for i in range(sys.maxunicode+1) if unicodedata.category(chr(i))=='Mn']
    ranges=[]
    for i in codes:
        if ranges and ranges[-1][1]==i-1: ranges[-1][1]=i
        else: ranges.append([i,i])
    return ''.join(chr(a) if a==b else chr(a)+'-'+chr(b) for a,b in ranges)

def bare(text):
    """Folded text without nonspacing marks, for comparing forms (not for match offsets)."""
    return ''.join(c for c in fold(text) if unicodedata.category(c)!='Mn')

def stem_pattern(term):
    """A term in any inflection: each folded word may take any ending, and vowel signs are optional."""
    m=marks()
    words=[''.join(re.escape(c)+f'[{m}]*' for c in w) for w in bare(term).split()]
    return r'(?<![\w-])'+rf'[\w{m}-]*\s+'.join(words)+rf'[\w{m}-]*'

def unit_files(manifest):
    """The prepared source units of a book in book order: the nonempty Markdown files, by name."""
    source=path(manifest['prepared_source'])
    if not source.is_dir(): fail('missing_source','Prepared source must be a directory of unit files',2)
    return [p for p in sorted(source.glob('*.md')) if p.read_text(encoding='utf-8').strip()]

def unit_range(value):
    """A unit scope NNN-NNN by the number that starts each unit filename."""
    m=re.fullmatch(r'(\d+)-(\d+)',str(value or ''))
    if not m or not 1<=int(m[1])<=int(m[2]): fail('invalid_scope','Use an ordered unit range, e.g. 001-010',2)
    return int(m[1]),int(m[2])

def unit_number(p):
    m=UNIT.match(Path(p).name)
    if not m: fail('invalid_scope',f'Unit filename must start with its number: {Path(p).name}',2)
    return int(m[1])

def fts_query(text):
    # Plain input is data, never FTS syntax. Match all input words.
    return ' AND '.join('"' + word.replace('"','""') + '"' for word in re.findall(r'\w+',key(text)))

def parse_lugat(text):
    """Parse only INSERT db_lugat VALUES; do not execute any dump statements."""
    starts = list(re.finditer(r'INSERT\s+INTO\s+`?db_lugat`?\s*\(([^)]+)\)\s*VALUES\s*',text,re.I))
    if not starts:
        fail('invalid_dump','No db_lugat INSERT statements found',2)
    scalar = re.compile(r'(NULL|[+-]?\d+)\b', re.I)
    escape = {'0':'\0','n':'\n','r':'\r','t':'\t','b':'\b','Z':'\x1a',"'":"'",'"':'"','\\':'\\'}
    for start in starts:
        columns = [v.strip().strip('`') for v in start.group(1).split(',')]
        if columns != ['id','indeks','kelime','kirpilmis','anlam']:
            fail('invalid_dump','Unexpected db_lugat columns',2)
        pos = start.end()
        def space():
            nonlocal pos
            while pos < len(text) and text[pos].isspace(): pos += 1
        def value():
            nonlocal pos
            space()
            if pos < len(text) and text[pos] == "'":
                pos += 1
                result = []
                while pos < len(text):
                    c = text[pos]; pos += 1
                    if c == '\\':
                        if pos >= len(text): fail('invalid_dump','Truncated escape',2)
                        c = text[pos]; pos += 1
                        result.append(escape.get(c,c))
                    elif c == "'":
                        if pos < len(text) and text[pos] == "'": result.append("'"); pos += 1
                        else: return ''.join(result)
                    else: result.append(c)
                fail('invalid_dump','Unclosed SQL string',2)
            match = scalar.match(text,pos)
            if not match: fail('invalid_dump',f'Invalid value at offset {pos}',2)
            pos += len(match.group())
            return None if match.group().upper() == 'NULL' else int(match.group())
        while True:
            space()
            if pos >= len(text) or text[pos] != '(': fail('invalid_dump','Expected row',2)
            pos += 1
            row=[]
            for i in range(5):
                row.append(value()); space()
                expected = ')' if i == 4 else ','
                if pos >= len(text) or text[pos] != expected: fail('invalid_dump','Invalid row delimiter',2)
                pos += 1
            if not isinstance(row[0],int) or any(v is not None and not isinstance(v,str) for v in row[1:]):
                fail('invalid_dump','Invalid lugat field type',2)
            yield {'id':row[0],'indeks':row[1],'kelime':row[2],'kirpilmis':row[3],'anlam':row[4]}
            space()
            if pos < len(text) and text[pos] == ';': break
            if pos >= len(text) or text[pos] != ',': fail('invalid_dump','Missing INSERT terminator',2)
            pos += 1

def required(record, fields):
    for field in fields:
        if field not in record or record[field] is None or record[field] == '':
            fail('missing_data',f'Missing field: {field}')

def validate_term(r):
    required(r,['id','language','source_form','sense','approval','approved_at'])
    # A missing reading form, translation or footnote is a decision, not an error.
    for field in ('reading_form','translation','arabic','footnote','note'):
        if r.get(field) is not None and not (isinstance(r[field],str) and r[field].strip()):
            fail('invalid_record',f'{field} must be text or null',2)
    if not (r.get('reading_form') or r.get('translation') or r.get('note')):
        fail('invalid_record','A term needs a reading form, a translation or a note',2)
    if r.get('footnote') and not r.get('reading_form'):
        fail('invalid_record','A footnote is called after the retained term; it needs a reading form',2)
    if r.get('later_use','equivalent') not in ('equivalent','original'):
        fail('invalid_record','later_use must be equivalent or original',2)
    unknown=set(r)-set(TERM_FIELDS)
    if unknown: fail('invalid_record',f'Unknown term fields: {sorted(unknown)}',2)
    if not re.fullmatch(r'[\w-]+',r['id']): fail('invalid_record','Term ID must be usable as a footnote ID',2)
    if not re.fullmatch(LANGUAGE,str(r['language'])): fail('invalid_record','Invalid language code',2)

class Knowledge:
    def __init__(self, config_path):
        self.config = dict(config_path) if isinstance(config_path,dict) else load_json(config_path)
        if self.config.get('engine') != 'sqlite': fail('unsupported_engine','Shared knowledge supports SQLite only',2)
        required(self.config,['path'])
        self.db = path(self.config['path'],write=True)

    def read(self):
        if not self.db.is_file(): fail('missing_store','Knowledge database does not exist',4)
        c=sqlite3.connect(self.db.as_uri()+'?mode=ro',uri=True)
        try:
            c.row_factory=sqlite3.Row
            c.execute('PRAGMA query_only=ON')
            self._version(c)
        except Exception:
            c.close()
            raise
        return c

    def _version(self,c):
        if c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] != str(SCHEMA_VERSION):
            fail('schema_version','Incompatible schema version: rebuild the store from knowledge/knowledge.jsonl (knowledge/overview.md#rebuild)',4)

    def init(self):
        self.db.parent.mkdir(parents=True,exist_ok=True)
        if self.db.exists():
            with contextlib.closing(self.read()) as c: self._version(c)
            return {'id':'store','unchanged':True}
        c=sqlite3.connect(self.db)
        c.execute('PRAGMA journal_mode=WAL')
        try: c.executescript(Path(__file__).with_name('knowledge_schema.sql').read_text(encoding='utf-8')); c.commit()
        except Exception:
            c.close(); self.db.unlink(missing_ok=True); raise
        finally: c.close()
        return {'id':'store','schema_version':SCHEMA_VERSION}

    def integrity(self):
        with contextlib.closing(self.read()) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok': fail('integrity','SQLite integrity check failed',4)
            base=[r[0] for r in c.execute('SELECT id FROM lugat')]
            if sorted(base)!=sorted(int(r[0]) for r in c.execute('SELECT id FROM lugat_fts')): fail('integrity','lugat search index mismatch',4)
            terms=c.execute('SELECT count(*) FROM terms').fetchone()[0]
        return {'integrity':'ok','lugat':len(base),'terms':terms}

    @contextlib.contextmanager
    def write(self,dry_run=False,export=True):
        if not self.db.exists(): fail('missing_store','Initialize database first',4)
        c=sqlite3.connect(self.db,timeout=10); changed=False
        try:
            c.row_factory=sqlite3.Row
            self._version(c)
            c.execute('BEGIN IMMEDIATE')
            yield c
            if dry_run: c.rollback()
            else:
                changed=bool(c.total_changes)
                c.commit()
        except Exception: c.rollback(); raise
        finally: c.close()
        if changed and export and self.config.get('export'):
            self._refresh_export(self.config['export'])

    def _refresh_export(self,output):
        """Keep the text copy current; never replace a populated export with an empty store's view.

        The SQLite write lock is held during the export, so concurrent writers export in commit
        order and each export reads the latest committed state.
        """
        target=path(output,write=True)
        lock=sqlite3.connect(self.db,timeout=30)
        try:
            lock.execute('BEGIN IMMEDIATE')
            with contextlib.closing(self.read()) as c:
                populated=c.execute('SELECT 1 FROM terms LIMIT 1').fetchone()
            if not populated and target.is_file() and target.read_text(encoding='utf-8').strip():
                return
            self.export_terms(output)
        finally:
            lock.rollback(); lock.close()

    def put_term(self,c,r):
        """Insert or replace one approved term."""
        r=dict(r,later_use=r.get('later_use') or 'equivalent'); validate_term(r)
        old=c.execute('SELECT language FROM terms WHERE id=?',(r['id'],)).fetchone()
        if old and old[0]!=r['language']: fail('language_conflict',f"Term {r['id']} belongs to another language")
        c.execute('INSERT INTO terms VALUES ('+','.join('?'*len(TERM_FIELDS))+') ON CONFLICT(id) DO UPDATE SET '+
                  ','.join(f'{f}=excluded.{f}' for f in TERM_FIELDS[1:]),[r.get(f) for f in TERM_FIELDS])

    def _record(self,c,ident):
        row=c.execute('SELECT * FROM terms WHERE id=?',(ident,)).fetchone()
        return {f:row[f] for f in TERM_FIELDS} if row else None

    def term_get(self,ident):
        with contextlib.closing(self.read()) as c: r=self._record(c,ident)
        if not r: fail('not_found',f'Term not found: {ident}')
        return r

    def terms_list(self,language):
        if not re.fullmatch(LANGUAGE,language or ''): fail('invalid_input','Supply a language code',2)
        with contextlib.closing(self.read()) as c:
            return [self._record(c,row[0]) for row in c.execute('SELECT id FROM terms WHERE language=? ORDER BY id',(language,)).fetchall()]

    def find(self,query,language):
        """Terms of one language whose original is the query (exact), a word prefix of it (inflection) or inside it
        (contained, as in a compound); longest first. Vowel signs do not change the form.

        Only an exact hit is reused: a prefix or a part can be another concept, so the others are candidates."""
        if not re.fullmatch(LANGUAGE,language or ''): fail('invalid_input','Supply a language code',2)
        needle=' '.join(fold(query).split())
        def kind(form):
            pattern=stem_pattern(form)
            return 'exact' if bare(form).split()==bare(query).split() else 'inflection' if re.fullmatch(pattern,needle) else 'contained' if re.search(pattern,needle) else None
        with contextlib.closing(self.read()) as c:
            rows=c.execute('SELECT id,source_form FROM terms WHERE language=?',(language,)).fetchall()
            hits=sorted(((row,kind(row['source_form'])) for row in rows if needle),key=lambda hit:(-len(hit[0]['source_form']),hit[0]['id']))
            return [dict(self._record(c,row['id']),match_type=match) for row,match in hits if match]

    def import_lugat(self,input_path):
        p=path(input_path); sha=digest(p); count=0
        with self.write(export=False) as c:
            old=c.execute("SELECT value FROM meta WHERE key='lugat_sha256'").fetchone()
            if old:
                if old[0]==sha: return {'id':'lugat','unchanged':True,'sha256':sha}
                fail('import_conflict','Lugat dump changed; existing originals are protected')
            for r in parse_lugat(p.read_text(encoding='utf-8')):
                c.execute('INSERT INTO lugat VALUES (?,?,?,?,?,?)',(r['id'],r['indeks'],r['kelime'],r['kirpilmis'],r['anlam'],key(r['kelime'])))
                c.execute('INSERT INTO lugat_fts VALUES (?,?)',(r['id'],key(' '.join(r[f] or '' for f in ('kelime','kirpilmis','anlam')))))
                count+=1
            c.execute("INSERT INTO meta VALUES ('lugat_sha256',?),('lugat_count',?)",(sha,str(count)))
        return {'id':'lugat','count':count,'sha256':sha}

    def lugat_search(self,query):
        with contextlib.closing(self.read()) as c:
            rows=c.execute('SELECT id,kelime,indeks FROM lugat WHERE search_key=? ORDER BY id',(key(query),)).fetchall()
            match='exact_form'
            if not rows:
                q=fts_query(query)
                rows=c.execute('SELECT l.id,l.kelime,l.indeks FROM lugat_fts f JOIN lugat l ON l.id=f.id WHERE lugat_fts MATCH ? ORDER BY rank',(q,)).fetchall() if q else []
                match='lexical'
            return [dict(r,match_type=match) for r in rows]

    def lugat_get(self,ident):
        """One dictionary entry with the entries that its "Bak:" references name."""
        with contextlib.closing(self.read()) as c:
            row=c.execute('SELECT id,indeks,kelime,kirpilmis,anlam FROM lugat WHERE id=?',(int(ident),)).fetchone()
            if not row: fail('not_found','Lugat record not found')
            references=[{'query':m[1].strip(),'target_ids':[r[0] for r in c.execute('SELECT id FROM lugat WHERE search_key=? ORDER BY id',(key(m[1].strip()),))]}
                        for m in re.finditer(r'\bBak\s*:\s*([^);.\n<]+)',row['anlam'] or '',re.I)]
        return dict(row,references=references)

    def scan(self,project,units=None):
        """Approved terms in a book's source units, in any inflection, with their unit and line; all units without a range."""
        manifest=project if isinstance(project,dict) else load_json(project); required(manifest,['target_language','prepared_source'])
        first,last=unit_range(units) if units else (1,float('inf'))
        files=[p for p in unit_files(manifest) if first<=unit_number(p)<=last]
        if not files: fail('missing_scope','No source units in the requested range',2)
        with contextlib.closing(self.read()) as c:
            terms=c.execute('SELECT id,source_form FROM terms WHERE language=? ORDER BY length(source_form) DESC,id',(manifest['target_language'],)).fetchall()
        result=[]
        for p in files:
            original=p.read_text(encoding='utf-8'); text=fold(original); occupied=[]
            for row in terms:
                for m in re.finditer(stem_pattern(row['source_form']),text):
                    if any(m.start()<b and m.end()>a for a,b in occupied): continue
                    occupied.append(m.span())
                    result.append({'id':row['id'],'term':row['source_form'],'text':original[m.start():m.end()],
                                   'path':p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p),'line':text.count('\n',0,m.start())+1})
        return sorted(result,key=lambda hit:(hit['path'],hit['line'],hit['id']))

    def export_terms(self,output):
        """Tracked text copy: one approved term per line."""
        p=path(output,write=True); p.parent.mkdir(parents=True,exist_ok=True)
        with contextlib.closing(self.read()) as c:
            lines=[dump(self._record(c,row[0])) for row in c.execute('SELECT id FROM terms ORDER BY id').fetchall()]
        temporary=p.with_name(p.name+'.tmp')
        temporary.write_text(''.join(line+'\n' for line in lines),encoding='utf-8')
        os.replace(temporary,p)
        return {'id':'export','terms':len(lines),'sha256':digest(p)}

    def import_terms(self,input_path):
        records=[json.loads(line) for line in path(input_path).read_text(encoding='utf-8').splitlines() if line.strip()]
        with self.write() as c:
            if c.execute('SELECT 1 FROM terms LIMIT 1').fetchone(): fail('import_conflict','Import requires an empty terms table')
            for r in records: self.put_term(c,r)
        return {'id':'import','terms':len(records)}

def load_project_terms(project, repo_root=ROOT):
    """The approved terms of the project's target language, for its validator. A missing route or store is an error."""
    root=Path(repo_root).resolve()
    def resolve(value):
        p=Path(value)
        return p.resolve() if p.is_absolute() else (root/p).resolve()
    manifest=project if isinstance(project,dict) else json.loads(resolve(project).read_text(encoding='utf-8'))
    required(manifest,['target_language'])
    if not manifest.get('knowledge'): fail('missing_knowledge_route','Project has no knowledge configuration route')
    store=Knowledge(resolve(manifest['knowledge']))
    return {r['id']:{'reading':r['reading_form'],'gloss':r['translation'],'body':r['footnote'],'later':r['later_use']}
            for r in store.terms_list(manifest['target_language'])}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--config',required=True)
    sub=parser.add_subparsers(dest='command',required=True)
    def paging(p,limit=10):
        p.add_argument('--cursor',type=int,default=0); p.add_argument('--limit',type=int,default=limit)
    sub.add_parser('init'); sub.add_parser('integrity')
    for name in ('import-lugat','import-terms'):
        sub.add_parser(name).add_argument('--input',required=True)
    sub.add_parser('export-terms').add_argument('--output',required=True)
    p=sub.add_parser('scan'); p.add_argument('--project',required=True); p.add_argument('--units'); paging(p)
    terms=sub.add_parser('terms').add_subparsers(dest='action',required=True)
    a=terms.add_parser('list'); a.add_argument('--language',required=True); paging(a,20)
    a=terms.add_parser('get'); a.add_argument('--id',required=True)
    a=terms.add_parser('find'); a.add_argument('--query',required=True); a.add_argument('--language',required=True); paging(a)
    lugat=sub.add_parser('lugat').add_subparsers(dest='action',required=True)
    a=lugat.add_parser('search'); a.add_argument('--query',required=True); paging(a)
    a=lugat.add_parser('get'); a.add_argument('--id',type=int,required=True)
    args=parser.parse_args(argv)
    try:
        k=Knowledge(args.config); cmd=args.command
        if cmd=='init': result=k.init()
        elif cmd=='integrity': result=k.integrity()
        elif cmd=='import-lugat': result=k.import_lugat(args.input)
        elif cmd=='import-terms': result=k.import_terms(args.input)
        elif cmd=='export-terms': result=k.export_terms(args.output)
        elif cmd=='scan': result=k.scan(args.project,args.units)
        elif cmd=='terms':
            if args.action=='list': result=k.terms_list(args.language)
            elif args.action=='get': result=k.term_get(args.id)
            else: result=k.find(args.query,args.language)
        else: result=k.lugat_get(args.id) if args.action=='get' else k.lugat_search(args.query)
        items=result if isinstance(result,list) else [result]; cursor=None; warnings=[]
        if hasattr(args,'limit'):
            if args.limit<1 or args.limit>20 or args.cursor<0: fail('invalid_input','limit must be 1..20; cursor must be nonnegative',2)
            cursor=args.cursor+args.limit if len(items)>args.cursor+args.limit else None
            items=items[args.cursor:args.cursor+args.limit]
        if len(dump(items).encode())>64000: warnings.append('Large full records returned intact; narrow the query if necessary.')
        print(dump({'ok':True,'items':items,'next_cursor':cursor,'warnings':warnings})); return 0
    except KnowledgeError as e:
        print(dump({'ok':False,'items':[],'next_cursor':None,'warnings':[],'error':{'code':e.code,'message':str(e)}})); return e.exit_code
    except (ValueError,KeyError,TypeError) as e:
        print(dump({'ok':False,'items':[],'next_cursor':None,'warnings':[],'error':{'code':'invalid_input','message':str(e)}})); return 2
    except sqlite3.IntegrityError as e:
        print(dump({'ok':False,'items':[],'next_cursor':None,'warnings':[],'error':{'code':'constraint_conflict','message':str(e)}})); return 3
    except (OSError,sqlite3.Error) as e:
        print(dump({'ok':False,'items':[],'next_cursor':None,'warnings':[],'error':{'code':'integrity_or_connection','message':str(e)}})); return 4

if __name__=='__main__': sys.stdout.reconfigure(encoding='utf-8'); sys.exit(main())
