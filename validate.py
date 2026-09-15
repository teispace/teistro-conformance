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


SAPTAVARGAJA_VARGAS = ("D1", "D2", "D3", "D7", "D9", "D12", "D30")
SHADBALA_SECTIONS = ("foundation", "positions", "houses", "vargas")


def shadbala(failures: list[str]) -> int:
    """The Shadbala: each file's inputs are its fixture's recorded chart,
    field for field; every group total is its components' sum and the whole
    the six groups'; the rupas are the shashtiamshas over 60 and sufficiency
    their comparison with the manifest's requirement; and each natural
    strength is the manifest's."""
    manifest = load(ROOT / "baseline" / "shadbala" / "manifest.json")
    manifest = manifest if isinstance(manifest, dict) else {}

    def close(a, b) -> bool:
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))

    def check(name, entry, document, fixture, systems):
        found = []
        foundation, houses = fixture["foundation"], fixture["houses"]
        bodies = fixture["positions"]["bodies"]
        selected = houses["selected"]
        whole = selected["system"] == "whole-sign"
        wanted = {
            "grahas": {
                g: {
                    "longitude_deg": bodies[g]["sidereal_longitude_deg"],
                    "speed_deg_per_day": bodies[g]["speed_deg_per_day"],
                    "house": bodies[g]["house"],
                    "sign_index": bodies[g]["sign_index"],
                    "degrees_in_sign": bodies[g]["degrees_in_sign"],
                }
                for g in SEVEN
            },
            "varga_sign_index": {v: {g: fixture["vargas"][v]["sign_index"][g] for g in SEVEN} for v in SAPTAVARGAJA_VARGAS},
            "jd_ut": foundation["jd_ut"],
            "is_day_birth": foundation["is_day_birth"],
            "weekday_swe": foundation["panchanga_day"]["weekday_swe"],
            "sunrise_jd": foundation["sunrise"]["sunrise_jd"],
            "sunset_jd": foundation["sunrise"]["sunset_jd"],
            "next_sunrise_jd": foundation["next_day"]["sunrise_jd"],
            "ayanamsha_deg": foundation["ayanamsha"]["value_deg"],
            "hora_lord": foundation["hora_lord"],
            "abda_lord": foundation.get("abda_lord"),
            "lagna_longitude_deg": foundation["lagna"]["sidereal_longitude_deg"],
            "house_system": selected["system"],
            "kendra_cusps_deg": None if whole else [selected["cusps"][i] for i in (0, 3, 6, 9)],
        }
        if document.get("inputs") != wanted:
            found.append(f"{name}: the inputs differ from the fixture's")
        for g, strength in document.get("shadbala", {}).items():
            sthana, kaala = strength["sthana"], strength["kaala"]
            parts = {k: v for k, v in sthana.items() if k != "total"}
            if not close(sum(parts.values()), sthana["total"]):
                found.append(f"{name}: {g}'s sthana total is not its components' sum")
            parts = {k: v for k, v in kaala.items() if k != "total"}
            if not close(sum(parts.values()), kaala["total"]):
                found.append(f"{name}: {g}'s kaala total is not its components' sum")
            six = sthana["total"] + strength["dig"] + kaala["total"] + strength["cheshta"] + strength["naisargika"] + strength["drik"]
            if not close(six, strength["total_shashtiamshas"]):
                found.append(f"{name}: {g}'s total is not the six strengths' sum")
            if not close(strength["total_shashtiamshas"] / 60, strength["total_rupas"]):
                found.append(f"{name}: {g}'s rupas are not its shashtiamshas over 60")
            required = manifest.get("minimum_rupas", {}).get(g)
            if strength["minimum_rupas"] != required or strength["is_sufficient"] != (strength["total_rupas"] >= required):
                found.append(f"{name}: {g}'s requirement or sufficiency differs from the manifest's")
            if strength["naisargika"] != manifest.get("naisargika", {}).get(g):
                found.append(f"{name}: {g}'s natural strength differs from the manifest's")
        return found, 1

    return derived(
        failures,
        "shadbala",
        "baseline-shadbala",
        lambda fixture: all(s in fixture.get("sections", []) for s in SHADBALA_SECTIONS) and "next_day" in fixture.get("foundation", {}),
        check,
        lambda files, systems, answers: {"files": files},
    )


GRAHAS = ("SUN", "MOON", "MARS", "MERCURY", "JUPITER", "VENUS", "SATURN", "RAHU", "KETU")


def bhava_bala(failures: list[str]) -> int:
    """The Bhava bala: each file's inputs are its fixture's recorded lagna and
    houses and its Shadbala file's strengths; the aspects are the seventh and
    the special aspects from those houses; the lord's strength is the lord's
    Shadbala; and each house's total is its components', all in hundredths."""
    special = {"MARS": (4, 8), "JUPITER": (5, 9), "SATURN": (3, 10)}

    def check(name, entry, document, fixture, systems):
        found = []
        bodies = fixture["positions"]["bodies"]
        strength = load(ROOT / "baseline" / "shadbala" / entry["fixture"])
        inputs = document.get("inputs", {})
        wanted = {
            "lagna_sign_index": fixture["foundation"]["lagna"]["sign_index"],
            "graha_house": {g: bodies[g]["house"] for g in GRAHAS},
            "shadbala": {
                g: {
                    "total_shashtiamshas": strength["shadbala"][g]["total_shashtiamshas"],
                    "drik": strength["shadbala"][g]["drik"],
                }
                for g in SEVEN
            }
            if isinstance(strength, dict)
            else None,
        }
        if inputs != wanted:
            found.append(f"{name}: the inputs differ from the fixture's and its Shadbala's")
            return found, 1
        aspected = {str(h): [] for h in range(1, 13)}
        for g in GRAHAS:
            at = inputs["graha_house"][g]
            for count in (7, *special.get(g, ())):
                aspected[str((at + count - 2) % 12 + 1)].append(g)
        if document.get("aspected_by") != aspected:
            found.append(f"{name}: the aspects are not the seventh and special aspects of the recorded houses")
        for index, bhava in enumerate(document.get("bhavas", [])):
            sign = (inputs["lagna_sign_index"] + index) % 12
            lord = RASHI_LORDS[sign]
            if round(inputs["shadbala"][lord]["total_shashtiamshas"] * 100) / 100 != bhava["bhavadhipati"]:
                found.append(f"{name}: house {index + 1}'s lord's strength is not {lord}'s Shadbala")
            if abs(bhava["bhavadhipati"] + bhava["dig"] + bhava["drishti"] - bhava["total"]) > 0.015:
                found.append(f"{name}: house {index + 1}'s total is not its components'")
        return found, 1

    return derived(
        failures,
        "bhava-bala",
        "baseline-bhava-bala",
        lambda fixture: all(s in fixture.get("sections", []) for s in SHADBALA_SECTIONS) and "next_day" in fixture.get("foundation", {}),
        check,
        lambda files, systems, answers: {"files": files},
    )


RASHI_LORDS = ("MARS", "VENUS", "MERCURY", "MOON", "SUN", "MERCURY", "VENUS", "MARS", "JUPITER", "SATURN", "SATURN", "JUPITER")




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


SEVEN_KARAKAS = ("AK", "AmK", "BK", "MK", "PK", "GK", "DK")
EIGHT_KARAKAS = ("AK", "AmK", "BK", "MK", "PK", "GK", "DK", "PiK")
YOGA_BODY_FIELDS = (
    "sidereal_longitude_deg", "degrees_in_sign", "sign_index", "house", "dignity",
    "is_retrograde", "combust", "is_vargottama", "avastha_baladi",
)


def recorded_chart(name: str, inputs: dict, fixture: dict) -> list[str]:
    """What a rule corpus repeats of a fixture's chart: its bodies as
    recorded, and chara karakas that rank the grahas by degrees in sign (Rahu
    by thirty less)."""
    found = []
    recorded = fixture["positions"]["bodies"]
    bodies = inputs.get("bodies", {})
    for body, fields in bodies.items():
        if any(fields.get(f) != recorded[body].get(f) for f in YOGA_BODY_FIELDS):
            found.append(f"{name}: inputs.bodies.{body} differs from the fixture's")
    degrees = {g: bodies[g]["degrees_in_sign"] for g in SEVEN}
    by_degree = sorted(SEVEN, key=lambda g: -degrees[g])
    if inputs.get("chara_karaka_7") != dict(zip(by_degree, SEVEN_KARAKAS)):
        found.append(f"{name}: the seven chara karakas do not rank the grahas by degree")
    degrees["RAHU"] = 30 - bodies["RAHU"]["degrees_in_sign"]
    by_degree = sorted(degrees, key=lambda g: -degrees[g])
    if inputs.get("chara_karaka_8") != dict(zip(by_degree, EIGHT_KARAKAS)):
        found.append(f"{name}: the eight chara karakas do not rank the grahas by degree")
    return found


def rule_keys(directory: str, schema: str, failures: list[str]) -> list[dict]:
    """A rule corpus's `rules.json`, against its schema, each key once."""
    path = ROOT / "baseline" / directory / "rules.json"
    rules = (against_schema(schema, path, failures) or {}).get("rules", [])
    keys = [rule["key"] for rule in rules]
    if len(keys) != len(set(keys)):
        failures.append(f"baseline/{directory}/rules.json: a rule key repeats")
    return rules


def presence_houses(name: str, key: str, presence: dict, bodies: dict) -> list[str]:
    """A presence's houses are its planets' recorded houses, distinct and
    ascending, the lagna left out."""
    houses = sorted({bodies[g]["house"] for g in presence["planets"] if g in bodies and g != "LAGNA"})
    return [] if presence["houses"] == houses else [f"{name}: {key}'s houses are not its planets' houses"]


def yogas(failures: list[str]) -> int:
    """The yogas: each file's inputs are its fixture's recorded chart, every
    present rule is one `rules.json` ships, and each presence's houses are
    its planets' recorded houses."""
    rules = rule_keys("yogas", "baseline-yoga-rules", failures)
    known = {rule["key"] for rule in rules}

    def check(name, entry, document, fixture, systems):
        inputs = document.get("inputs", {})
        found = recorded_chart(name, inputs, fixture)
        present = document.get("present", {})
        for key, presence in present.items():
            if key not in known:
                found.append(f"{name}: {key} is not a rule rules.json ships")
            found += presence_houses(name, key, presence, inputs.get("bodies", {}))
        if entry.get("present") != len(present):
            found.append(f"{name}: the manifest's presence count differs")
        return found, len(present)

    return derived(
        failures,
        "yogas",
        "baseline-yogas",
        lambda fixture: "positions" in fixture.get("sections", []),
        check,
        lambda files, systems, answers: {"files": files, "rules": len(rules), "presences": answers},
    )


def doshas(failures: list[str]) -> int:
    """The doshas: each file's inputs are its fixture's recorded chart and,
    where it records one, its panchanga with the Moon's pada; every present
    dosha is a rule `rules.json` ships, found from at least one reference,
    with its planets' houses; and each net status is what its cancellations
    and the rule's threshold make it (the threshold, when a rule gives none,
    the number of references it was found from)."""
    rules = {rule["key"]: rule for rule in rule_keys("doshas", "baseline-dosha-rules", failures)}

    def check(name, entry, document, fixture, systems):
        inputs = document.get("inputs", {})
        found = recorded_chart(name, inputs, fixture)
        recorded = fixture.get("panchanga")
        if recorded is None:
            expected = None
        else:
            expected = {
                "tithi_number": recorded["tithi"]["number"],
                "paksha": recorded["tithi"]["paksha"],
                "vara": recorded["vara"],
                "nakshatra_index": recorded["nakshatra_index"],
                "moon_pada": fixture["positions"]["bodies"]["MOON"]["pada"],
                "yoga_index": recorded["yoga_index"],
                "karana_index": recorded["karana"]["index"],
            }
        if inputs.get("panchanga") != expected:
            found.append(f"{name}: inputs.panchanga differs from the fixture's")
        present = document.get("present", {})
        for key, presence in present.items():
            rule = rules.get(key)
            if rule is None:
                found.append(f"{name}: {key} is not a rule rules.json ships")
                continue
            found += presence_houses(name, key, presence, inputs.get("bodies", {}))
            if not presence["present_from"]:
                found.append(f"{name}: {key} is present from no reference")
            cancelled = len(presence["cancellations"])
            threshold = rule.get("fullCancellationThreshold", max(1, len(presence["present_from"])))
            status = (
                "fully-cancelled" if cancelled >= threshold
                else "partially-cancelled" if cancelled
                else "active"
            )
            if presence["net_status"] != status:
                found.append(f"{name}: {key}'s net status is not what its cancellations make it")
        if entry.get("present") != len(present):
            found.append(f"{name}: the manifest's presence count differs")
        return found, len(present)

    return derived(
        failures,
        "doshas",
        "baseline-doshas",
        lambda fixture: "positions" in fixture.get("sections", []),
        check,
        lambda files, systems, answers: {"files": files, "rules": len(rules), "presences": answers},
    )


VIMSHOTTARI = ("KETU", "VENUS", "SUN", "MOON", "MARS", "RAHU", "JUPITER", "SATURN", "MERCURY")


def pyjhora_vimshottari(failures: list[str]) -> int:
    """PyJHora's Vimshottari, rank 3: every file against its schema and its
    hash, its inputs its fixture's instant and place, its periods the nine
    lords in Vimshottari's order each divided in that order from itself, each
    starting where the one before ended, and every chart fixture either
    answered or listed with the tool's refusal."""
    root = ROOT / "pyjhora" / "vimshottari"
    manifest = against_schema("pyjhora-vimshottari-manifest", root / "manifest.json", failures)
    if manifest is None:
        return 0
    listed = set()
    for entry in manifest.get("files", []):
        name = entry.get("file", "")
        path = ROOT / "pyjhora" / name
        listed.add(entry.get("fixture"))
        if not path.is_file():
            failures.append(f"the PyJHora manifest lists a missing file: {name}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            failures.append(f"pyjhora/{name}: the sha256 differs from the manifest")
        document = against_schema("pyjhora-vimshottari", path, failures)
        fixture = load(ROOT / "baseline" / entry.get("fixture", ""))
        if document is None or not isinstance(fixture, dict):
            continue
        resolved, place = fixture["input"]["resolved"], fixture["input"]["place"]
        wanted = {
            "jd_ut": resolved["jd_ut"],
            "latitude_deg": place["latitude"],
            "longitude_deg": place["longitude"],
            "tz_offset_min": resolved["tz_offset_min"],
        }
        if document.get("inputs") != wanted or document.get("fixture") != entry.get("fixture"):
            failures.append(f"pyjhora/{name}: the inputs differ from the fixture's")
        if sorted(document.get("durations", {})) != sorted(manifest.get("durations", [])):
            failures.append(f"pyjhora/{name}: the durations differ from the manifest's")
        for duration, answer in document.get("durations", {}).items():
            periods = answer.get("periods", [])
            first = VIMSHOTTARI.index(periods[0][0]) if periods else 0
            for k, (maha, antara, start, years) in enumerate(periods):
                m, a = divmod(k, 9)
                lord = VIMSHOTTARI[(first + m) % 9]
                if (maha, antara) != (lord, VIMSHOTTARI[(first + m + a) % 9]):
                    failures.append(f"pyjhora/{name} {duration}: period {k} is not Vimshottari's order")
                    break
                if k + 1 < len(periods):
                    end = start + years * answer["year_days"]
                    if abs(end - periods[k + 1][2]) > 1e-3:
                        failures.append(f"pyjhora/{name} {duration}: period {k} does not end where the next starts")
                        break
    refused = {entry.get("fixture") for entry in manifest.get("refused", [])}
    for path in sorted((ROOT / "baseline" / "charts").glob("*.json")):
        fixture = f"charts/{path.name}"
        if (fixture in listed) == (fixture in refused):
            failures.append(f"pyjhora: {fixture} is neither answered nor refused, or both")
    counts = {"files": len(listed), "durations": len(manifest.get("durations", [])), "refused": len(refused)}
    if manifest.get("counts") != counts:
        failures.append(f"the PyJHora manifest's counts {manifest.get('counts')} disagree with its files")
    for path in sorted((root / "charts").glob("*.json")):
        if f"charts/{path.name}" not in listed:
            failures.append(f"a PyJHora file the manifest does not list: {path.name}")
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
    systems = dasha_systems(failures) + rashi_dashas(failures) + kalachakra(failures)
    systems += ashtakavarga(failures) + vimshopaka(failures) + shadbala(failures) + bhava_bala(failures)
    systems += yogas(failures) + doshas(failures) + pyjhora_vimshottari(failures)
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
