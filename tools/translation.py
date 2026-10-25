#!/usr/bin/env python3
"""Bounded project preparation, source units and terminology requests."""
import argparse
import contextlib
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from pathlib import Path

import knowledge

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local(value):
    path = (ROOT / value).resolve()
    require(path.is_relative_to(ROOT), 'Path must stay inside the repository')
    return path


def relative(path):
    return str(path.resolve().relative_to(ROOT))


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def slug(value):
    text = unicodedata.normalize('NFKD', value.replace('ı', 'i'))
    text = text.encode('ascii', 'ignore').decode().lower()
    result = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    require(result, 'Cannot derive a book ID from the filename; supply --book')
    return result


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project(value):
    path = local(value)
    require(path.name == 'project.json' and path.is_file() and path.is_relative_to(ROOT / 'translations'), 'Unknown project')
    data = load(path)
    require(data.get('target_language') and data.get('prepared_source'), 'Incomplete project routes')
    return path, data


def units(data):
    """Each prepared segment file is one unit, in name order."""
    if not local(data['prepared_source']).is_dir():
        return []
    return [{'id': path.stem, 'path': relative(path), 'start_line': 1,
             'end_line': len(path.read_text(encoding='utf-8').splitlines())}
            for path in knowledge.unit_files(dict(data, prepared_source=str(local(data['prepared_source']))))]


def prepare(source, source_language, target_language, book=None, project_path=None, create=False):
    for language in (source_language, target_language):
        require(re.fullmatch(r'[a-z]{2,3}(?:-[a-z0-9]+)*', language), 'Use language codes such as tr, ro, fr or ur')
    source = (ROOT / source).resolve()
    require(source.is_file(), 'The book path must identify an existing file')
    require(source.suffix.lower() == '.epub', 'The source must be an EPUB file')
    book_id = slug(book or source.stem)
    if project_path:
        explicit = local(project_path)
        require(explicit.name == 'project.json' and explicit.parent.parent == ROOT / 'translations' / target_language,
                'Project must be translations/<target-language>/<book-id>/project.json')
    import_from = None
    if not source.is_relative_to(ROOT):
        require(create, 'Use --create to import an external source without changing its contents')
        destination = local(Path('Book-original-sources/imported') / source.name)
        require(not destination.exists() or fingerprint(source) == fingerprint(destination), 'Imported filename already contains a different source')
        import_from = source
        source = destination.resolve()
    candidates = []
    if project_path:
        candidates = [local(project_path)]
    else:
        named = local(Path('translations') / target_language / book_id / 'project.json')
        if named.is_file():
            candidates = [named]
        else:
            for path in sorted((ROOT / 'translations' / target_language).glob('*/project.json')):
                data = load(path)
                if any(local(item['path']) == source for item in data.get('sources', []) if item.get('role') == 'primary'):
                    candidates.append(path)
    require(len(candidates) <= 1, 'Multiple projects use this source; supply --project: ' + ', '.join(relative(p) for p in candidates))
    path = candidates[0] if candidates else local(Path('translations') / target_language / book_id / 'project.json')
    is_new = not path.exists()
    if is_new:
        if not create:
            return {'state': 'setup_required', 'project': relative(path), 'next': 'Repeat prepare with --create'}
        # Reuse shared preparation only when another manifest binds it to this source.
        prepared = local(Path('sources') / book_id / 'segments')
        if prepared.exists() and any(prepared.iterdir()):
            bound = []
            for manifest in (ROOT / 'translations').glob('*/*/project.json'):
                other = load(manifest)
                if other.get('prepared_source') and local(other['prepared_source']) == prepared:
                    bound.extend(local(s['path']) for s in other.get('sources', []) if s.get('role') == 'primary')
            require(bound and all(p == source for p in bound), 'Shared source ID collision; supply a distinct --book')
        data = {'id': target_language + '-' + path.parent.name, 'source_language': source_language,
                'target_language': target_language,
                'sources': [{'path': relative(source), 'role': 'primary'}],
                'prepared_source': 'sources/' + book_id + '/segments',
                'translation': relative(path.parent / 'translation')}
        data['knowledge'] = 'knowledge/config.json'
        data['validator'] = ['python3', '-B', 'tools/validate_translation.py', '--project', relative(path), '--units', 'UNITS']
    else:
        path, data = project(relative(path))
        require(path.is_relative_to(ROOT / 'translations' / target_language), 'Project is outside the requested language')
        require(data.get('source_language') == source_language and data['target_language'] == target_language, 'Language mismatch')
        require(any(local(item['path']) == source for item in data.get('sources', []) if item.get('role') == 'primary'), 'Requested source differs from project authority; resolve it before preparation')
    if import_from is not None and not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        with import_from.open('rb') as incoming, source.open('xb') as destination:
            shutil.copyfileobj(incoming, destination)
    if is_new:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        local(data['prepared_source']).mkdir(parents=True, exist_ok=True)
    rows = units(data)
    command = ['python3', '-B', 'tools/prepare_epub.py', '--epub', relative(source),
               '--book', Path(data['prepared_source']).parent.name]
    return {'state': 'available' if rows else 'preparation_required', 'project': relative(path),
            'source': relative(source), 'prepared_source': data['prepared_source'],
            'translation': data.get('translation'), 'unit_count': len(rows),
            'needs': [] if rows else ['prepared_source'], 'preparation_command': None if rows else command}


def term_request(project_path, term, location):
    _, data = project(project_path)
    require(data.get('knowledge'), 'No terminology route for this project')
    filename, separator, number = location.rpartition(':')
    require(separator and number.isdecimal(), 'Use a source-segment.md:line location')
    path = local(filename)
    prepared = local(data['prepared_source'])
    require(path.is_file() and (path == prepared or path.is_relative_to(prepared)), 'Term location is outside the prepared source')
    lines = path.read_text(encoding='utf-8').splitlines()
    line = int(number)
    require(1 <= line <= len(lines) and lines[line - 1].strip(), 'Location must identify a nonempty source line')
    start, end = line - 1, line
    while start > 0 and lines[start - 1].strip() and not lines[start - 1].startswith('#'):
        start -= 1
    while end < len(lines) and lines[end].strip() and not lines[end].startswith('#'):
        end += 1
    require(term.strip(), 'Term must not be empty')
    require(re.search(knowledge.stem_pattern(term), knowledge.fold('\n'.join(lines[start:end]))),
            'Term is absent from the located paragraph')
    store = knowledge.Knowledge(local(data['knowledge']))
    found = store.find(term, data['target_language'])
    request_text = term + ' (' + relative(path) + ':' + str(line) + ')'
    if not found:
        return {'state': 'request', 'text': request_text}
    book_id = knowledge.book_id(data)
    for record in found:
        record['placements'] = [p for p in record['placements'] if p['book_id'] == book_id]
    return {'state': 'approved', 'records': found}


def known_terms(data, text, start_line):
    """Expose the first source occurrence of each approved term, in any inflection, without a whole glossary."""
    require(data.get('knowledge'), 'No terminology route for this project')
    store = knowledge.Knowledge(local(data['knowledge']))
    folded = knowledge.fold(text)
    found, occupied = {}, []
    with contextlib.closing(store.read()) as connection:
        rows = connection.execute('SELECT id,source_form FROM terms WHERE language=? ORDER BY length(source_form) DESC,id', (data['target_language'],)).fetchall()
    for row in rows:
        for match in re.finditer(knowledge.stem_pattern(row['source_form']), folded):
            if any(match.start() < end and match.end() > start for start, end in occupied):
                continue
            occupied.append(match.span())
            found.setdefault(row['id'], {'id': row['id'], 'term': row['source_form'], 'text': text[match.start():match.end()],
                                         'line': start_line + folded[:match.start()].count('\n')})
    return sorted(found.values(), key=lambda hit: (hit['line'], hit['id']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare')
    p.add_argument('--source', required=True)
    p.add_argument('--source-language', required=True)
    p.add_argument('--target-language', required=True)
    p.add_argument('--book')
    p.add_argument('--project')
    p.add_argument('--create', action='store_true')
    p = commands.add_parser('segments')
    p.add_argument('--project', required=True)
    p.add_argument('--cursor', type=int, default=0)
    p.add_argument('--limit', type=int, default=10)
    p = commands.add_parser('read')
    p.add_argument('--project', required=True)
    p.add_argument('--unit', required=True)
    p = commands.add_parser('term-request')
    p.add_argument('--project', required=True)
    p.add_argument('--term', required=True)
    p.add_argument('--at', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            result = prepare(args.source, args.source_language, args.target_language, args.book, args.project, args.create)
        elif args.command in ('segments', 'read'):
            _, data = project(args.project)
            rows = units(data)
            if args.command == 'segments':
                require(args.cursor >= 0 and 1 <= args.limit <= 20, 'Use nonnegative cursor and limit 1–20')
                stop = args.cursor + args.limit
                result = {'items': rows[args.cursor:stop], 'total': len(rows), 'next_cursor': stop if stop < len(rows) else None}
            else:
                row = next((row for row in rows if row['id'] == args.unit), None)
                require(row, 'Unknown source unit')
                lines = local(row['path']).read_text(encoding='utf-8').splitlines()
                text = '\n'.join(lines[row['start_line'] - 1:row['end_line']])
                result = {'source': row, 'text': text, 'known_terms': known_terms(data, text, row['start_line'])}
        else:
            result = term_request(args.project, args.term, args.at)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, knowledge.KnowledgeError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
