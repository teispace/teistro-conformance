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


def derived(
    failures: list[str],
    directory: str,
    schema: str,
    eligible,
    check,
    counts,
) -> int:
    """A corpus computed from the chart fixtures' recorded values: its
    manifest, every file it lists against its schema and its hash, the
    fixture each names, and a file for exactly the fixtures that hold what
    it reads.

    `eligible(fixture)` says whether a fixture should have a file;
    `check(name, entry, document, fixture, systems)` returns the file's
    own failures and how many answers it holds; `counts(listed, systems,
    answers)` is what the manifest's counts must be.
    """
    base = ROOT / "baseline"
    root = base / directory
    manifest = against_schema(f"{schema}-manifest", root / "manifest.json", failures)
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
            failures.append(f"the {directory} manifest lists a missing file: {name}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            failures.append(f"{name}: the sha256 differs from the manifest")
        document = against_schema(schema, path, failures)
        if document is None:
            continue
        fixture = load(base / entry.get("fixture", ""))
        if not isinstance(fixture, dict) or not eligible(fixture):
            failures.append(f"{name}: the fixture it names does not hold what it reads")
            continue
        if document.get("fixture") != entry.get("fixture"):
            failures.append(f"{name}: the fixture differs from the manifest")
        if "systems" in manifest and sorted(document.get("systems", {})) != sorted(systems):
            failures.append(f"{name}: the systems differ from the manifest's")
        found, held = check(name, entry, document, fixture, systems)
        failures.extend(found)
        answers += held

    for sub in ("charts", "variants"):
        for path in sorted((base / sub).glob("*.json")):
            fixture = load(path)
            if isinstance(fixture, dict) and eligible(fixture):
                if f"{directory}/{sub}/{path.name}" not in listed:
                    failures.append(f"a fixture holds what {directory} reads and has no file: {sub}/{path.name}")
        for path in sorted((root / sub).glob("*.json")):
            if f"{directory}/{sub}/{path.name}" not in listed:
                failures.append(f"a {directory} file the manifest does not list: {directory}/{sub}/{path.name}")

    if manifest.get("counts") != counts(len(listed), len(systems), answers):
        failures.append(f"the {directory} manifest's counts {manifest.get('counts')} disagree with its files")
    return len(listed)


def dasha_systems(failures: list[str]) -> int:
    """The nakshatra-seeded systems beside Vimshottari: each answers exactly
    the balance methods its fixture records."""

    def check(name, entry, document, fixture, systems):
        found = []
        recorded = sorted(fixture["dashas"].get("methods", {}))
        if sorted(entry.get("methods", [])) != recorded:
            found.append(f"{name}: the methods differ from the fixture's")
        held = 0
        for system, answer in document.get("systems", {}).items():
            if sorted(answer.get("methods", {})) != recorded:
                found.append(f"{name}: {system} answers methods the fixture does not record")
            held += len(answer.get("methods", {}))
        return found, held

    return derived(
        failures,
        "dasha-systems",
        "baseline-dasha-systems",
        lambda fixture: isinstance(fixture.get("dashas"), dict),
        check,
        lambda files, systems, answers: {"files": files, "systems": systems, "methods": answers},
    )


def kalachakra(failures: list[str]) -> int:
    """The Kalachakra dasha: each file answers the methods its fixture
    records, from the Moon's nakshatra and pada it says, and the manifest's
    tables serve every nakshatra exactly once."""
    manifest = load(ROOT / "baseline" / "kalachakra" / "manifest.json")
    if isinstance(manifest, dict):
        served = sorted(n for table in manifest.get("rules", {}).get("tables", []) for n in table.get("nakshatras", []))
        if served != list(range(27)):
            failures.append("kalachakra/manifest.json: the tables do not serve every nakshatra exactly once")

    def check(name, entry, document, fixture, systems):
        found = []
        recorded = sorted(fixture["dashas"].get("methods", {}))
        if sorted(entry.get("methods", [])) != recorded or sorted(document.get("methods", {})) != recorded:
            found.append(f"{name}: the methods differ from the fixture's")
        longitude = fixture["dashas"]["moon_sidereal_longitude_deg"]
        if document.get("moon_sidereal_longitude_deg") != longitude:
            found.append(f"{name}: the Moon differs from the fixture's")
        in_nakshatra = (longitude % (360 / 27)) / (360 / 108)
        if document.get("nakshatra_index") != int(longitude // (360 / 27)) or document.get("pada_index") != int(in_nakshatra):
            found.append(f"{name}: the nakshatra or pada is not the Moon's")
        return found, len(document.get("methods", {}))

    return derived(
        failures,
        "kalachakra",
        "baseline-kalachakra",
        lambda fixture: isinstance(fixture.get("dashas"), dict),
        check,
        lambda files, systems, answers: {"files": files, "methods": answers},
    )


SEVEN = ("SUN", "MOON", "MARS", "MERCURY", "JUPITER", "VENUS", "SATURN")


def ashtakavarga(failures: list[str]) -> int:
    """The Ashtakavarga: each file's inputs are its fixture's recorded
    signs, and its sums are the sums of its own bindus."""

    def check(name, entry, document, fixture, systems):
        found = []
        bodies = fixture["positions"]["bodies"]
        wanted = {
            "lagna_sign_index": fixture["foundation"]["lagna"]["sign_index"],
            "graha_sign_index": {g: bodies[g]["sign_index"] for g in SEVEN},
        }
        if document.get("inputs") != wanted:
            found.append(f"{name}: the inputs differ from the fixture's")
        bav = document.get("bav", {})
        sav = [sum(bav.get(g, [0] * 12)[i] for g in SEVEN) for i in range(12)]
        if sav != document.get("sav"):
            found.append(f"{name}: the sav is not the sum of the bav")
        return found, 1

    return derived(
        failures,
        "ashtakavarga",
        "baseline-ashtakavarga",
        lambda fixture: "foundation" in fixture.get("sections", []) and "positions" in fixture.get("sections", []),
        check,
        lambda files, systems, answers: {"files": files},
    )


VIMSHOPAKA_VARGAS = ("D1", "D2", "D3", "D4", "D7", "D9", "D10", "D12", "D16", "D20", "D24", "D27", "D30", "D40", "D45", "D60")


def vimshopaka(failures: list[str]) -> int:
    """The Vimshopaka: each file's inputs are its fixture's recorded varga
    signs, and every scheme's weights sum to twenty."""
    manifest = load(ROOT / "baseline" / "vimshopaka" / "manifest.json")
    if isinstance(manifest, dict):
        for scheme in manifest.get("schemes", []):
            if sum(scheme.get("weights", {}).values()) != 20:
                failures.append(f"vimshopaka/manifest.json: the {scheme.get('key')} weights do not sum to 20")

    def check(name, entry, document, fixture, systems):
        wanted = {v: {g: fixture["vargas"][v]["sign_index"][g] for g in SEVEN} for v in VIMSHOPAKA_VARGAS}
        if document.get("inputs", {}).get("sign_index") != wanted:
            return [f"{name}: the inputs differ from the fixture's"], 1
        return [], 1

    return derived(
        failures,
        "vimshopaka",
        "baseline-vimshopaka",
        lambda fixture: "vargas" in fixture.get("sections", []) and "D60" in fixture.get("vargas", {}),
        check,
        lambda files, systems, answers: {"files": files},
    )


GRAHAS = ("SUN", "MOON", "MARS", "MERCURY", "JUPITER", "VENUS", "SATURN", "RAHU", "KETU")


def rashi_dashas(failures: list[str]) -> int:
    """The sign-based dashas: each file's inputs are its fixture's recorded
    chart, field for field."""

    def check(name, entry, document, fixture, systems):
        foundation = fixture["foundation"]
        bodies = fixture["positions"]["bodies"]
        wanted = {
            "jd_ut": fixture["input"]["resolved"]["jd_ut"],
            "lagna_sign_index": foundation["lagna"]["sign_index"],
            "arudha_lagna_sign_index": foundation["arudha_lagna_sign_index"],
            "navamsha_lagna_sign_index": foundation["navamsha_lagna_sign_index"],
            "graha_sign_index": {g: bodies[g]["sign_index"] for g in GRAHAS},
            "graha_dignity": {g: bodies[g]["dignity"] for g in GRAHAS},
        }
        found = []
        for field, value in wanted.items():
            if document.get("inputs", {}).get(field) != value:
                found.append(f"{name}: inputs.{field} differs from the fixture's")
        return found, len(document.get("systems", {}))

    return derived(
        failures,
        "rashi-dashas",
        "baseline-rashi-dashas",
        lambda fixture: "foundation" in fixture.get("sections", []) and "positions" in fixture.get("sections", []),
        check,
        lambda files, systems, answers: {"files": files, "systems": systems, "answers": answers},
    )


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
    systems = dasha_systems(failures) + rashi_dashas(failures) + kalachakra(failures)
    systems += ashtakavarga(failures) + vimshopaka(failures)
    against_schema("tolerances", ROOT / "tolerances.json", failures)
    recorded = tables(failures)

    for failure in failures:
        print(f"FAIL  {failure}")
    print(
        f"checked {fixtures} fixtures, {systems} derived files and {recorded} recorded tables: "
        f"{len(failures)} failure(s)"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
