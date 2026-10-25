#!/usr/bin/env python3
"""Convert an EPUB into located Markdown units: one file per spine document, split at headings when long."""
import argparse
import hashlib
import html.parser
import json
import posixpath
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LONG = 24000  # Markdown characters; a longer document is split at its headings
SKIPPED_GUIDE = {'cover', 'toc', 'copyright-page'}
VOID = {'area', 'base', 'br', 'col', 'hr', 'img', 'input', 'link', 'meta', 'source', 'wbr'}
BLOCK = {'address', 'article', 'aside', 'blockquote', 'body', 'dd', 'div', 'dl', 'dt', 'figcaption', 'figure',
         'footer', 'header', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section', 'table', 'tr', 'ul'}
HEADING = {f'h{n}': n for n in range(1, 7)}
SILENT = {'head', 'script', 'style', 'title'}


class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []


class TreeBuilder(html.parser.HTMLParser):
    """A minimal element tree; text is kept exactly as written."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node('#root', {})

    def handle_starttag(self, tag, attrs):
        node = Node(tag, [(k, v or '') for k, v in attrs], self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, [(k, v or '') for k, v in attrs], self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def parse(text):
    builder = TreeBuilder()
    builder.feed(text)
    builder.close()
    return builder.root


def walk(node):
    yield node
    for child in node.children:
        if isinstance(child, Node):
            yield from walk(child)


def slug(value):
    text = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-') or 'document'


class Book:
    """Reads the OPF package: metadata, manifest, spine order and the documents the EPUB marks as auxiliary."""

    def __init__(self, epub):
        self.zip = zipfile.ZipFile(epub)
        container = parse(self.read('META-INF/container.xml'))
        rootfile = next((n for n in walk(container) if n.tag == 'rootfile'), None)
        if rootfile is None:
            raise ValueError('EPUB container names no package file')
        self.opf = rootfile.attrs['full-path']
        package = parse(self.read(self.opf))
        base = posixpath.dirname(self.opf)
        nodes = list(walk(package))
        self.title = next((''.join(c for c in n.children if isinstance(c, str)).strip()
                           for n in nodes if n.tag == 'dc:title'), '')
        items = {n.attrs['id']: n.attrs for n in nodes if n.tag == 'item'}
        self.href = {ident: posixpath.normpath(posixpath.join(base, unquote(a['href']))) for ident, a in items.items()}
        self.documents = sorted(self.href[i] for i, a in items.items() if a.get('media-type') == 'application/xhtml+xml')
        self.spine = [(self.href[n.attrs['idref']], n.attrs.get('linear', 'yes') != 'no')
                      for n in nodes if n.tag == 'itemref']
        self.skipped = {self.href[i]: 'navigation document' for i, a in items.items() if 'nav' in a.get('properties', '').split()}
        for n in nodes:
            if n.tag == 'reference' and n.attrs.get('type') in SKIPPED_GUIDE:
                target = posixpath.normpath(posixpath.join(base, unquote(n.attrs['href'].split('#')[0])))
                self.skipped.setdefault(target, 'marked ' + n.attrs['type'] + ' in the EPUB guide')

    def read(self, name):
        return self.zip.read(name).decode('utf-8')


class Renderer:
    """Turns a document tree into Markdown blocks; note calls become [^label] with their bodies collected."""

    def __init__(self, document, linear, trees, defects):
        self.document, self.linear, self.trees, self.defects = document, linear, trees, defects
        self.notes = []

    def target(self, href):
        path, _, fragment = href.partition('#')
        document = posixpath.normpath(posixpath.join(posixpath.dirname(self.document), unquote(path))) if path else self.document
        return document, unquote(fragment)

    def is_call(self, node):
        if node.tag != 'a' or 'href' not in node.attrs or re.match(r'[a-z]+:', node.attrs['href']):
            return False
        document, fragment = self.target(node.attrs['href'])
        # A note is what the EPUB marks as one, or a target outside the reading order.
        outside = document in self.trees and self.linear.get(document) is not True
        return bool(fragment) and ('noteref' in node.attrs.get('epub:type', '').split() or outside)

    def inline(self, node, out, marks):
        for child in node.children:
            if isinstance(child, str):
                out.append(re.sub(r'[ \t\r\n\f]+', ' ', child))
            elif child.tag in SILENT:
                continue
            elif child.tag == 'br':
                out.append('\n')
            elif child.tag == 'img':
                self.defects.append(f'image in {self.document}: ' + (child.attrs.get('alt') or child.attrs.get('src', '')))
            elif self.is_call(child):
                out.append(self.call(child))
            elif child.tag in ('strong', 'b', 'em', 'i') and marks:
                mark = '**' if child.tag in ('strong', 'b') else '*'
                inner = []
                self.inline(child, inner, marks)
                text = ''.join(inner)
                core = text.strip(' ')
                if core:
                    lead, trail = text[:len(text) - len(text.lstrip(' '))], text[len(text.rstrip(' ')):]
                    out.append(lead + mark + core + mark + trail)
                else:
                    out.append(text)
            elif child.tag in ('td', 'th'):
                out.append(' | ')
                self.inline(child, out, marks)
            else:
                self.inline(child, out, marks)

    def call(self, node):
        document, fragment = self.target(node.attrs['href'])
        label_parts = []
        self.inline(node, label_parts, False)
        label = ''.join(label_parts).strip()
        body = next((n for n in walk(self.trees[document]) if n.attrs.get('id') == fragment), None) if document in self.trees else None
        if body is None:
            self.defects.append(f'note call without note body in {self.document}: {node.attrs["href"]}')
            return label
        ident = label if re.fullmatch(r'[\w-]+', label) else slug(fragment)
        taken = {n[0] for n in self.notes}
        while ident in taken:
            ident += '-'
        note = Renderer(document, self.linear, self.trees, self.defects)
        note.back = self.document
        blocks = note.blocks(body, inside_note=True)
        if blocks:
            blocks[0] = re.sub(r'^' + re.escape(label) + r'[).]?\s*', '', blocks[0]) if label else blocks[0]
        self.notes.append((ident, [b for b in blocks if b.strip()]))
        self.notes.extend(note.notes)
        return f'[^{ident}]'

    def blocks(self, node, inside_note=False):
        result, buffer = [], []

        def flush():
            text = ''.join(buffer).strip()
            # Adjacent bold runs (<b>a</b><b>b</b>) read as one.
            text = '\n'.join(line.strip() for line in text.split('\n')).replace('****', '')
            buffer.clear()
            if text.strip():
                result.append(text)

        def visit(current, prefix=''):
            for child in current.children:
                if isinstance(child, str) or not (child.tag in BLOCK or child.tag in HEADING or child.tag == 'hr'):
                    if inside_note and isinstance(child, Node) and child.tag == 'a' and self.target(child.attrs.get('href', '#'))[0] == getattr(self, 'back', None):
                        continue  # the note's link back to its call
                    holder = Node('#span', {})
                    holder.children = [child]
                    self.inline(holder, buffer, True)
                    continue
                flush()
                if child.tag in HEADING:
                    parts = []
                    self.inline(child, parts, False)
                    text = ' '.join(''.join(parts).split())
                    if text:
                        result.append('#' * min(6, HEADING[child.tag] + 2) + ' ' + text)
                elif child.tag == 'hr':
                    result.append('* * *')
                elif child.tag in ('ul', 'ol'):
                    number = 0
                    for item in child.children:
                        if isinstance(item, Node) and item.tag == 'li':
                            number += 1
                            parts = []
                            self.inline(item, parts, True)
                            text = ' '.join(''.join(parts).split())
                            if text:
                                result.append((f'{number}. ' if child.tag == 'ol' else '- ') + text)
                else:
                    visit(child)
                    flush()
            flush()

        visit(node)
        return result


def sections(blocks):
    """Split blocks before each heading; the first section keeps whatever precedes the first heading."""
    parts = [[]]
    for block in blocks:
        if block.startswith('#') and parts[-1]:
            parts.append([])
        parts[-1].append(block)
    return parts


def units(blocks, notes):
    """Group heading sections into units of about LONG characters where headings allow; short sections join a neighbour."""
    groups, size = [[]], 0
    for section in sections(blocks):
        length = sum(len(b) + 2 for b in section)
        if groups[-1] and size + length > LONG and min(size, length) >= LONG // 4:
            groups.append([])
            size = 0
        groups[-1].extend(section)
        size += length
    result = []
    for group in groups:
        calls = set(re.findall(r'\[\^([\w-]+)\]', '\n'.join(group)))
        used = [(ident, body) for ident, body in notes if ident in calls]
        result.append((group, used))
    return result


def note_text(ident, body):
    lines = [f'[^{ident}]: ' + body[0].replace('\n', '\n    ')]
    for block in body[1:]:
        lines.append('')
        lines.append('    ' + block.replace('\n', '\n    '))
    return '\n'.join(lines)


def convert(epub, book_id):
    book = Book(epub)
    linear = dict(book.spine)
    trees, defects = {}, []
    for document in dict.fromkeys([d for d, _ in book.spine] + book.documents):
        trees[document] = parse(book.read(document))
    produced, skipped = [], []
    for document, is_linear in book.spine:
        if document in book.skipped:
            skipped.append((document, book.skipped[document]))
            continue
        if not is_linear:
            skipped.append((document, 'non-linear spine item; its notes are placed at their calls'))
            continue
        body = next((n for n in walk(trees[document]) if n.tag == 'body'), trees[document])
        renderer = Renderer(document, linear, trees, defects)
        blocks = renderer.blocks(body)
        if not blocks:
            skipped.append((document, 'no text'))
            continue
        parts = units(blocks, renderer.notes)
        for index, (group, notes) in enumerate(parts, 1):
            heading = '## ' + document + (f' ({index}/{len(parts)})' if len(parts) > 1 else '')
            text = '\n\n'.join([heading] + group + [note_text(i, b) for i, b in notes]) + '\n'
            if len(text) > LONG and len(group) > 1 and not any(b.startswith('#') for b in group[1:]):
                defects.append(f'long text without headings in {document}; kept as one unit')
            produced.append((document, text))
    width = max(3, len(str(len(produced))))
    files = {}
    for number, (document, text) in enumerate(produced, 1):
        files[f'{number:0{width}d}-{slug(Path(document).stem)}.md'] = text
    return book, files, skipped, defects


def overview(book, epub, book_id, files, skipped, defects):
    lines = [f'# {book.title or book_id}', '',
             f'Prepared by `tools/prepare_epub.py` from `{Path(epub).name}`',
             f'(sha256 `{hashlib.sha256(Path(epub).read_bytes()).hexdigest()}`). Rerunning the tool on the same',
             'EPUB reproduces these files byte for byte.', '', '## Units', '',
             '| File | Spine document | Lines |', '| --- | --- | --- |']
    for name, text in files.items():
        lines.append(f'| `segments/{name}` | `{text.splitlines()[0][3:]}` | {len(text.splitlines())} |')
    lines += ['', '## Not converted', '']
    lines += [f'- `{document}`: {reason}' for document, reason in skipped] or ['- None']
    lines += ['', '## Defects to check', '']
    lines += [f'- {defect}' for defect in dict.fromkeys(defects)] or ['- None found by the tool']
    return '\n'.join(lines) + '\n'


def write(epub, book_id, root=ROOT):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', book_id):
        raise ValueError('Book ID must be lowercase ASCII words joined by hyphens')
    book, files, skipped, defects = convert(epub, book_id)
    if not files:
        raise ValueError('The EPUB has no convertible text')
    target = Path(root) / 'sources' / book_id
    segments = target / 'segments'
    outputs = {segments / name: text for name, text in files.items()}
    outputs[target / 'overview.md'] = overview(book, epub, book_id, files, skipped, defects)
    existing = set(segments.glob('*.md')) if segments.is_dir() else set()
    changed = sorted(str(p.relative_to(root)) for p in existing - outputs.keys())
    changed += sorted(str(p.relative_to(root)) for p, text in outputs.items()
                      if p.is_file() and p.read_text(encoding='utf-8') != text)
    if changed:
        raise ValueError('Prepared source differs from this EPUB; changing segmentation needs approval: ' + ', '.join(changed[:10]))
    segments.mkdir(parents=True, exist_ok=True)
    for path, text in outputs.items():
        if not path.is_file():
            path.write_text(text, encoding='utf-8')
    return {'book_id': book_id, 'overview': str((target / 'overview.md').relative_to(root)),
            'units': len(files), 'skipped': len(skipped), 'defects': len(set(defects))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epub', required=True)
    parser.add_argument('--book', required=True)
    args = parser.parse_args(argv)
    try:
        result = write(Path(args.epub), args.book)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
