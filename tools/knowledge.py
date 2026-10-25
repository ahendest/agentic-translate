#!/usr/bin/env python3
"""Shared SQLite store: source dictionary, approved terminology and book placements. Python standard library."""
import argparse
import contextlib
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
SCHEMA_VERSION = 6
LANGUAGE = r'[a-z]{2,3}(?:-[a-z0-9]+)*'
TERM_FIELDS = ('id','language','source_form','reading_form','translation','arabic','footnote','sense','note','approval','approved_at')
PLACEMENT_FIELDS = ('term_id','book_id','source_path','source_line','source_quote','translation_path','translation_line','first_expression')
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

def fold(text):
    """Case- and diacritic-insensitive form of text with the same length, so match offsets stay valid."""
    return ''.join((key(c) or c)[:1] for c in text)

def stem_pattern(term):
    """A term in any inflection: each folded word may take any ending."""
    return r'(?<![\w-])'+r'[\w-]*\s+'.join(map(re.escape,fold(term).split()))+r'[\w-]*'

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

def note_blocks(text):
    """Read Markdown footnotes; only indented continuation lines belong to a note."""
    lines=text.splitlines(keepends=True); offset=0; i=0
    while i<len(lines):
        match=re.fullmatch(r'\[\^([^]\n]+)\]:[ \t]*(.*)',lines[i].rstrip('\r\n'))
        if not match: offset+=len(lines[i]); i+=1; continue
        start=offset; identifier,first=match.groups(); body=[first]
        offset+=len(lines[i]); i+=1
        while i<len(lines):
            value=lines[i].rstrip('\r\n')
            if value.startswith('    ') or value.startswith('\t'):
                body.append(value[4:] if value.startswith('    ') else value[1:])
            elif not value.strip():
                j=i+1
                while j<len(lines) and not lines[j].strip(): j+=1
                if j>=len(lines) or not lines[j].startswith(('    ','\t')): break
                body.append('')
            else: break
            offset+=len(lines[i]); i+=1
        yield start,offset,identifier,'\n'.join(body)

def without_notes(text):
    position=0; parts=[]
    for start,end,identifier,body in note_blocks(text):
        parts.append(text[position:start]); position=end
    parts.append(text[position:]); return ''.join(parts)

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
    required(r,['id','language','source_form','reading_form','translation','footnote','sense','approval','approved_at'])
    unknown=set(r)-set(TERM_FIELDS)-{'placements'}
    if unknown: fail('invalid_record',f'Unknown term fields: {sorted(unknown)}',2)
    if not re.fullmatch(r'[\w-]+',r['id']): fail('invalid_record','Term ID must be usable as a footnote ID',2)
    if not re.fullmatch(LANGUAGE,str(r['language'])): fail('invalid_record','Invalid language code',2)

def validate_placement(p):
    required(p,['term_id','book_id','source_path','source_line','translation_path','translation_line'])
    unknown=set(p)-set(PLACEMENT_FIELDS)
    if unknown: fail('invalid_record',f'Unknown placement fields: {sorted(unknown)}',2)
    for field in ('source_line','translation_line'):
        if type(p[field]) is not int or p[field]<1: fail('invalid_record',f'{field} must be a positive integer',2)

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
            c.execute('PRAGMA foreign_keys=ON')
            c.execute('PRAGMA query_only=ON')
            self._version(c)
        except Exception:
            c.close()
            raise
        return c

    def _version(self,c):
        if c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] != str(SCHEMA_VERSION):
            fail('schema_version','Incompatible schema version',4)

    def init(self):
        self.db.parent.mkdir(parents=True,exist_ok=True)
        if self.db.exists():
            with contextlib.closing(self.read()) as c: self._version(c)
            return {'id':'store','unchanged':True}
        c=sqlite3.connect(self.db)
        c.execute('PRAGMA journal_mode=WAL')
        try: c.executescript(Path(__file__).with_name('knowledge_schema.sql').read_text()); c.commit()
        except Exception:
            c.close(); self.db.unlink(missing_ok=True); raise
        finally: c.close()
        return {'id':'store','schema_version':SCHEMA_VERSION}

    def integrity(self):
        with contextlib.closing(self.read()) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok': fail('integrity','SQLite integrity check failed',4)
            if list(c.execute('PRAGMA foreign_key_check')): fail('integrity','Foreign key check failed',4)
            counts={}
            base=[r[0] for r in c.execute('SELECT id FROM lugat')]
            if sorted(base)!=sorted(int(r[0]) for r in c.execute('SELECT id FROM lugat_fts')): fail('integrity','lugat search index mismatch',4)
            counts['lugat']=len(base)
            for table in ('terms','placements'): counts[table]=c.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
        return dict(integrity='ok',**counts)

    @contextlib.contextmanager
    def write(self,dry_run=False,export=True):
        if not self.db.exists(): fail('missing_store','Initialize database first',4)
        c=sqlite3.connect(self.db,timeout=10); changed=False
        try:
            c.row_factory=sqlite3.Row
            c.execute('PRAGMA foreign_keys=ON'); self._version(c)
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
        """Insert or replace one approved term; placements are kept."""
        r=dict(r); r.pop('placements',None); validate_term(r)
        old=c.execute('SELECT language FROM terms WHERE id=?',(r['id'],)).fetchone()
        if old and old[0]!=r['language']: fail('language_conflict',f"Term {r['id']} belongs to another language")
        c.execute('INSERT INTO terms VALUES ('+','.join('?'*len(TERM_FIELDS))+') ON CONFLICT(id) DO UPDATE SET '+
                  ','.join(f'{f}=excluded.{f}' for f in TERM_FIELDS[1:]),[r.get(f) for f in TERM_FIELDS])

    def put_placement(self,c,p):
        validate_placement(p)
        if not c.execute('SELECT 1 FROM terms WHERE id=?',(p['term_id'],)).fetchone(): fail('not_found',f"Term not found: {p['term_id']}")
        c.execute('INSERT INTO placements VALUES ('+','.join('?'*len(PLACEMENT_FIELDS))+') ON CONFLICT(term_id,book_id) DO UPDATE SET '+
                  ','.join(f'{f}=excluded.{f}' for f in PLACEMENT_FIELDS[2:]),[p.get(f) for f in PLACEMENT_FIELDS])

    def place(self,input_path,dry_run=False):
        p=load_json(input_path)
        with self.write(dry_run) as c:
            before=c.execute('SELECT * FROM placements WHERE term_id=? AND book_id=?',(p.get('term_id'),p.get('book_id'))).fetchone()
            self.put_placement(c,p)
        return {'id':p['term_id'],'dry_run':dry_run,'before':dict(before) if before else None,'after':p}

    def _record(self,c,ident,book=None):
        row=c.execute('SELECT * FROM terms WHERE id=?',(ident,)).fetchone()
        if not row: return None
        r={f:row[f] for f in TERM_FIELDS}
        r['placements']=[{f:p[f] for f in PLACEMENT_FIELDS[1:]} for p in c.execute('SELECT * FROM placements WHERE term_id=? AND (? IS NULL OR book_id=?) ORDER BY book_id',(ident,book,book))]
        return r

    def term_get(self,ident,language=None,book=None):
        with contextlib.closing(self.read()) as c: r=self._record(c,ident,book)
        if not r or (language and r['language']!=language): fail('not_found',f'Term not found: {ident}')
        return r

    def terms_list(self,language):
        if not re.fullmatch(LANGUAGE,language or ''): fail('invalid_input','Supply a language code',2)
        with contextlib.closing(self.read()) as c:
            return [self._record(c,row[0]) for row in c.execute('SELECT id FROM terms WHERE language=? ORDER BY id',(language,)).fetchall()]

    def find(self,query,language):
        """Terms of one language whose original is the query or its inflection; longest original first."""
        if not re.fullmatch(LANGUAGE,language or ''): fail('invalid_input','Supply a language code',2)
        needle=' '.join(fold(query).split())
        with contextlib.closing(self.read()) as c:
            rows=c.execute('SELECT id,source_form FROM terms WHERE language=?',(language,)).fetchall()
            hits=sorted((row for row in rows if needle and re.fullmatch(stem_pattern(row['source_form']),needle)),key=lambda row:(-len(row['source_form']),row['id']))
            return [dict(self._record(c,row['id']),match_type='exact' if fold(row['source_form'])==needle else 'inflection') for row in hits]

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
        with contextlib.closing(self.read()) as c:
            row=c.execute('SELECT id,indeks,kelime,kirpilmis,anlam FROM lugat WHERE id=?',(int(ident),)).fetchone()
        if not row: fail('not_found','Lugat record not found')
        return dict(row,references=self.lugat_references(int(ident)))

    def lugat_references(self,ident):
        """Follow exact Bak targets; expose missing, ambiguous and cyclic edges."""
        edges=[]; complete=set()
        with contextlib.closing(self.read()) as c:
            def visit(current,trail):
                if current in complete: return
                if len(complete)+len(trail)>=100:
                    edges.append({'id':current,'issue':'reference_budget_exceeded'}); return
                row=c.execute('SELECT anlam FROM lugat WHERE id=?',(current,)).fetchone()
                for match in re.finditer(r'\bBak\s*:\s*([^);.\n<]+)',row[0] or '',re.I):
                    query=match[1].strip()
                    targets=[r[0] for r in c.execute('SELECT id FROM lugat WHERE search_key=? ORDER BY id',(key(query),))]
                    edge={'from_id':current,'query':query,'target_ids':targets}
                    if not targets: edge['issue']='missing_target'
                    elif len(targets)>1: edge['issue']='ambiguous_target'
                    elif targets[0] in trail+[current]: edge['issue']='reference_cycle'
                    edges.append(edge)
                    if len(targets)==1 and 'issue' not in edge: visit(targets[0],trail+[current])
                complete.add(current)
            visit(ident,[])
        return edges

    def case(self,case_path):
        """A book scope: the project and an optional unit range (all units without one)."""
        case=load_json(case_path); required(case,['project'])
        manifest=load_json(case['project']); required(manifest,['id','target_language','prepared_source','translation'])
        language=manifest['target_language']
        if not re.fullmatch(LANGUAGE,str(language)): fail('invalid_scope','Project needs a valid target language code',2)
        files=unit_files(manifest)
        first,last=unit_range(case['units']) if case.get('units') else (1,float('inf'))
        units=[{'path':str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),'file':p,'text':p.read_text(encoding='utf-8')}
               for p in files if first<=unit_number(p)<=last]
        if not units: fail('missing_scope','No source units in the requested range',2)
        return {'book_id':book_id(manifest),'language':language,'manifest':manifest,'files':files,'units':units}

    def _terms(self,language):
        with contextlib.closing(self.read()) as c:
            return c.execute('SELECT id,source_form FROM terms WHERE language=? ORDER BY length(source_form) DESC,id',(language,)).fetchall()

    def scan(self,case):
        """Approved terms in the scope's source units, in any inflection, with their unit and line."""
        scope=self.case(case); result=[]
        terms=self._terms(scope['language'])
        for unit in scope['units']:
            occupied=[]; text=fold(unit['text'])
            for row in terms:
                for m in re.finditer(stem_pattern(row['source_form']),text):
                    if any(m.start()<b and m.end()>a for a,b in occupied): continue
                    occupied.append(m.span())
                    result.append({'id':row['id'],'text':unit['text'][m.start():m.end()],'path':unit['path'],'line':text.count('\n',0,m.start())+1})
        return sorted(result,key=lambda hit:(hit['path'],hit['line'],hit['id']))

    def _check_placement(self,r,placement,scope,issues):
        source=path(placement['source_path'])
        if source not in scope['files']: fail('first_use_missing',f"First-use source unit missing: {r['id']}")
        lines=source.read_text(encoding='utf-8').splitlines(); number=placement['source_line']
        if number>len(lines): fail('first_use_missing',f"First-use source line missing: {r['id']}")
        pattern=stem_pattern(r['source_form'])
        quote=placement.get('source_quote')
        if quote:
            if quote not in lines[number-1]: fail('first_use_quote_missing',f"First-use quotation absent: {r['id']}")
        elif not re.search(pattern,fold(lines[number-1])):
            fail('first_use_form_missing',f"No term occurrence or exact quotation on the first-use line: {r['id']}")
        # Stem matches include derived words, so an earlier match needs a human or translator decision.
        for unit in scope['files'][:scope['files'].index(source)+1]:
            body=unit.read_text(encoding='utf-8').splitlines()
            for n,line in enumerate(body[:number-1] if unit==source else body,1):
                found=re.search(pattern,fold(line))
                if found:
                    issues.append({'id':r['id'],'issue':'possible_earlier_occurrence','at':f"{unit.relative_to(ROOT) if unit.is_relative_to(ROOT) else unit}:{n}",'text':line[found.start():found.end()]})
                    break
        target_root=path(scope['manifest']['translation'])
        resolved=translation_file(placement['translation_path'],target_root)
        if not resolved.is_file():
            issues.append({'id':r['id'],'issue':'first_translation_untranslated','path':str(resolved)}); return
        target_text=resolved.read_text(encoding='utf-8')
        prose=without_notes(target_text).splitlines()
        target_lines=target_text.splitlines(); line=placement['translation_line']
        reference='[^'+r['id']+']'
        if line>len(target_lines) or reference not in target_lines[line-1] or target_lines[line-1].startswith(reference+':'):
            fail('first_note_reference_missing',f"First-use footnote call absent from the routed line: {r['id']}")
        if reference in '\n'.join(target_lines[:line-1]).replace(reference+':',''):
            fail('first_note_earlier_reference',f"Footnote call precedes the routed line: {r['id']}")
        if sum(l.count(reference) for l in prose)>1: fail('duplicate_footnote_call',f"Footnote called more than once: {r['id']}")
        blocks=[body for start,end,identifier,body in note_blocks(target_text) if identifier==r['id']]
        if len(blocks)>1: fail('duplicate_footnote_body',f"Duplicate book footnote definition: {r['id']}")
        if not blocks or blocks[0].strip()!=r['footnote'].strip(): fail('footnote_body_mismatch',f"Exact approved footnote differs: {r['id']}")
        if placement.get('first_expression') and placement['first_expression'] not in target_lines[line-1]:
            fail('first_expression_missing',f"Approved first-use expression absent: {r['id']}")

    def check(self,case):
        scope=self.case(case); issues=[]
        self.integrity()
        identifiers=dict.fromkeys(r['id'] for r in self.scan(case))
        with contextlib.closing(self.read()) as c:
            identifiers.update(dict.fromkeys(r[0] for r in c.execute('SELECT p.term_id FROM placements p JOIN terms t ON t.id=p.term_id WHERE p.book_id=? AND t.language=? ORDER BY p.term_id',(scope['book_id'],scope['language']))))
            records=[self._record(c,ident,scope['book_id']) for ident in identifiers]
        for r in records:
            validate_term(r)
            if not r['placements']:
                issues.append({'id':r['id'],'issue':'book_placement_missing','message':'The term occurs in scope but has no placement in this book yet.'}); continue
            self._check_placement(r,r['placements'][0],scope,issues)
        return [{'id':'check','book_id':scope['book_id'],'warnings':issues,'source_units':len(scope['units']),'limits':'First-use order covers inflections of the original; spelling variants and meaning require source review.'}]

    def export_terms(self,output):
        """Tracked text copy: one approved term per line with its placements."""
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
            for r in records:
                self.put_term(c,r)
                for p in r.get('placements',[]): self.put_placement(c,dict(p,term_id=r['id']))
        return {'id':'import','terms':len(records)}

def translation_file(value,target_root):
    """A placement's translation path: relative to the routed translation directory, never outside it."""
    raw=Path(value); target_root=target_root.resolve()
    if raw.is_absolute(): resolved=raw.resolve()
    elif raw.parts and raw.parts[0]=='translation': resolved=(target_root/Path(*raw.parts[1:])).resolve()
    else:
        direct=path(raw)
        resolved=direct if direct.is_relative_to(target_root) else (target_root/raw).resolve()
    if not resolved.is_relative_to(target_root): fail('translation_path_escape','First-use translation outside the routed translation directory',2)
    return resolved

def book_id(manifest):
    """The book identity shared by every language: an explicit book_id or the project ID without its language prefix."""
    return manifest.get('book_id') or manifest['id'].removeprefix(manifest['target_language']+'-')

def load_project_terms(project, repo_root=ROOT):
    """Read this book's placed terms for the project's validator.

    Missing routes/stores are errors. Terms with no placement in this book impose no
    validator obligations.
    """
    root=Path(repo_root).resolve()
    def resolve(value):
        p=Path(value)
        return p.resolve() if p.is_absolute() else (root/p).resolve()
    manifest=project if isinstance(project,dict) else json.loads(resolve(project).read_text(encoding='utf-8'))
    required(manifest,['id','target_language','translation'])
    if not manifest.get('knowledge'): fail('missing_knowledge_route','Project has no knowledge configuration route')
    store=Knowledge(resolve(manifest['knowledge']))
    book=book_id(manifest)
    translation_root=resolve(manifest['translation'])
    with contextlib.closing(store.read()) as c:
        ids=[r[0] for r in c.execute('SELECT t.id FROM terms t JOIN placements p ON p.term_id=t.id WHERE t.language=? AND p.book_id=? ORDER BY t.id',(manifest['target_language'],book))]
        records=[store._record(c,ident,book) for ident in ids]
    result={}
    for r in records:
        validate_term(r); placement=r['placements'][0]
        result[r['id']]={'original':r['source_form'],'reading':r['reading_form'],'gloss':r['translation'],'body':r['footnote'],
                         'path':translation_file(placement['translation_path'],translation_root),'line':placement['translation_line'],
                         'first_phrase':placement.get('first_expression'),'record_id':r['id']}
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--config',required=True)
    sub=parser.add_subparsers(dest='command',required=True)
    def paging(p,limit=10):
        p.add_argument('--cursor',type=int,default=0); p.add_argument('--limit',type=int,default=limit)
    sub.add_parser('init'); sub.add_parser('integrity')
    for name in ('import-lugat','import-terms','place'):
        p=sub.add_parser(name); p.add_argument('--input',required=True)
        if name=='place': p.add_argument('--dry-run',action='store_true')
    p=sub.add_parser('export-terms'); p.add_argument('--output',required=True)
    for name in ('scan','check'):
        p=sub.add_parser(name); p.add_argument('--case',required=True)
        if name=='scan': paging(p)
    terms=sub.add_parser('terms').add_subparsers(dest='action',required=True)
    a=terms.add_parser('list'); a.add_argument('--language',required=True); paging(a,20)
    a=terms.add_parser('get'); a.add_argument('--id',required=True); a.add_argument('--book')
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
        elif cmd=='place': result=k.place(args.input,args.dry_run)
        elif cmd=='check': result=k.check(args.case)
        elif cmd=='scan': result=k.scan(args.case)
        elif cmd=='terms':
            if args.action=='list': result=k.terms_list(args.language)
            elif args.action=='get': result=k.term_get(args.id,book=args.book)
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

if __name__=='__main__': sys.exit(main())
