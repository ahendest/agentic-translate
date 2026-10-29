#!/usr/bin/env python3
"""Validate a project's translation units: coverage, author notes, waiting terms, verbatim quotations and terminology.

Book-specific values come from project.json: `target_language`, `prepared_source`, `translation`
and optionally `verbatim_script`, the Unicode script name (for example "Arabic") of quotations
that the translation keeps exactly as printed. A source written in that script omits the key.
Each source unit `NNN-name.md` has the target file `NNN-name.<language>.md`.

A term's first use is read from the translation itself: in book order, the first retained
occurrence of an approved term carries its parenthetical equivalent and footnote call, and the
book defines that note once. Later occurrences carry no parenthetical. A term ID is a footnote ID
that names an approved term; other footnotes are author notes.
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
# A waiting unit outside the scope keeps its placeholders; they are not term occurrences.
PLACEHOLDER_RE = re.compile(r"\{\{TERM:[^}\n]*\}\}")
TERM_DEFINITION_RE = re.compile(r"^\[\^([^\]\n]+)\]:[ \t]*(.*)$")
TERM_REFERENCE_RE = re.compile(r"\[\^([^\]\n]+)\]")
# A retained term may be inflected freely; its first use requires the parenthetical equivalent.
PARENTHETICAL_RE = re.compile(r" \([^()\n]+\)")
NOTE_ID_RE = re.compile(r"\[\^([^\]\n]+)\]")
NOTE_DEFINITION_RE = re.compile(r"^\[\^([^\]\n]+)\]:", re.M)


def note_blocks(text: str, terms: dict):
    """Yield native Markdown terminology notes, preserving logical body lines."""
    lines = text.splitlines(keepends=True)
    offset = i = 0
    while i < len(lines):
        line = lines[i]
        match = TERM_DEFINITION_RE.fullmatch(line.rstrip("\r\n"))
        if not match or match.group(1) not in terms:
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
    """Each retained term in any inflection, longest reading form first, without nested matches; in text order."""
    folded, spans = fold(prose), []
    # Note calls such as `[^sunnet-i-seniye]` hold term IDs, not term uses.
    calls = [match.span() for match in NOTE_ID_RE.finditer(prose)]
    retained = {identifier: term for identifier, term in terms.items() if term["reading"]}
    for identifier, term in sorted(retained.items(), key=lambda item: -len(item[1]["reading"])):
        for match in re.finditer(stem_pattern(term["reading"]), folded):
            # Apostrophe-linked source compounds are separate concepts.
            if prose[match.end():].startswith(("’", "'")):
                continue
            if any(match.start() < end and match.end() > start for start, end in calls):
                continue
            if any(match.start() < end and match.end() > start for start, end, _ in spans):
                continue
            spans.append((match.start(), match.end(), identifier))
    return sorted(spans)


def author_notes(text: str, terms: dict) -> tuple[Counter, Counter]:
    """Calls and definitions of the non-terminology footnotes."""
    definitions = Counter(i for i in NOTE_DEFINITION_RE.findall(text) if i not in terms)
    calls = Counter(i for i in NOTE_ID_RE.findall(text) if i not in terms) - definitions
    return calls, definitions


def check_editorial_footnotes(text: str, path: Path, terms: dict, noted: set[str],
                             definitions: Counter, references: Counter) -> str:
    """Verify terminology notes and parentheticals; return the prose with note bodies blanked, lines kept.

    `noted` holds the terms whose first occurrence came in an earlier unit of the book."""
    parts, position, defined_here = [], 0, set()
    for start, end, identifier, body in note_blocks(text, terms):
        if terms[identifier]["body"] is None or body.strip() != terms[identifier]["body"].strip():
            raise RuntimeError(f"Unapproved or altered editorial footnote {identifier} in {path.name}")
        definitions[identifier] += 1
        defined_here.add(identifier)
        parts.extend((text[position:start], "\n" * text[start:end].count("\n")))
        position = end
    parts.append(text[position:])
    prose = "".join(parts)
    calls = [match for match in TERM_REFERENCE_RE.finditer(prose) if match.group(1) in terms]
    for match in calls:
        references[match.group(1)] += 1
    if {match.group(1) for match in calls} != defined_here:
        raise RuntimeError(f"Terminology notes must be called and defined in the same unit: {path.name}")

    # The first use reads `term (equivalent)[^id]`: the parenthetical when the term has an equivalent and a
    # footnote or later uses keep the term alone, the call when it has a footnote. Later uses carry no
    # parentheses. A term with neither has no first use: every use is written like a later use.
    attached = set()
    for start, end, identifier in retained_occurrences(prose, terms):
        term = terms[identifier]
        gloss = bool(term["gloss"]) and (bool(term["body"]) or term["later"] == "original")
        parenthetical = PARENTHETICAL_RE.match(prose, end)
        if identifier in noted or not (gloss or term["body"]):
            if parenthetical:
                raise RuntimeError(f"Parenthetical after the first use of {identifier}: {prose[start:end]}{parenthetical.group()} "
                                   f"in {path.name}; write the equivalent without parentheses")
            continue
        if gloss and not parenthetical:
            raise RuntimeError(f"Missing parenthetical equivalent at the first use of {prose[start:end]} in {path.name}")
        after = parenthetical.end() if gloss else end
        if term["body"]:
            if not prose[after:].startswith(f"[^{identifier}]"):
                raise RuntimeError(f"Missing footnote at first term occurrence: {identifier} in {path.name}")
            attached.add((after, identifier))
        noted.add(identifier)
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
            gap = [" "]
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
    definitions, references = Counter(), Counter()
    noted: set[str] = set()
    notes = 0
    for target, source in targets.items():
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8")
        if target in scope and not text.strip():
            raise RuntimeError(f"Empty translation unit: {target.name}")
        if target in scope and PENDING_TERM_RE.search(text):
            raise RuntimeError(f"Waiting terminology placeholder in {target.name}; complete the term before validation")
        if target in scope:
            calls, defined = author_notes(source.read_text(encoding="utf-8"), terms)
            if author_notes(text, terms) != (calls, defined):
                raise RuntimeError(f"Author notes differ from the source in {target.name}: "
                                   f"source calls={sorted(calls.elements())} definitions={sorted(defined.elements())}")
            notes += sum(defined.values())
        text = PLACEHOLDER_RE.sub(lambda match: " " * len(match.group()), text)
        prose = check_editorial_footnotes(text, target, terms, noted, definitions, references)
        if script and target in scope:
            check_verbatim(source.read_text(encoding="utf-8"), prose, script, target.name)

    for identifier in sorted({i for i in noted if terms[i]["body"]} | set(definitions) | set(references)):
        if definitions[identifier] != 1 or references[identifier] != 1:
            raise RuntimeError(f"Terminology note must be defined and called once in the book: {identifier}")
    print(f"translation-ok units={len(scope)}: present and non-empty, no waiting terms, "
          f"author notes kept={notes}" + (f", verbatim {script.title()} kept" if script else "") +
          f", first uses with parenthetical and note={len(noted)}, later uses without parentheses; meaning is not checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
