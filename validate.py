#!/usr/bin/env python3
"""The corpus checks itself.

Every fixture against its schema, every settings hash against the profile
it claims, every section a fixture lists against what it actually holds,
every file against the manifest that must list it, and the tolerance file
against its own schema.

A corpus that nobody validates is a corpus that quietly rots: a fixture
edited by hand, a manifest that forgot an entry, a hash that stopped
matching the settings beside it. None of those announce themselves, and
every one of them makes a consumer's score meaningless.

    python3 -m venv .venv && .venv/bin/pip install jsonschema
    .venv/bin/python validate.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - the message is the point
    sys.exit("this needs `jsonschema`: python3 -m pip install jsonschema")

ROOT = Path(__file__).parent
SCHEMA = ROOT / "schema"


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return error


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(load(SCHEMA / f"{name}.schema.json"))


def against_schema(name: str, path: Path, failures: list[str]) -> dict | None:
    """One file against one schema; the failures name the field."""
    document = load(path)
    if not isinstance(document, dict):
        failures.append(f"{path.relative_to(ROOT)} is not readable JSON: {document}")
        return None
    for error in validator(name).iter_errors(document):
        where = "/".join(str(part) for part in error.path) or "the document"
        failures.append(f"{path.relative_to(ROOT)}: {where}: {error.message}")
    return document


def baseline(failures: list[str]) -> int:
    """The chart corpus: the manifest, then every fixture it lists."""
    directory = ROOT / "baseline"
    manifest = against_schema("baseline-manifest", directory / "manifest.json", failures)
    if manifest is None:
        return 0

    profiles = manifest.get("profiles", {})
    listed: set[str] = set()
    for entry in manifest.get("fixtures", []):
        name = entry.get("file", "")
        listed.add(name)
        path = directory / name
        if not path.is_file():
            failures.append(f"the manifest lists a missing file: {name}")
            continue
        fixture = against_schema("baseline-chart", path, failures)
        if fixture is None:
            continue

        if fixture.get("id") != entry.get("id"):
            failures.append(f"{name}: the id differs from the manifest")

        found = fixture.get("settings_hash", {}).get("value")
        wanted = profiles.get(entry.get("profile", ""), {}).get("settings_hash", {}).get("value")
        if found != wanted or entry.get("settings_hash") != found:
            failures.append(
                f"{name}: the settings hash {found} disagrees with profile "
                f"`{entry.get('profile')}` ({wanted}) or with the manifest"
            )

        for section in fixture.get("sections", []):
            if not isinstance(fixture.get(section), dict):
                failures.append(f"{name}: the listed section `{section}` is missing")

        engine = manifest.get("provenance", {}).get("engine_version")
        if fixture.get("provenance", {}).get("engine_version") != engine:
            failures.append(f"{name}: provenance.engine_version differs from the manifest")

    for sub in ("charts", "variants"):
        for path in sorted((directory / sub).glob("*.json")):
            name = f"{sub}/{path.name}"
            if name not in listed:
                failures.append(f"a fixture the manifest does not list: {name}")
    return len(listed)


def dasha_systems(failures: list[str]) -> int:
    """The dasha systems corpus: its manifest, every file it lists against
    its schema and its hash, and every fixture that records a dasha has its
    file, answering the same balance methods."""
    base = ROOT / "baseline"
    directory = base / "dasha-systems"
    manifest = against_schema(
        "baseline-dasha-systems-manifest", directory / "manifest.json", failures
    )
    if manifest is None:
        return 0
    systems = manifest.get("systems", [])
    listed: set[str] = set()
    answers = 0
    for entry in manifest.get("files", []):
        name = entry.get("file", "")
        listed.add(name)
        path = base / name
        if not path.is_file():
            failures.append(f"the dasha systems manifest lists a missing file: {name}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            failures.append(f"{name}: the sha256 differs from the manifest")
        document = against_schema("baseline-dasha-systems", path, failures)
        if document is None:
            continue
        fixture = load(base / entry.get("fixture", ""))
        if not isinstance(fixture, dict) or not isinstance(fixture.get("dashas"), dict):
            failures.append(f"{name}: the fixture it names records no dasha")
            continue
        recorded = sorted(fixture["dashas"].get("methods", {}))
        if document.get("fixture") != entry.get("fixture") or sorted(entry.get("methods", [])) != recorded:
            failures.append(f"{name}: the fixture or its methods differ from the manifest")
        if sorted(document.get("systems", {})) != sorted(systems):
            failures.append(f"{name}: the systems differ from the manifest's")
        for system, answer in document.get("systems", {}).items():
            if sorted(answer.get("methods", {})) != recorded:
                failures.append(f"{name}: {system} answers methods the fixture does not record")
            answers += len(answer.get("methods", {}))

    for sub in ("charts", "variants"):
        for path in sorted((base / sub).glob("*.json")):
            if isinstance(load(path), dict) and load(path).get("dashas") is not None:
                name = f"dasha-systems/{sub}/{path.name}"
                if name not in listed:
                    failures.append(f"a fixture records a dasha and has no dasha systems file: {sub}/{path.name}")
        for path in sorted((directory / sub).glob("*.json")):
            name = f"dasha-systems/{sub}/{path.name}"
            if name not in listed:
                failures.append(f"a dasha systems file the manifest does not list: {name}")

    counts = manifest.get("counts", {})
    if counts != {"files": len(listed), "systems": len(systems), "methods": answers}:
        failures.append(f"the dasha systems manifest's counts {counts} disagree with its files")
    return len(listed)


def tables(failures: list[str]) -> int:
    """The recorded tables: readable, and each says what it is."""
    count = 0
    for path in sorted((ROOT / "teimeris").glob("*.json")) + sorted((ROOT / "official").glob("*.json")):
        document = load(path)
        if not isinstance(document, dict):
            failures.append(f"{path.relative_to(ROOT)} is not readable JSON: {document}")
            continue
        if not isinstance(document.get("schema"), str):
            failures.append(f"{path.relative_to(ROOT)} declares no schema")
        count += 1
    return count


def corpus(failures: list[str]) -> None:
    """The top-level manifest: it exists, and it names files that exist."""
    document = load(ROOT / "corpus.json")
    if not isinstance(document, dict):
        failures.append(f"corpus.json is not readable JSON: {document}")
        return
    for entry in document.get("corpora", []):
        path = ROOT / entry.get("path", "")
        if not path.exists():
            failures.append(f"corpus.json names a missing path: {entry.get('path')}")
    for name in document.get("schemas", []) + [document.get("tolerances", "")]:
        if not (ROOT / name).is_file():
            failures.append(f"corpus.json names a missing file: {name}")


def main() -> int:
    failures: list[str] = []
    corpus(failures)
    fixtures = baseline(failures)
    systems = dasha_systems(failures)
    against_schema("tolerances", ROOT / "tolerances.json", failures)
    recorded = tables(failures)

    for failure in failures:
        print(f"FAIL  {failure}")
    print(
        f"checked {fixtures} fixtures, {systems} dasha systems files and {recorded} recorded tables: "
        f"{len(failures)} failure(s)"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
