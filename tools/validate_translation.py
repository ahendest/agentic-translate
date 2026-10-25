#!/usr/bin/env python3
"""Validate a project's translation units: coverage, waiting terms, verbatim quotations and terminology notes.

Book-specific values come from project.json: `target_language`, `prepared_source`, `translation`
and optionally `verbatim_script`, the Unicode script name (for example "Arabic") of quotations
that the translation keeps exactly as printed. A source written in that script omits the key.
Each source unit `NNN-name.md` has the target file `NNN-name.<language>.md`.
"""

from __future__ import annotations

import argparse
import functools
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from knowledge import fold, load_project_terms, stem_pattern, unit_files, unit_number, unit_range  # noqa: E402

PENDING_TERM_RE = re.compile(r"\{\{TERM:")
TERM_DEFINITION_RE = re.compile(r"^\[\^(term-[^\]\n]+)\]:[ \t]*(.*)$")
TERM_REFERENCE_RE = re.compile(r"\[\^(term-[^\]\n]+)\]")
# A retained term may be inflected freely; its parenthetical equivalent is required.
PARENTHETICAL_RE = re.compile(r" \([^()\n]+\)")


def note_blocks(text: str):
    """Yield native Markdown terminology notes, preserving logical body lines."""
    lines = text.splitlines(keepends=True)
    offset = i = 0
    while i < len(lines):
        line = lines[i]
        match = TERM_DEFINITION_RE.fullmatch(line.rstrip("\r\n"))
        if not match:
            offset += len(line)
            i += 1
            continue
        start = offset
        identifier, first = match.groups()
        body = [first]
        offset += len(line)
        i += 1
        while i < len(lines):
            value = lines[i].rstrip("\r\n")
            if value.startswith("    ") or value.startswith("\t"):
                body.append(value[4:] if value.startswith("    ") else value[1:])
            elif not value.strip():
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j >= len(lines) or not lines[j].startswith(("    ", "\t")):
                    break
                body.append("")
            else:
                break
            offset += len(lines[i])
            i += 1
        yield start, offset, identifier, "\n".join(body)


def retained_occurrences(prose: str, terms: dict) -> list[tuple[int, int, str]]:
    """Each retained term in any inflection, longest reading form first, without nested matches."""
    folded, spans = fold(prose), []
    for identifier, term in sorted(terms.items(), key=lambda item: -len(item[1]["reading"])):
        for match in re.finditer(stem_pattern(term["reading"]), folded):
            # Apostrophe-linked source compounds are separate concepts.
            if prose[match.end():].startswith(("’", "'")):
                continue
            if any(match.start() < end and match.end() > start for start, end, _ in spans):
                continue
            spans.append((match.start(), match.end(), identifier))
    return spans


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def check_editorial_footnotes(text: str, path: Path, terms: dict, order: dict,
                             definitions: Counter, references: Counter, first_occurrences: set[str]) -> str:
    """Verify terminology notes and parentheticals; return the prose with note bodies blanked, lines kept."""
    parts, position = [], 0
    for start, end, identifier, body in note_blocks(text):
        if identifier not in terms:
            raise RuntimeError(f"Unknown editorial footnote {identifier} in {path.name}")
        if body.strip() != terms[identifier]["body"].strip():
            raise RuntimeError(f"Unapproved or altered editorial footnote {identifier} in {path.name}")
        definitions[identifier] += 1
        parts.extend((text[position:start], "\n" * text[start:end].count("\n")))
        position = end
    parts.append(text[position:])
    prose = "".join(parts)
    calls = list(TERM_REFERENCE_RE.finditer(prose))
    for match in calls:
        identifier = match.group(1)
        if identifier not in terms:
            raise RuntimeError(f"Unknown terminology reference {identifier} in {path.name}")
        term = terms[identifier]
        if path != term["path"] or line_of(prose, match.start()) != term["line"]:
            raise RuntimeError(f"Wrong first-occurrence location for {identifier} in {path.name}")
        references[identifier] += 1

    attached = set()
    occurrences = []
    for start, end, identifier in retained_occurrences(prose, terms):
        parenthetical = PARENTHETICAL_RE.match(prose, end)
        if not parenthetical:
            raise RuntimeError(f"Missing parenthetical equivalent for {prose[start:end]} in {path.name}")
        occurrences.append((start, parenthetical.end(), identifier))

    lines = prose.split("\n")
    for identifier, term in terms.items():
        phrase = term.get("first_phrase")
        if phrase and path == term["path"]:
            offset = sum(len(line) + 1 for line in lines[:term["line"] - 1])
            match = re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", lines[term["line"] - 1] if term["line"] <= len(lines) else "")
            if not match:
                raise RuntimeError(f"Missing contextual first-occurrence phrase for {identifier} in {path.name}")
            occurrences.append((offset + match.start(), offset + match.end(), identifier))
    for start, end, identifier in sorted(occurrences):
        term = terms[identifier]
        expected = f"[^{identifier}]"
        line = line_of(prose, start)
        if term["path"] in order and (order[path], line) < (order[term["path"]], term["line"]):
            raise RuntimeError(f"Term occurs before its recorded first occurrence: {identifier} in {path.name}")
        if identifier not in first_occurrences and path == term["path"] and line == term["line"]:
            if not prose[end:].startswith(expected):
                raise RuntimeError(f"Missing footnote at first term occurrence: {identifier} in {path.name}")
            first_occurrences.add(identifier)
        if prose[end:].startswith(expected):
            attached.add((end, identifier))
    for call in calls:
        if (call.start(), call.group(1)) not in attached:
            raise RuntimeError(f"Terminology reference is not attached to its term: {call.group(1)} in {path.name}")
    return prose


@functools.lru_cache(maxsize=None)
def in_script(character: str, script: str) -> bool:
    """A character belongs to the script whose name starts its Unicode name (ARABIC FATHA, ARABIC-INDIC DIGIT ONE)."""
    name = unicodedata.name(character, "")
    return name.startswith(script) and name[len(script):len(script) + 1] in (" ", "-")


def script_runs(text: str, script: str) -> list[str]:
    """Runs of the script's characters joined by spaces, with whitespace collapsed."""
    runs, current, gap = [], [], []
    for character in text:
        if in_script(character, script):
            current.extend(gap)
            current.append(character)
            gap = []
        elif character.isspace() and current:
            gap.append(" ")
        else:
            if current:
                runs.append("".join(current))
            current, gap = [], []
    if current:
        runs.append("".join(current))
    return runs


def check_verbatim(source: str, prose: str, script: str, name: str) -> None:
    target = " ".join(prose.split())
    for run, count in Counter(script_runs(source, script)).items():
        if target.count(run) < count:
            raise RuntimeError(f"Verbatim {script.title()} text changed or missing in {name}: {run[:60]}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--units", required=True, help="Requested source units, e.g. 001-010")
    args = parser.parse_args(argv)
    first, last = unit_range(args.units)
    project_path = args.project if args.project.is_absolute() else REPO_ROOT / args.project
    project = json.loads(project_path.read_text(encoding="utf-8"))
    translation_root = (REPO_ROOT / project["translation"]).resolve()
    language = project["target_language"]
    script = (project.get("verbatim_script") or "").upper()
    if script and not re.fullmatch(r"[A-Z]+(?: [A-Z]+)*", script):
        raise RuntimeError("verbatim_script must be a Unicode script name, e.g. Arabic")

    sources = unit_files(project)
    targets = {translation_root / f"{path.stem}.{language}.md": path for path in sources}
    strays = sorted(p.name for p in translation_root.glob(f"*.{language}.md") if p not in targets)
    if strays:
        raise RuntimeError(f"Translation files without a source unit: {strays}")
    scope = {target for target, source in targets.items() if first <= unit_number(source) <= last}
    missing = sorted(target.name for target in scope if not target.is_file())
    if not scope or missing:
        raise RuntimeError(f"Translation scope coverage failed: units={args.units} missing={missing}")

    terms = load_project_terms(project, REPO_ROOT)
    order = {target: index for index, target in enumerate(targets)}
    definitions, references = Counter(), Counter()
    first_occurrences: set[str] = set()
    for target, source in targets.items():
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8")
        if target in scope and PENDING_TERM_RE.search(text):
            raise RuntimeError(f"Waiting terminology placeholder in {target.name}; complete the term before validation")
        prose = check_editorial_footnotes(text, target, terms, order, definitions, references, first_occurrences)
        if script and target in scope:
            check_verbatim(source.read_text(encoding="utf-8"), prose, script, target.name)

    required_terms = {identifier for identifier, term in terms.items() if term["path"] in scope}
    for identifier in sorted(required_terms):
        if definitions[identifier] != 1 or references[identifier] != 1 or identifier not in first_occurrences:
            raise RuntimeError(f"Terminology note must have one definition and first-occurrence reference: {identifier}")
    print(f"translation-ok units={len(scope)} terminology-notes={len(required_terms)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
