#!/usr/bin/env python3
# SPDX-License-Identifier: CC0-1.0
"""Record JPL's own answers: CSPICE over DE440, and JPL Horizons.

The recording is the corpus's truth rung (ADR-0021 in the Teistro SDK): an
implementation's positions measured against JPL's ephemeris rather than
against another implementation.

By default it records the CSPICE half alone, asking no web service:

- ``jpl/cspice/states.json``: ``spkezr`` over ``de440.bsp`` (and the same
  states over DE441), geocentric, with the IAU 1976/1980 of-date rotations
  SPICE defines.
- ``jpl/cspice/self-check.json``: CSPICE against itself (DE441 against
  DE440, one-iteration against converged light time, a frame round trip,
  the rotations' orthonormality).
- ``jpl/manifest.json``: the recording date, the versions, the kernels by
  URL and SHA-256, the instants and why each was chosen, and the files'
  hashes.

With ``--horizons`` it also queries the JPL Horizons API and records its
half beside it, with its own manifest (``jpl/horizons/manifest.json``):
geometric states (``horizons/vectors.json``), astrometric and apparent
places (``horizons/observer.json``), every raw response under
``horizons/raw/`` with every query exactly as sent, and Horizons measured
against CSPICE (``jpl/self-check.json``). The flag is off by default.

Every recorded value comes from CSPICE or from Horizons. The adversarial
instants are *chosen* with CSPICE over DE440 (a lunar perigee, a station),
which cannot bias a value: the value at the chosen instant is still JPL's.

Usage::

    python3 -m venv .venv && .venv/bin/pip install spiceypy==8.2.0
    .venv/bin/python -I tools/record_jpl.py \\
        --kernels DIR_WITH_de440.bsp_AND_naif0012.tls \\
        --de441 DIR_WITH_de441_part-1.bsp_AND_de441_part-2.bsp
    python3 -I tools/record_jpl.py --verify          # offline, stdlib only
    .venv/bin/python -I tools/record_jpl.py --verify --kernels DIR --de441 DIR

``--verify`` checks every hash in the manifest and that the self-check is
what ``states.json`` produces, byte for byte; with the kernels it also
recomputes ``states.json`` byte for byte. ``--rebuild`` rewrites the derived
files offline, for a change to how they are laid out or measured. Each
takes ``--horizons`` to include that half.

Dependencies: the standard library, and for recording (or ``--verify`` with
kernels) spiceypy 8.2.0, which bundles CSPICE N0067. Pinned here and in the
manifest; a different version is refused rather than silently used.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JPL = ROOT / "jpl"
RAW = JPL / "horizons" / "raw"

RECORDER_VERSION = "1.0.0"
SPICEYPY_VERSION = "8.2.0"  # pinned; bundles CSPICE N0067
CSPICE_VERSION = "CSPICE_N0067"
ENDPOINT = "https://ssd.jpl.nasa.gov/api/horizons_file.api"
# The file API's own documented version (doc/horizons_file.html, 1.0, 2021
# July). The GET API (doc/horizons.html) documents 1.3 and signs 1.2; it is
# not used because its URLs refuse a long TLIST (HTTP 502 at about 60 times).
FILE_API_VERSION = "1.0"
KERNEL_BASE = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels"
KERNELS = {
    "de440.bsp": f"{KERNEL_BASE}/spk/planets/de440.bsp",
    "naif0012.tls": f"{KERNEL_BASE}/lsk/naif0012.tls",
}
DE441 = {
    "de441_part-1.bsp": f"{KERNEL_BASE}/spk/planets/de441_part-1.bsp",
    "de441_part-2.bsp": f"{KERNEL_BASE}/spk/planets/de441_part-2.bsp",
}

AU_KM = 149597870.7
C_KM_S = 299792.458
ARCSEC = math.degrees(1.0) * 3600.0
J2000 = 2451545.0
TICK = 512  # every instant is a whole number of 1/512 day: exact in binary and in nine decimals

# Horizons targets. A planet's body centre comes from its satellite
# ephemeris and covers less than 1600 to 2400; its system barycentre is
# DE441's own and covers it all. CSPICE over DE440 has body centres only for
# the Sun, the Moon, Mercury, Venus and the Earth, so the barycentres are
# what Horizons and CSPICE are compared over.
TARGETS = {
    "10": ("Sun", "body"),
    "301": ("Moon", "body"),
    "199": ("Mercury", "body"),
    "299": ("Venus", "body"),
    "399": ("Earth", "body"),
    "499": ("Mars", "body"),
    "599": ("Jupiter", "body"),
    "699": ("Saturn", "body"),
    "799": ("Uranus", "body"),
    "899": ("Neptune", "body"),
    "999": ("Pluto", "body"),
    "4": ("Mars barycentre", "barycentre"),
    "5": ("Jupiter barycentre", "barycentre"),
    "6": ("Saturn barycentre", "barycentre"),
    "7": ("Uranus barycentre", "barycentre"),
    "8": ("Neptune barycentre", "barycentre"),
    "9": ("Pluto barycentre", "barycentre"),
}
GEOCENTRIC = ["10", "301", "199", "299", "499", "599", "699", "799", "899", "999", "4", "5", "6", "7", "8", "9"]
BARYCENTRIC = ["10", "301", "199", "299", "399", "499", "599", "699", "799", "899", "999", "4", "5", "6", "7", "8", "9"]
TOPOCENTRIC = ["10", "301", "199", "299", "4", "5", "6", "7", "8", "9"]
SPICE_TARGETS = ["10", "301", "199", "299", "4", "5", "6", "7", "8", "9"]

# Three of the corpus's own chart places (baseline/charts), chosen for what
# they stress: altitude, the equator at altitude, and the Arctic.
SITES = [
    {"name": "Kathmandu", "fixture": "charts/c051-kathmandu-2020-04-13.json",
     "longitude_deg": 85.324, "latitude_deg": 27.7172, "altitude_km": 1.4},
    {"name": "Quito", "fixture": "charts/c042-quito-2001-01-01.json",
     "longitude_deg": -78.4678, "latitude_deg": -0.1807, "altitude_km": 2.85},
    {"name": "Tromsø", "fixture": "charts/c028-troms-1988-06-21.json",
     "longitude_deg": 18.9553, "latitude_deg": 69.6492, "altitude_km": 0.01},
]

VECTOR_COLUMNS = ["jd_tdb", "x_au", "y_au", "z_au", "vx_au_per_day", "vy_au_per_day", "vz_au_per_day"]
OBSERVER_COLUMNS = [
    "jd_tt",
    "ra_astrometric_deg",
    "dec_astrometric_deg",
    "ra_apparent_deg",
    "dec_apparent_deg",
    "delta_au",
    "deldot_km_per_s",
    "ecliptic_longitude_apparent_deg",
    "ecliptic_latitude_apparent_deg",
]
# Horizons' column labels, in the order of OBSERVER_COLUMNS after the date.
OBSERVER_LABELS = ["R.A.___(ICRF)", "DEC____(ICRF)", "R.A.__(a-app)", "DEC___(a-app)", "delta", "deldot", "ObsEcLon", "ObsEcLat"]
VECTOR_LABELS = ["X", "Y", "Z", "VX", "VY", "VZ"]

# SPICE's own IAU 1976 precession / IAU 1980 nutation and obliquity frames,
# defined as parameterised dynamic frames (frames required reading, s. 4).
OF_DATE_FRAMES = {
    "TEISTRO_TOD_IAU1980": {
        "id": 1400001,
        "FAMILY": "TRUE_EQUATOR_AND_EQUINOX_OF_DATE",
        "PREC_MODEL": "EARTH_IAU_1976",
        "NUT_MODEL": "EARTH_IAU_1980",
    },
    "TEISTRO_MECL_IAU1980": {
        "id": 1400002,
        "FAMILY": "MEAN_ECLIPTIC_AND_EQUINOX_OF_DATE",
        "PREC_MODEL": "EARTH_IAU_1976",
        "OBLIQ_MODEL": "EARTH_IAU_1980",
    },
}


# --------------------------------------------------------------------------
# Writing JSON the corpus way: two-space indentation, a leaf array of
# numbers on one line, a final newline, and every float as Python's repr
# (the shortest string that reads back to the same double).


def dumps(value, indent: int = 0) -> str:
    pad, inner = "  " * indent, "  " * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [f"{inner}{json.dumps(k, ensure_ascii=False)}: {dumps(v, indent + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(not isinstance(v, (dict, list)) for v in value):
            return "[" + ", ".join(dumps(v) for v in value) + "]"
        return "[\n" + ",\n".join(inner + dumps(v, indent + 1) for v in value) + "\n" + pad + "]"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("a recorded value is not finite")
        return repr(value)
    return json.dumps(value, ensure_ascii=False)


def write(path: Path, document) -> bytes:
    data = (dumps(document) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(JPL).as_posix()


# --------------------------------------------------------------------------
# Time


def gregorian_jd(year: int, month: int, day: int) -> float:
    """The Julian date at 0h of a proleptic Gregorian calendar date."""
    a = (14 - month) // 12
    y, m = year + 4800 - a, month + 12 * a - 3
    jdn = day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jdn - 0.5


MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def tick(jd: float) -> float:
    return round(jd * TICK) / TICK


def tlist_value(jd: float) -> str:
    return f"{jd:.9f}"


def grid() -> list[dict]:
    """One instant in each five-year stratum of 1600 to 2400, at a
    deterministic pseudo-random offset (from a SHA-256 of the stratum's
    year) so that no instant falls on a round date or a lunar phase."""
    out = []
    for year in range(1600, 2400, 5):
        start, end = gregorian_jd(year, 1, 1), gregorian_jd(year + 5, 1, 1)
        digest = hashlib.sha256(f"teistro-conformance/jpl/grid/{year}".encode()).digest()
        u = int.from_bytes(digest[:8], "big") / 2**64
        out.append({"jd": tick(start + u * (end - start)), "kind": "grid", "why": f"the stratum {year} to {year + 5}"})
    return out


# --------------------------------------------------------------------------
# The adversarial instants, chosen with CSPICE over DE440. Only the choice
# uses SPICE here; nothing chosen is recorded as a value.


def spice(kernels: Path, de441: Path | None):
    try:
        import spiceypy
    except ImportError:
        sys.exit("recording needs spiceypy: pip install spiceypy==" + SPICEYPY_VERSION)
    if spiceypy.__version__ != SPICEYPY_VERSION:
        sys.exit(f"spiceypy {spiceypy.__version__} is installed; the recording pins {SPICEYPY_VERSION}")
    if spiceypy.tkvrsn("TOOLKIT") != CSPICE_VERSION:
        sys.exit(f"CSPICE {spiceypy.tkvrsn('TOOLKIT')} is bundled; the recording pins {CSPICE_VERSION}")
    spiceypy.kclear()
    for name in KERNELS:
        spiceypy.furnsh(str(kernels / name))
    for name, frame in OF_DATE_FRAMES.items():
        fid = frame["id"]
        spiceypy.pipool(f"FRAME_{name}", [fid])
        spiceypy.pcpool(f"FRAME_{fid}_NAME", [name])
        spiceypy.pipool(f"FRAME_{fid}_CLASS", [5])
        spiceypy.pipool(f"FRAME_{fid}_CLASS_ID", [fid])
        spiceypy.pipool(f"FRAME_{fid}_CENTER", [399])
        spiceypy.pcpool(f"FRAME_{fid}_RELATIVE", ["J2000"])
        spiceypy.pcpool(f"FRAME_{fid}_DEF_STYLE", ["PARAMETERIZED"])
        spiceypy.pcpool(f"FRAME_{fid}_ROTATION_STATE", ["ROTATING"])
        for key in ("FAMILY", "PREC_MODEL", "NUT_MODEL", "OBLIQ_MODEL"):
            if key in frame:
                spiceypy.pcpool(f"FRAME_{fid}_{key}", [frame[key]])
    return spiceypy


def et_of(jd: float) -> float:
    return (jd - J2000) * 86400.0


def jd_of(et: float) -> float:
    return J2000 + et / 86400.0


def refine(f, a: float, b: float) -> float:
    """A sign change of f in [a, b], by bisection to a millisecond."""
    fa = f(a)
    while b - a > 1e-3:
        m = 0.5 * (a + b)
        fm = f(m)
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b = m
    return 0.5 * (a + b)


def first_root(f, start_jd: float, step_days: float, span_days: float, want=None) -> float:
    et, end = et_of(start_jd), et_of(start_jd + span_days)
    step = step_days * 86400.0
    prev = f(et)
    while et < end:
        nxt = f(et + step)
        if (prev > 0) != (nxt > 0) and (want is None or want(prev, nxt, et)):
            return refine(f, et, et + step)
        et, prev = et + step, nxt
    raise RuntimeError("no root found")


def adversarial(sp) -> list[dict]:
    def dist_rate(et):
        state, _ = sp.spkezr("301", et, "J2000", "NONE", "399")
        return sum(state[i] * state[i + 3] for i in range(3))

    def lon(target, et):
        pos, _ = sp.spkpos(target, et, "ECLIPJ2000", "LT+S", "399")
        return math.atan2(pos[1], pos[0])

    def lon_rate(target):
        return lambda et: math.remainder(lon(target, et + 1800.0) - lon(target, et - 1800.0), math.tau)

    def from_sun(target):
        return lambda et: math.remainder(lon(target, et) - lon("10", et), math.tau)

    def jd(et):
        return tick(jd_of(et))

    out = []

    def add(value, why):
        out.append({"jd": jd(value), "kind": "adversarial", "why": why})

    for year in (1600, 2000, 2399):
        start = gregorian_jd(year, 3 if year == 1600 else 1, 1)
        perigee = first_root(dist_rate, start, 0.5, 40, want=lambda a, b, et: a < 0 < b)
        apogee = first_root(dist_rate, start, 0.5, 40, want=lambda a, b, et: a > 0 > b)
        add(perigee, f"the first lunar perigee after {year}-{3 if year == 1600 else 1:02d}-01 (DE440 geocentric distance)")
        add(apogee, f"the first lunar apogee after {year}-{3 if year == 1600 else 1:02d}-01 (DE440 geocentric distance)")
    for target, name, years in (("199", "Mercury", (1600, 2000)), ("4", "Mars", (2000, 2398))):
        for year in years:
            station = first_root(lon_rate(target), gregorian_jd(year, 6 if year == 1600 else 1, 1), 1.0, 800)
            add(station, f"the first station of {name} after {year} (DE440 apparent ecliptic longitude, J2000 ecliptic)")
    for year in (1600, 2000, 2399):
        start = gregorian_jd(year, 6 if year == 2399 else 1, 15 if year == 1600 else 1)
        conj = first_root(from_sun("301"), start, 0.25, 35, want=lambda a, b, et: a < 0 < b)
        add(conj, f"the first Sun-Moon conjunction in apparent J2000 ecliptic longitude after {year} (DE440)")

    def farther(a, b, et):
        m, _ = sp.spkpos("199", et, "J2000", "NONE", "399")
        s, _ = sp.spkpos("10", et, "J2000", "NONE", "399")
        return a < 0 < b and sum(v * v for v in m) > sum(v * v for v in s)

    sup = first_root(from_sun("199"), gregorian_jd(2000, 1, 1), 0.5, 200, want=farther)
    add(sup, "the first superior conjunction of Mercury after 2000 (DE440): light passing close to the Sun")
    # DE440's Chebyshev records all start at JD 2287184.5 and run 4, 8, 16 or
    # 32 days, so 2287184.5 + 32k is a record boundary for every body.
    for target_jd, why, first in ((gregorian_jd(1600, 1, 1), "the first after 1600", True), (J2000, "the first after J2000.0", True),
                                  (gregorian_jd(2400, 1, 1), "the last before 2400", False)):
        k = (math.ceil if first else math.floor)((target_jd - 2287184.5) / 32)
        out.append({"jd": 2287184.5 + 32 * k, "kind": "adversarial", "why": f"{why} of the DE440 record boundaries every body shares"})
    out.append({"jd": 2440432.5, "kind": "adversarial",
                "why": "the end of de441_part-1.bsp, inside the overlap with part-2, and a DE440 record boundary of every body"})
    out.append({"jd": J2000, "kind": "adversarial", "why": "J2000.0"})
    out.append({"jd": gregorian_jd(1600, 1, 1), "kind": "adversarial", "why": "the start of the range, 1600-01-01 0h"})
    out.append({"jd": gregorian_jd(2400, 1, 1), "kind": "adversarial", "why": "the end of the range, 2400-01-01 0h"})
    return out


def instants(sp) -> list[dict]:
    chosen = {}
    for entry in grid() + adversarial(sp):
        chosen.setdefault(entry["jd"], entry)
    return [chosen[k] for k in sorted(chosen)]


# --------------------------------------------------------------------------
# Horizons


def horizons_input(params: dict, jds: list[float]) -> str:
    lines = ["!$$SOF"] + [f"{k}='{v}'" for k, v in params.items()] + ["TLIST="]
    lines += [f"'{tlist_value(jd)}'" for jd in jds]
    return "\n".join(lines) + "\n"


def post(text: str) -> tuple[int, bytes]:
    boundary = "teistro" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"format\"\r\n\r\njson\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"input\"; filename=\"input.txt\"\r\n"
        f"Content-Type: text/plain\r\n\r\n{text}\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    delay = 10.0
    for attempt in range(8):
        request = urllib.request.Request(
            ENDPOINT, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                                          "User-Agent": f"teistro-conformance record_jpl/{RECORDER_VERSION}"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (502, 503, 504):
                return error.code, error.read()
            print(f"  HTTP {error.code}; waiting {delay:.0f} s (attempt {attempt + 1})", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError) as error:
            print(f"  {error}; waiting {delay:.0f} s (attempt {attempt + 1})", file=sys.stderr)
        time.sleep(delay)
        delay = min(delay * 2, 300.0)
    sys.exit("Horizons did not answer after eight attempts")


REFUSAL = re.compile(r"No ephemeris for target \"[^\"]+\" (prior to|after) A\.D\. (\d{4})-([A-Z]{3})-(\d{2}) (\d{2}):(\d{2}):(\d{2}\.\d+) (TDB|TT|UT)")


def refusal_bound(message: str) -> tuple[str, float] | None:
    match = REFUSAL.search(message)
    if not match:
        return None
    side, y, mon, d, hh, mm, ss, _scale = match.groups()
    jd = gregorian_jd(int(y), MONTHS[mon], int(d)) + (int(hh) + int(mm) / 60 + float(ss) / 3600) / 24
    return side, jd


class Recorder:
    """Sends the queries serially and keeps every raw response."""

    def __init__(self):
        self.queries: list[dict] = []
        RAW.mkdir(parents=True, exist_ok=True)

    def ask(self, qid: str, params: dict, jds: list[float]) -> list[tuple[dict, dict]]:
        """Every response to one series, the refusals included: Horizons
        refuses a TLIST that reaches outside a body's ephemeris and names the
        bound, so the series is resent without the instants beyond it."""
        answers, wanted = [], list(jds)
        for round_ in range(4):
            text = horizons_input(params, wanted)
            status, raw = post(text)
            digest = sha256(raw)
            path = RAW / f"{digest}.json"
            path.write_bytes(raw)
            document = json.loads(raw)
            version = document.get("signature", {}).get("version")
            if version != FILE_API_VERSION:
                sys.exit(f"{qid}: the API signs version {version}; this recorder parses {FILE_API_VERSION}")
            entry = {"id": qid if round_ == 0 else f"{qid}#{round_}", "series": qid, "endpoint": ENDPOINT,
                     "method": "POST multipart/form-data", "format": "json", "input": text, "http_status": status,
                     "signature": document.get("signature"), "file": rel(path), "sha256": digest}
            self.queries.append(entry)
            answers.append((entry, document))
            error = document.get("error")
            if status == 200 and not error:
                return answers
            bound = refusal_bound(error or "")
            if bound is None:
                sys.exit(f"{qid}: Horizons answered {status}: {error}")
            side, limit = bound
            wanted = [jd for jd in wanted if (jd >= limit if side == "prior to" else jd <= limit)]
            print(f"  {qid}: refused {side} JD {limit}; resending {len(wanted)} instants", file=sys.stderr)
            time.sleep(1.0)
        sys.exit(f"{qid}: still refused after four rounds")


# --------------------------------------------------------------------------
# Parsing a kept raw response. Used both when recording and by `verify`, so
# the files are a function of the raw responses and nothing else.


def table(result: str) -> tuple[list[str], list[list[str]]]:
    lines = result.splitlines()
    soe = lines.index("$$SOE")
    eoe = lines.index("$$EOE")
    header = lines[soe - 2]
    labels = [c.strip() for c in header.split(",")]
    rows = [[c.strip() for c in line.split(",")] for line in lines[soe + 1:eoe]]
    return labels, rows


def number(text: str):
    return None if text in ("n.a.", "") else float(text)


def header_value(result: str, key: str) -> str | None:
    for line in result.splitlines():
        if line.startswith(key):
            return line.split(":", 1)[1].strip()
    return None


def source_of(result: str, key: str) -> str | None:
    value = header_value(result, key)
    match = re.search(r"\{source: ([^}]+)\}", value or "")
    return match.group(1).strip() if match else None


def parse_series(answers: list[tuple[dict, dict]], date_label: str, labels_wanted: list[str]):
    rows, refused, final = [], [], None
    for entry, document in answers:
        if document.get("error"):
            refused.append({"query": entry["id"], "refusal": document["error"].strip()})
            continue
        final = entry, document
        labels, raw_rows = table(document["result"])
        index = [labels.index(date_label)] + [labels.index(label) for label in labels_wanted]
        for raw in raw_rows:
            values = [number(raw[i]) for i in index]
            rows.append(values)
    return rows, refused, final


def load_answers(queries: list[dict]) -> dict[str, list[tuple[dict, dict]]]:
    grouped: dict[str, list[tuple[dict, dict]]] = {}
    for entry in queries:
        raw = (JPL / entry["file"]).read_bytes()
        if sha256(raw) != entry["sha256"]:
            raise ValueError(f"{entry['file']}: the SHA-256 differs from the manifest")
        grouped.setdefault(entry["series"], []).append((entry, json.loads(raw)))
    return grouped


def check_times(qid: str, rows: list[list], expected: list[float]) -> None:
    got = [row[0] for row in rows]
    if got != [jd for jd in expected if jd in set(got)] or not set(got) <= set(expected):
        raise ValueError(f"{qid}: Horizons answered for instants that were not asked")


def build_vectors(manifest: dict, grouped) -> dict:
    jds = [i["jd"] for i in manifest["instants"]]
    series = []
    for centre, targets in (("500@399", GEOCENTRIC), ("@0", BARYCENTRIC)):
        for code in targets:
            qid = f"vectors/{centre}/{code}"
            rows, refused, final = parse_series(grouped[qid], "JDTDB", VECTOR_LABELS)
            check_times(qid, rows, jds)
            result = final[1]["result"]
            series.append({
                "target": code, "name": TARGETS[code][0], "kind": TARGETS[code][1], "centre": centre,
                "target_source": source_of(result, "Target body name"),
                "centre_source": source_of(result, "Center body name"),
                "query": final[0]["id"], "refused": refused, "rows": rows,
            })
    return {
        "schema": "teistro-conformance/jpl-horizons-vectors/1",
        "source": "JPL Horizons API (file-based endpoint), EPHEM_TYPE=VECTORS",
        "evidence_rank": 1,
        "recorded": manifest["recorded"],
        "scale": "TDB", "frame": "ICRF", "reference_plane": "the ICRF equator (REF_PLANE=FRAME)",
        "correction": "NONE (geometric: no light time, no aberration, no deflection)",
        "units": {"position": "au", "velocity": "au per day", "au_km": AU_KM},
        "columns": VECTOR_COLUMNS,
        "note": "A body centre (499 to 999) comes from that planet's satellite ephemeris and covers less than the range; Horizons' refusal of the instants outside it is kept in `refused`. A barycentre (4 to 9) is the planetary ephemeris's own.",
        "series": series,
    }


def site_of(centre: str):
    for site in SITES:
        if centre == f"coord@399:{site['name']}":
            return site
    return None


def build_observer(manifest: dict, grouped) -> dict:
    jds = [i["jd"] for i in manifest["instants"]]
    series, headers = [], {}
    places = [("500@399", None, GEOCENTRIC)] + [(f"coord@399:{s['name']}", s, TOPOCENTRIC) for s in SITES]
    for centre, site, targets in places:
        for code in targets:
            qid = f"observer/{centre}/{code}"
            rows, refused, final = parse_series(grouped[qid], "Date_________JDTT", OBSERVER_LABELS)
            check_times(qid, rows, jds)
            result = final[1]["result"]
            for key in ("Rel. light bend", "Rel. lght bnd GM", "Atmos refraction", "EOP file", "EOP coverage", "Center pole/equ", "Center radii"):
                headers.setdefault(key, header_value(result, key))
            series.append({
                "target": code, "name": TARGETS[code][0], "kind": TARGETS[code][1],
                "site": {"name": "geocentre", "centre": "500@399"} if site is None else {
                    "name": site["name"], "centre": "coord@399", "fixture": site["fixture"],
                    "longitude_deg": site["longitude_deg"], "latitude_deg": site["latitude_deg"], "altitude_km": site["altitude_km"]},
                "target_source": source_of(result, "Target body name"),
                "query": final[0]["id"], "refused": refused, "rows": rows,
            })
    return {
        "schema": "teistro-conformance/jpl-horizons-observer/1",
        "source": "JPL Horizons API (file-based endpoint), EPHEM_TYPE=OBSERVER, QUANTITIES 1, 2, 20, 31",
        "evidence_rank": 1,
        "recorded": manifest["recorded"],
        "scale": "TT",
        "columns": OBSERVER_COLUMNS,
        "conventions": {
            "ra_astrometric_deg": "Horizons quantity 1: astrometric right ascension and declination in the ICRF, corrected for down-leg light time only (no aberration, no deflection)",
            "ra_apparent_deg": "Horizons quantity 2: airless apparent right ascension and declination of date: light time, gravitational deflection by the Sun, stellar aberration, and IAU 1976 precession with IAU 1980 nutation corrected by the Earth orientation (EOP) celestial pole offsets; the header states the equinox lies 53 mas from the IAU 2006/2000A one",
            "delta_au": "Horizons quantity 20: the light-time aberrated range (c times the down-leg light time) and its rate in km/s",
            "ecliptic_longitude_apparent_deg": "Horizons quantity 31: the observer-centred apparent longitude and latitude on the IAU 1976/1980 ecliptic and equinox of date, with light time, deflection and stellar aberration",
            "precession_nutation": "the Horizons manual (https://ssd.jpl.nasa.gov/horizons/manual.html, Precession Model, Nutation Model, ITRF93): IAU 1976 precession (Lieske) from 1799-01-01 to 2202-01-01 and Owen's long-term precession and obliquity model outside it; IAU 1980 nutation (Wahr); both corrected by the JPL EOP file's measured celestial pole offsets, which cover 1962 to the file's date and are held at the last predicted value after it. The response header says only IAU76/80, so a comparison outside 1799 to 2202 meets Owen's model, not Lieske's",
            "time": "the manual's TDB to UT section: before 1962-01-20 Horizons does not keep the periodic difference between TT and TDB (at most 2 ms), so a TT instant before then is read as the same TDB",
            "relativity": "the manual's Statement of Ephemeris Limitations: second-order terms in stellar aberration, and the Sun's gravitational deflection of light",
            "precision": "EXTRA_PREC=YES: right ascension and declination to 1e-9 degree; quantity 31 to 1e-7 degree",
            "topocentric": "a site is geodetic on the Horizons Earth model (Center radii below), longitude east, altitude above the reference ellipsoid; Horizons places it with its own UT1 (EOP data within its coverage)",
            "header": headers,
        },
        "series": series,
    }


# --------------------------------------------------------------------------
# CSPICE


def spice_states(sp, manifest: dict, kernels: Path, de441: Path | None) -> dict:
    jds = [i["jd"] for i in manifest["instants"]]
    epochs = [{"jd": jd, "et_tdb": et_of(jd), "et_from_tt": float(sp.unitim(et_of(jd), "TT", "TDB"))} for jd in jds]

    def series(kernel, epoch, frame, corr):
        out = []
        for code in SPICE_TARGETS:
            rows = []
            for e in epochs:
                state, lt = sp.spkezr(code, e["et_tdb" if epoch == "tdb" else "et_from_tt"], frame, corr, "399")
                rows.append([float(v) for v in state] + [float(lt)])
            out.append({"target": code, "name": TARGETS[code][0], "kind": TARGETS[code][1] if code in ("10", "301", "199", "299") else "barycentre",
                        "kernel": kernel, "epoch": epoch, "frame": frame, "correction": corr, "rows": rows})
        return out

    blocks = []
    for frame in ("J2000", "ECLIPJ2000"):
        blocks += series("de440", "tdb", frame, "NONE")
    for corr in ("LT", "LT+S", "CN", "CN+S"):
        blocks += series("de440", "tt", "J2000", corr)
    for corr in ("LT", "LT+S"):
        blocks += series("de440", "tt", "ECLIPJ2000", corr)
    of_date = {"tod": [], "mecl": []}
    for e in epochs:
        for key, name in (("tod", "TEISTRO_TOD_IAU1980"), ("mecl", "TEISTRO_MECL_IAU1980")):
            m = sp.pxform("J2000", name, e["et_from_tt"])
            of_date[key].append([float(m[i][j]) for i in range(3) for j in range(3)])
    if de441 is not None:
        for name in DE441:
            sp.furnsh(str(de441 / name))
        sp.unload(str(kernels / "de440.bsp"))
        blocks += series("de441", "tdb", "J2000", "NONE")
        for corr in ("CN", "CN+S"):
            blocks += series("de441", "tt", "J2000", corr)
        for name in DE441:
            sp.unload(str(de441 / name))
        sp.furnsh(str(kernels / "de440.bsp"))
    return {
        "schema": "teistro-conformance/jpl-cspice-states/1",
        "source": f"CSPICE {CSPICE_VERSION} through spiceypy {SPICEYPY_VERSION}, spkezr and pxform",
        "evidence_rank": 1,
        "recorded": manifest["recorded"],
        "observer": "399 (the geocentre)",
        "units": {"position": "km", "velocity": "km per s", "light_time": "s"},
        "columns": ["x_km", "y_km", "z_km", "vx_km_per_s", "vy_km_per_s", "vz_km_per_s", "light_time_s"],
        "epochs": {
            "tdb": "the instant's JD read as TDB: et = (jd - 2451545) * 86400, as the vectors are",
            "tt": "the instant's JD read as TT, as the observer tables are, converted to TDB by SPICE's unitim (the leapseconds kernel's DELTET formula)",
        },
        "corrections": {
            "NONE": "geometric",
            "LT": "Newtonian light time, one iteration",
            "LT+S": "one-iteration light time and SPICE's stellar aberration",
            "CN": "converged Newtonian light time",
            "CN+S": "converged light time and stellar aberration; SPICE applies no gravitational deflection",
        },
        "targets": "the Sun, the Moon, Mercury and Venus are body centres; Mars to Pluto are system barycentres, because de440.bsp and de441 carry no other centres for them",
        "kernels": {"de440": ["de440.bsp", "naif0012.tls"], "de441": list(DE441) + ["naif0012.tls"]},
        "instants": epochs,
        "of_date": {
            "note": "Row-major rotation matrices from J2000 (the ICRF, as SPICE treats it) at each instant's TT epoch, from SPICE's parameterised dynamic frames: `tod` the true equator and equinox of date (IAU 1976 precession, IAU 1980 nutation) and `mecl` the mean ecliptic and equinox of date (IAU 1976 precession, IAU 1980 obliquity). The true ecliptic of date is `mecl` turned about its pole by the nutation in longitude, which is the longitude of the true equinox (the first axis of `tod`) in `mecl`.",
            "definitions": OF_DATE_FRAMES,
            "tod": of_date["tod"],
            "mecl": of_date["mecl"],
        },
        "series": blocks,
    }


# --------------------------------------------------------------------------
# The reference against itself


def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def angle(a, b) -> float:
    a, b = unit(a), unit(b)
    cross = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    return math.atan2(math.sqrt(sum(x * x for x in cross)), sum(x * y for x, y in zip(a, b))) * ARCSEC


def radec(ra_deg, dec_deg):
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    return [math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)]


def apply(m9, v):
    return [m9[3 * i] * v[0] + m9[3 * i + 1] * v[1] + m9[3 * i + 2] * v[2] for i in range(3)]


def true_ecliptic(tod, mecl, v):
    """v (J2000) on the true ecliptic and equinox of date."""
    x_tod_in_j2000 = [tod[0], tod[1], tod[2]]  # the first row of tod is its x axis in J2000
    e = apply(mecl, x_tod_in_j2000)
    dpsi = math.atan2(e[1], e[0])
    w = apply(mecl, v)
    c, s = math.cos(dpsi), math.sin(dpsi)
    return [c * w[0] + s * w[1], -s * w[0] + c * w[1], w[2]]


SRS_AU = 1.97412574336e-8  # the Sun's Schwarzschild radius in au (SOFA's ERFA_SRS)


def deflected(p, q, e, em):
    """SOFA's iauLd for the Sun: the direction p of a body (unit, from the
    observer), q the body from the Sun (unit), e the observer from the Sun
    (unit), em the observer-Sun distance in au."""
    qpe = [q[i] + e[i] for i in range(3)]
    qdqpe = sum(q[i] * qpe[i] for i in range(3))
    w = SRS_AU / em / max(qdqpe, 1e-9)
    eq = [e[1] * q[2] - e[2] * q[1], e[2] * q[0] - e[0] * q[2], e[0] * q[1] - e[1] * q[0]]
    peq = [p[1] * eq[2] - p[2] * eq[1], p[2] * eq[0] - p[0] * eq[2], p[0] * eq[1] - p[1] * eq[0]]
    return [p[i] + w * peq[i] for i in range(3)]


def self_check(vectors: dict, observer: dict, states: dict) -> dict:
    instants = [e["jd"] for e in states["instants"]]
    pos = {jd: k for k, jd in enumerate(instants)}

    def cspice(kernel, epoch, frame, corr):
        return {s["target"]: s["rows"] for s in states["series"]
                if (s["kernel"], s["epoch"], s["frame"], s["correction"]) == (kernel, epoch, frame, corr)}

    horizons_vec = {s["target"]: s["rows"] for s in vectors["series"] if s["centre"] == "500@399"}
    horizons_obs = {s["target"]: s["rows"] for s in observer["series"] if s["site"]["centre"] == "500@399"}
    sun_tt = cspice("de440", "tt", "J2000", "CN")["10"]
    tod, mecl = states["of_date"]["tod"], states["of_date"]["mecl"]
    rungs = []

    def worst(name, kernel, measure, unit_name, what):
        has = any(s["kernel"] == kernel for s in states["series"])
        if not has:
            return
        bodies = []
        for code in SPICE_TARGETS:
            best = None
            n = 0
            for value, jd, extra in measure(code, kernel):
                n += 1
                if best is None or value > best[0]:
                    best = (value, jd, extra)
            if best is None:
                continue
            row = {"target": code, "name": TARGETS[code][0], "compared": n, "worst": best[0], "at_jd": best[1]}
            row.update(best[2])
            bodies.append(row)
        rungs.append({"rung": name, "kernel": kernel, "unit": unit_name, "what": what, "bodies": bodies})

    def elongation(k, v):
        return {"elongation_deg": angle(v, sun_tt[k][:3]) / 3600.0}

    def geometric(code, kernel):
        ref = cspice(kernel, "tdb", "J2000", "NONE")[code]
        for row in horizons_vec[code]:
            k = pos[row[0]]
            h = [x * AU_KM for x in row[1:4]]
            yield angle(h, ref[k][:3]), row[0], {"position_km": math.dist(h, ref[k][:3])}

    def astrometric(corr):
        def measure(code, kernel):
            ref = cspice(kernel, "tt", "J2000", corr)[code]
            for row in horizons_obs[code]:
                k = pos[row[0]]
                yield angle(radec(row[1], row[2]), ref[k][:3]), row[0], {}
        return measure

    def apparent(with_deflection):
        def measure(code, kernel):
            ref = cspice(kernel, "tt", "J2000", "CN+S")[code]
            geo = cspice(kernel, "tt", "J2000", "CN")[code]
            for row in horizons_obs[code]:
                k = pos[row[0]]
                v = ref[k][:3]
                if with_deflection and code != "10":
                    # the body from the Sun at the light-time epoch, the Earth from the Sun now
                    sun = sun_tt[k][:3]
                    q = unit([geo[k][i] - sun[i] for i in range(3)])
                    e = unit([-sun[i] for i in range(3)])
                    v = deflected(unit(v), q, e, math.sqrt(sum(x * x for x in sun)) / AU_KM)
                yield angle(radec(row[3], row[4]), apply(tod[k], v)), row[0], elongation(k, ref[k][:3])
        return measure

    def ecliptic(code, kernel):
        ref = cspice(kernel, "tt", "J2000", "CN+S")[code]
        for row in horizons_obs[code]:
            k = pos[row[0]]
            lon, lat = math.radians(row[7]), math.radians(row[8])
            h = [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
            yield angle(h, true_ecliptic(tod[k], mecl[k], ref[k][:3])), row[0], elongation(k, ref[k][:3])

    def distance(code, kernel):
        ref = cspice(kernel, "tt", "J2000", "CN")[code]
        for row in horizons_obs[code]:
            k = pos[row[0]]
            yield abs(row[5] * AU_KM - ref[k][6] * C_KM_S), row[0], {}

    for kernel in ("de440", "de441"):
        worst("geometric", kernel, geometric, "arcsec",
              "Horizons VECTORS (NONE, ICRF, TDB, geocentre) against spkezr NONE in J2000; `position_km` is the distance between the two positions")
        worst("astrometric", kernel, astrometric("CN"), "arcsec",
              "Horizons quantity 1 against the direction of spkezr CN in J2000 at the TT epoch")
    worst("astrometric_one_iteration", "de440", astrometric("LT"), "arcsec",
          "Horizons quantity 1 against spkezr LT, whose light time is one Newtonian iteration rather than converged")
    for kernel in ("de440", "de441"):
        worst("apparent", kernel, apparent(False), "arcsec",
              "Horizons quantity 2 against spkezr CN+S turned to SPICE's IAU 1976/1980 true equator and equinox of date")
    worst("apparent_with_modelled_deflection", "de441", apparent(True), "arcsec",
          "as `apparent`, with the Sun's gravitational deflection, which SPICE does not apply, added to the CSPICE direction by SOFA's iauLd formula; an explanation of `apparent`, never a correction of a recorded value")
    centres = {"4": "499", "5": "599", "6": "699", "7": "799", "8": "899", "9": "999"}

    def centre_offset(code, kernel):
        if code not in centres:
            return
        ref = cspice(kernel, "tdb", "J2000", "NONE")[code]
        for row in horizons_vec[centres[code]]:
            k = pos[row[0]]
            h = [x * AU_KM for x in row[1:4]]
            yield angle(h, ref[k][:3]), row[0], {"position_km": math.dist(h, ref[k][:3]), "horizons_target": centres[code]}

    worst("body_centre_against_barycentre", "de441", centre_offset, "arcsec",
          "Horizons' body centre of Mars to Pluto (499 to 999) against CSPICE's system barycentre: what comparing the one with the other costs, not a disagreement")
    for kernel in ("de440", "de441"):
        worst("ecliptic_of_date", kernel, ecliptic, "arcsec",
              "Horizons quantity 31 against spkezr CN+S on SPICE's IAU 1976/1980 true ecliptic and equinox of date")
        worst("range", kernel, distance, "km", "Horizons quantity 20 (delta) against c times spkezr CN's light time")
    eras = apparent_eras(observer, horizons_obs, cspice, pos, tod, sun_tt, states)
    return {
        "schema": "teistro-conformance/jpl-self-check/1",
        "recorded": vectors["recorded"],
        "note": "The reference measured against itself: Horizons (DE441) against CSPICE over DE440 and over DE441, geocentric, for every instant both answer. Computed from the recorded files only, so `verify` reproduces it. A rung is the worst angular separation of the two directions (or the worst range difference), with the instant it falls at. Nothing here alters a recorded value.",
        "rungs": rungs,
        "apparent_eras": eras,
    }


def eop_bounds(observer: dict) -> tuple[float, float]:
    """The EOP file's data start and prediction end, from the response header."""
    text = observer["conventions"]["header"].get("EOP coverage") or ""
    match = re.search(r"(\d{4})-([A-Z]{3})-(\d{2}) TO .*PREDICTS-> (\d{4})-([A-Z]{3})-(\d{2})", text)
    if not match:
        raise ValueError("the header states no EOP coverage")
    y0, m0, d0, y1, m1, d1 = match.groups()
    return gregorian_jd(int(y0), MONTHS[m0], int(d0)), gregorian_jd(int(y1), MONTHS[m1], int(d1))


def apparent_eras(observer, horizons_obs, cspice, pos, tod, sun_tt, states) -> dict:
    """The apparent rung over DE441, with the modelled deflection, split by
    the spans the Horizons manual names: Owen's precession before 1799 and
    after 2202, the EOP file's data and prediction span, and the spans
    either side of it. In each, the mean right ascension and declination
    differences, and the worst separation before and after turning the
    CSPICE direction about the pole of date by the mean right ascension
    difference: a residual that collapses when one constant equinox offset
    is removed is a convention, not a disagreement."""
    if not any(s["kernel"] == "de441" for s in states["series"]):
        return {}
    start, end = eop_bounds(observer)
    spans = [("before 1799 (Owen precession, before the EOP data)", -math.inf, gregorian_jd(1799, 1, 1)),
             ("1799 to the EOP data (Lieske precession, before the EOP data)", gregorian_jd(1799, 1, 1), start),
             ("the EOP file's data and prediction span", start, end),
             ("after the EOP prediction to 2202 (last predicted EOP held)", end, gregorian_jd(2202, 1, 1)),
             ("after 2202 (Owen precession, last predicted EOP held)", gregorian_jd(2202, 1, 1), math.inf)]
    aps, geo = cspice("de441", "tt", "J2000", "CN+S"), cspice("de441", "tt", "J2000", "CN")
    rows = []
    for code in SPICE_TARGETS:
        for row in horizons_obs[code]:
            k = pos[row[0]]
            v = unit(aps[code][k][:3])
            if code != "10":
                sun = sun_tt[k][:3]
                q = unit([geo[code][k][i] - sun[i] for i in range(3)])
                v = deflected(v, q, unit([-x for x in sun]), math.sqrt(sum(x * x for x in sun)) / AU_KM)
            w = unit(apply(tod[k], v))
            ra, dec = math.atan2(w[1], w[0]), math.asin(w[2])
            dra = math.remainder(math.radians(row[3]) - ra, math.tau) * ARCSEC
            rows.append((row[0], code, dra, (math.radians(row[4]) - dec) * ARCSEC, w, radec(row[3], row[4])))
    out = []
    for name, lo, hi in spans:
        inside = [r for r in rows if lo <= r[0] < hi]
        if not inside:
            continue
        mean_ra = sum(r[2] for r in inside) / len(inside)
        mean_dec = sum(r[3] for r in inside) / len(inside)
        c, s_ = math.cos(mean_ra / ARCSEC), math.sin(mean_ra / ARCSEC)
        before = max(inside, key=lambda r: angle(r[5], r[4]))
        after = max(((angle(r[5], [c * r[4][0] - s_ * r[4][1], s_ * r[4][0] + c * r[4][1], r[4][2]]), r) for r in inside), key=lambda x: x[0])
        out.append({"span": name, "from_jd": lo if math.isfinite(lo) else None, "to_jd": hi if math.isfinite(hi) else None,
                    "rows": len(inside), "mean_ra_difference_arcsec": mean_ra, "mean_dec_difference_arcsec": mean_dec,
                    "worst": angle(before[5], before[4]), "worst_at_jd": before[0], "worst_target": before[1],
                    "worst_after_mean_ra_offset": after[0], "worst_after_at_jd": after[1][0], "worst_after_target": after[1][1]})
    return {"kernel": "de441", "unit": "arcsec",
            "what": "Horizons quantity 2 minus CSPICE CN+S with the modelled deflection, on SPICE's IAU 1976/1980 true equator of date; right ascension differences are of right ascension itself (an equinox offset), not scaled by the cosine of declination",
            "spans": out}


# --------------------------------------------------------------------------


def horizons_params(kind: str, centre: str, code: str) -> dict:
    params = {"COMMAND": code, "OBJ_DATA": "NO", "MAKE_EPHEM": "YES"}
    if kind == "vectors":
        params.update({"EPHEM_TYPE": "VECTORS", "CENTER": centre, "REF_SYSTEM": "ICRF", "REF_PLANE": "FRAME",
                       "VEC_CORR": "NONE", "OUT_UNITS": "AU-D", "VEC_TABLE": "2", "VEC_LABELS": "NO",
                       "CSV_FORMAT": "YES", "TIME_TYPE": "TDB", "TLIST_TYPE": "JD"})
    else:
        site = site_of(centre)
        params.update({"EPHEM_TYPE": "OBSERVER"})
        if site is None:
            params["CENTER"] = centre
        else:
            params.update({"CENTER": "coord@399", "COORD_TYPE": "GEODETIC",
                           "SITE_COORD": f"{site['longitude_deg']},{site['latitude_deg']},{site['altitude_km']}"})
        params.update({"QUANTITIES": "1,2,20,31", "REF_SYSTEM": "ICRF", "ANG_FORMAT": "DEG", "EXTRA_PREC": "YES",
                       "APPARENT": "AIRLESS", "CSV_FORMAT": "YES", "CAL_FORMAT": "JD", "TIME_TYPE": "TT", "TLIST_TYPE": "JD"})
    return params


def kernel_entries(kernels_dir: Path, de441: Path | None) -> list[dict]:
    out = []
    for name, url in list(KERNELS.items()) + (list(DE441.items()) if de441 else []):
        path = (de441 if name in DE441 else kernels_dir) / name
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        out.append({"file": name, "url": url, "bytes": path.stat().st_size, "sha256": digest.hexdigest(),
                    "used_for": "the TT to TDB conversion (DELTET)" if name.endswith(".tls") else
                    ("the DE440 states" if name == "de440.bsp" else "the DE441 states, which are what Horizons reads")})
    return out


# --------------------------------------------------------------------------
# What CSPICE alone can say about itself


OBLIQUITY_J2000 = math.radians(84381.448 / 3600.0)  # SPICE's ECLIPJ2000: the IAU 1976 obliquity at J2000


def cspice_self_check(states: dict) -> dict:
    """The CSPICE half measured against itself, reading no Horizons file:
    DE441 against DE440 per body, correction and epoch; one-iteration light
    time against converged; ECLIPJ2000 against J2000 turned by SPICE's fixed
    obliquity (a frame round trip that should agree to rounding); and the
    of-date rotations' orthonormality."""
    instants = [e["jd"] for e in states["instants"]]
    by = {(s["kernel"], s["epoch"], s["frame"], s["correction"], s["target"]): s["rows"] for s in states["series"]}
    c, s_ = math.cos(OBLIQUITY_J2000), math.sin(OBLIQUITY_J2000)

    def to_ecliptic(v):
        return [v[0], c * v[1] + s_ * v[2], -s_ * v[1] + c * v[2]]

    rungs = []

    def rung(name, unit_name, what, pairs):
        bodies = []
        for code in SPICE_TARGETS:
            worst = None
            for key_a, key_b, transform in pairs:
                a, b = by.get(key_a + (code,)), by.get(key_b + (code,))
                if a is None or b is None:
                    continue
                for k, jd in enumerate(instants):
                    va, vb = transform(a[k][:3]), b[k][:3]
                    value = angle(va, vb)
                    if worst is None or value > worst[0]:
                        worst = (value, jd, math.dist(va, vb), f"{key_a[3]} at {key_a[1].upper()}")
            if worst is not None:
                bodies.append({"target": code, "name": TARGETS[code][0], "compared": len(instants) * len(pairs),
                               "worst": worst[0], "at_jd": worst[1], "position_km": worst[2], "correction": worst[3]})
        if bodies:
            rungs.append({"rung": name, "unit": unit_name, "what": what, "bodies": bodies})

    same = lambda v: v  # noqa: E731
    rung("de441_against_de440", "arcsec",
         "the geocentric direction over DE441 against DE440, for geometric (NONE, at the TDB epoch), converged light time (CN) and CN+S (at the TT epoch), in J2000; the worst over the three, with the correction it falls under",
         [(("de441", "tdb", "J2000", "NONE"), ("de440", "tdb", "J2000", "NONE"), same),
          (("de441", "tt", "J2000", "CN"), ("de440", "tt", "J2000", "CN"), same),
          (("de441", "tt", "J2000", "CN+S"), ("de440", "tt", "J2000", "CN+S"), same)])
    rung("one_iteration_against_converged", "arcsec",
         "spkezr LT (one Newtonian light-time iteration) against CN (converged), and LT+S against CN+S, over DE440 in J2000: what the single iteration costs",
         [(("de440", "tt", "J2000", "LT"), ("de440", "tt", "J2000", "CN"), same),
          (("de440", "tt", "J2000", "LT+S"), ("de440", "tt", "J2000", "CN+S"), same)])
    rung("ecliptic_against_equator", "arcsec",
         "each J2000 state turned about x by 84381.448 arcsec against the ECLIPJ2000 state SPICE gives for the same correction and epoch: a frame round trip, which agrees to rounding",
         [(("de440", "tdb", "J2000", "NONE"), ("de440", "tdb", "ECLIPJ2000", "NONE"), to_ecliptic),
          (("de440", "tt", "J2000", "LT"), ("de440", "tt", "ECLIPJ2000", "LT"), to_ecliptic),
          (("de440", "tt", "J2000", "LT+S"), ("de440", "tt", "ECLIPJ2000", "LT+S"), to_ecliptic)])
    rotations = []
    for name in ("tod", "mecl"):
        worst = (-1.0, None)
        for k, m in enumerate(states["of_date"][name]):
            err = max(abs(sum(m[3 * i + n] * m[3 * j + n] for n in range(3)) - (1.0 if i == j else 0.0))
                      for i in range(3) for j in range(3))
            if err > worst[0]:
                worst = (err, instants[k])
        rotations.append({"rotation": name, "rows": len(states["of_date"][name]),
                          "worst_departure_from_orthonormal": worst[0], "at_jd": worst[1]})
    return {
        "schema": "teistro-conformance/jpl-cspice-self-check/1",
        "recorded": states["recorded"],
        "note": "CSPICE measured against itself, from cspice/states.json alone, so --verify reproduces it without kernels. A rung is the worst angular separation of two directions over every instant, with the instant and the distance between the two positions. Nothing here alters a recorded value.",
        "rungs": rungs,
        "rotations": rotations,
    }


# --------------------------------------------------------------------------
# Recording, rebuilding and verifying. The CSPICE half is the default; the
# Horizons half needs --horizons and is kept apart, with its own manifest.

CSPICE_FILES = ("cspice/states.json", "cspice/self-check.json")
HORIZONS_FILES = ("horizons/vectors.json", "horizons/observer.json", "self-check.json")
HORIZONS_MANIFEST = JPL / "horizons" / "manifest.json"


def counts_cspice(manifest: dict, states: dict) -> dict:
    return {"instants": len(manifest["instants"]), "cspice_series": len(states["series"]),
            "cspice_rows": sum(len(s["rows"]) for s in states["series"])}


def counts_horizons(hmanifest: dict, vectors: dict, observer: dict) -> dict:
    return {
        "queries": len(hmanifest["queries"]),
        "vector_series": len(vectors["series"]),
        "vector_rows": sum(len(s["rows"]) for s in vectors["series"]),
        "observer_series": len(observer["series"]),
        "observer_rows": sum(len(s["rows"]) for s in observer["series"]),
    }


def cspice_manifest(recorded: str, sp, kernels: list[dict], chosen: list[dict]) -> dict:
    return {
        "schema": "teistro-conformance/jpl-manifest/1",
        "recorded": recorded,
        "recorder": {"script": "tools/record_jpl.py", "version": RECORDER_VERSION, "python": sys.version.split()[0],
                     "spiceypy": SPICEYPY_VERSION, "cspice": sp.tkvrsn("TOOLKIT")},
        "kernels": kernels,
        "kernel_notes": "Kernels are not kept here: they are NAIF's files, at the URLs given, identified by SHA-256. No planetary constants kernel is loaded, because no body-fixed frame enters a geocentric state.",
        "instants": chosen,
        "files": {},
        "counts": {},
    }


def horizons_manifest(recorded: str, queries: list[dict]) -> dict:
    return {
        "schema": "teistro-conformance/jpl-horizons-manifest/1",
        "recorded": recorded,
        "instants": "the instants of jpl/manifest.json",
        "horizons": {"endpoint": ENDPOINT, "documentation": "https://ssd-api.jpl.nasa.gov/doc/horizons_file.html",
                     "documented_version": FILE_API_VERSION,
                     "why_post": "the GET endpoint (https://ssd.jpl.nasa.gov/api/horizons.api) answered HTTP 502 to a TLIST of 60 or more instants in a URL; the file endpoint takes the same settings as a batch input file and accepts the whole list",
                     "ephemeris": "DE441, as every response header states for the planetary bodies ({source: DE441}); body centres of Mars to Pluto come from the satellite ephemerides each header names"},
        "queries": queries,
        "files": {},
        "counts": {},
    }


def read(name: str) -> dict:
    return json.loads((JPL / name).read_text(encoding="utf-8"))


def horizons_inputs(manifest: dict, hmanifest: dict) -> dict:
    return {"instants": manifest["instants"], "recorded": hmanifest["recorded"]}


def record(args) -> int:
    kernels_dir = Path(args.kernels).resolve()
    de441 = Path(args.de441).resolve() if args.de441 else None
    sp = spice(kernels_dir, de441)
    if (JPL / "manifest.json").exists() or (RAW.exists() and any(RAW.iterdir())):
        sys.exit(f"{JPL} already holds a recording: a recording starts from nothing")
    recorded = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    chosen = instants(sp)
    print(f"{len(chosen)} instants", file=sys.stderr)
    manifest = cspice_manifest(recorded, sp, kernel_entries(kernels_dir, de441), chosen)
    states = spice_states(sp, manifest, kernels_dir, de441)
    for name, document in (("cspice/states.json", states), ("cspice/self-check.json", cspice_self_check(states))):
        manifest["files"][name] = sha256(write(JPL / name, document))
    manifest["counts"] = counts_cspice(manifest, states)
    write(JPL / "manifest.json", manifest)
    print(json.dumps(manifest["counts"]), file=sys.stderr)
    if not args.horizons:
        return 0
    jds = [i["jd"] for i in chosen]
    recorder = Recorder()
    series = [("vectors", c, t) for c, ts in (("500@399", GEOCENTRIC), ("@0", BARYCENTRIC)) for t in ts]
    series += [("observer", "500@399", t) for t in GEOCENTRIC]
    series += [("observer", f"coord@399:{s['name']}", t) for s in SITES for t in TOPOCENTRIC]
    for kind, centre, code in series:
        qid = f"{kind}/{centre}/{code}"
        print(qid, file=sys.stderr)
        recorder.ask(qid, horizons_params(kind, centre, code), jds)
        time.sleep(1.0)
    write_horizons(manifest, horizons_manifest(recorded, recorder.queries), states)
    return 0


def write_horizons(manifest: dict, hmanifest: dict, states: dict) -> None:
    """The Horizons files, from the raw responses on disk, exactly as verify rebuilds them."""
    grouped = load_answers(hmanifest["queries"])
    inputs = horizons_inputs(manifest, hmanifest)
    vectors, observer = build_vectors(inputs, grouped), build_observer(inputs, grouped)
    outputs = {"horizons/vectors.json": vectors, "horizons/observer.json": observer,
               "self-check.json": self_check(vectors, observer, states)}
    for name, document in outputs.items():
        hmanifest["files"][name] = sha256(write(JPL / name, document))
    hmanifest["counts"] = counts_horizons(hmanifest, vectors, observer)
    write(HORIZONS_MANIFEST, hmanifest)
    print(json.dumps(hmanifest["counts"]), file=sys.stderr)


def rebuild(args) -> int:
    """Rewrite the derived files from the recorded states (and, with
    --horizons, from the kept responses), never asking Horizons anything:
    for a change to how the recording is laid out or measured, never to its
    values."""
    manifest = read("manifest.json")
    states = read("cspice/states.json")
    manifest["files"]["cspice/states.json"] = sha256((JPL / "cspice/states.json").read_bytes())
    manifest["files"]["cspice/self-check.json"] = sha256(write(JPL / "cspice/self-check.json", cspice_self_check(states)))
    manifest["counts"] = counts_cspice(manifest, states)
    write(JPL / "manifest.json", manifest)
    print("rebuilt cspice/self-check.json from cspice/states.json")
    if args.horizons:
        write_horizons(manifest, read("horizons/manifest.json"), states)
        print("rebuilt the Horizons files from the kept responses")
    return 0


def same_bytes(name: str, document) -> bool:
    return (dumps(document) + "\n").encode("utf-8") == (JPL / name).read_bytes()


def verify(args) -> int:
    failures = []
    manifest = read("manifest.json")
    for name, digest in manifest["files"].items():
        if sha256((JPL / name).read_bytes()) != digest:
            failures.append(f"{name}: the SHA-256 differs from the manifest")
    states = read("cspice/states.json")
    if args.kernels:
        kernels_dir = Path(args.kernels).resolve()
        de441 = Path(args.de441).resolve() if args.de441 else None
        recomputed = spice_states(spice(kernels_dir, de441), manifest, kernels_dir, de441)
        if not same_bytes("cspice/states.json", recomputed):
            failures.append("cspice/states.json: not what CSPICE computes over the named kernels")
    if not same_bytes("cspice/self-check.json", cspice_self_check(states)):
        failures.append("cspice/self-check.json: not what cspice/states.json produces")
    if manifest["counts"] != counts_cspice(manifest, states):
        failures.append("the manifest's counts disagree with cspice/states.json")
    what = "the CSPICE states" + (" (recomputed)" if args.kernels else "") + " and their self-check"
    if args.horizons:
        hmanifest = read("horizons/manifest.json")
        listed = {q["file"] for q in hmanifest["queries"]}
        for path in sorted(RAW.iterdir()):
            if rel(path) not in listed:
                failures.append(f"a raw response the manifest does not list: {rel(path)}")
        for name, digest in hmanifest["files"].items():
            if sha256((JPL / name).read_bytes()) != digest:
                failures.append(f"{name}: the SHA-256 differs from the Horizons manifest")
        try:
            grouped = load_answers(hmanifest["queries"])
        except (OSError, ValueError) as error:
            failures.append(str(error))
            grouped = None
        if grouped is not None:
            inputs = horizons_inputs(manifest, hmanifest)
            vectors, observer = build_vectors(inputs, grouped), build_observer(inputs, grouped)
            for name, document in (("horizons/vectors.json", vectors), ("horizons/observer.json", observer),
                                   ("self-check.json", self_check(vectors, observer, states))):
                if not same_bytes(name, document):
                    failures.append(f"{name}: not what the kept responses and the recorded states produce")
            if hmanifest["counts"] != counts_horizons(hmanifest, vectors, observer):
                failures.append("the Horizons manifest's counts disagree with its files")
        what += f", and {len(hmanifest['queries'])} Horizons responses with the files they produce"
    for failure in failures:
        print(f"FAIL  {failure}")
    print(f"verified {what}: {len(failures)} failure(s)")
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--verify", action="store_true", help="check the recording offline instead of making one")
    parser.add_argument("--rebuild", action="store_true", help="rewrite the derived files from the recorded data, offline")
    parser.add_argument("--horizons", action="store_true",
                        help="also query (or verify, or rebuild) the Horizons half; off by default")
    parser.add_argument("--kernels", help="the directory holding de440.bsp and naif0012.tls (required to record)")
    parser.add_argument("--de441", help="the directory holding de441_part-1.bsp and de441_part-2.bsp")
    args = parser.parse_args(argv)
    if args.verify:
        return verify(args)
    if args.rebuild:
        return rebuild(args)
    if not args.kernels:
        parser.error("recording needs --kernels")
    return record(args)


if __name__ == "__main__":
    sys.exit(main())
