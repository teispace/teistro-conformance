# Teistro Conformance

A corpus of recorded astrological and astronomical answers, with the
settings each was computed under, so that an implementation can be
measured against something other than its own opinion.

Version 0.12.0. Dedicated to the public domain under
[CC0-1.0](LICENSE) — there is no attribution requirement, because
attribution is friction for an implementation checking itself, and a
standard nobody can use freely is not a standard.

## What is in it

| directory | what it holds | evidence rank |
|---|---|---|
| [`baseline/`](baseline) | 115 fixtures over 55 charts under 13 settings profiles, from an established open-source engine over Swiss Ephemeris 2.10.03: positions, houses, vargas, panchanga and dashas, each with the complete profile and its hash. [What each chart is for, what each profile changes and what every section holds](baseline/README.md) | 2 |
| [`baseline/dasha-systems/`](baseline/dasha-systems) | the same engine's eight other nakshatra-seeded dasha systems for each of the 93 fixtures that record a dasha, computed from the fixture's recorded Moon and nakshatra span: 1184 answers | 2 |
| [`baseline/rashi-dashas/`](baseline/rashi-dashas) | the same engine's eight sign-based (Jaimini) dashas for each of the 77 fixtures that record their foundation and positions, computed from the fixture's recorded chart: 616 answers | 2 |
| [`baseline/kalachakra/`](baseline/kalachakra) | the same engine's Kalachakra dasha for each of the 93 fixtures that record a dasha, computed from the recorded Moon and nakshatra span, with its sign years and pada tables in the manifest: 148 answers | 2 |
| [`baseline/ashtakavarga/`](baseline/ashtakavarga) | the same engine's Ashtakavarga for each of the 77 fixtures that record their foundation and positions, computed from the recorded signs under each of its three Ekadhipatya methods | 2 |
| [`baseline/vimshopaka/`](baseline/vimshopaka) | the same engine's Vimshopaka for each of the 93 fixtures that record their divisional charts, computed from the recorded varga signs under its four schemes | 2 |
| [`baseline/shadbala/`](baseline/shadbala) | the same engine's Shadbala for each of the 71 fixtures that record their chart, day, houses and divisional charts, computed from those recorded values | 2 |
| [`baseline/bhava-bala/`](baseline/bhava-bala) | the same engine's Bhava bala for the same 71 charts, computed from the recorded lagna and houses and its Shadbala of each | 2 |
| [`baseline/yogas/`](baseline/yogas) | the same engine's 605 yoga rules, in its own condition language, and which are present for each of the 93 fixtures that record their positions, computed from the recorded chart: 5552 presences | 2 |
| [`baseline/doshas/`](baseline/doshas) | the same engine's 52 natal dosha rules, in its own shape, and which are present for each of the 93 fixtures that record their positions, computed from the recorded chart and, for 77, the recorded panchanga: 1024 presences with their severity, cancellations and net status | 2 |
| [`baseline/names.json`](baseline/names.json) | the same engine's entity name tables: 40 types, 383 entities, four languages | 2 |
| [`pyjhora/vimshottari/`](pyjhora) | PyJHora 4.8.7's Vimshottari for 53 of the 55 charts, run as a black box: its Moon, and every mahadasha and antardasha under five year durations, with the two charts it refuses listed. [What to know before comparing](pyjhora/README.md) | 3 |
| [`official/`](official) | what Nepal's national panchanga committee printed in its Rashtriya Panchangam for BS 2082 and 2083 — 24 sankranti instants, four rows of places at sunrise, 22 days of sunrise and sunset, eight tithi ends — read from the published page images, with the file URLs and page numbers | 1 |
| [`teimeris/`](teimeris) | Teimeris 0.1.0 in its corrected profile: 1044 ayanamsha rows, 1260 house rows, 128 star records, 176 phenomena rows, 49 sidereal-time rows, each with the geometry it was read from | 2 |
| [`jpl/`](#the-jpl-recording) | JPL's ephemeris itself: geocentric states computed by CSPICE over DE440 and DE441 over a stratified grid across 1600 to 2400 and a set of adversarial instants, with SPICE's of-date rotations, and CSPICE measured against itself. The counts are in `corpus.json` and `jpl/manifest.json` | 1 |

**Evidence rank** is how much weight an answer carries when two sources
disagree: **1** a classical text or an institution's own publication,
**2** an established implementation, **3** another implementation, **4**
anything else. A rank is a claim about provenance, not about accuracy: a
committee's printed sunrise is rank 1 even where a modern ephemeris
disagrees with it, and the disagreement is the interesting part.

## The JPL recording

`jpl/` is the corpus's truth rung. ADR-0021 in the Teistro SDK makes JPL's
ephemeris the final authority, because agreement with another
implementation proves consistency, not correctness. What is published here
is computed from JPL's own files: NAIF's CSPICE Toolkit reading DE440 and
DE441.

- `cspice/states.json`: `spkezr` states of the Sun, the Moon, Mercury,
  Venus and the system barycentres of Mars to Pluto, from the geocentre.
  Over `de440.bsp` they are geometric, with one-iteration and converged
  light time, with and without stellar aberration, in J2000 and
  ECLIPJ2000. The same geometric and converged states are given over
  DE441, together with SPICE's IAU 1976/1980 of-date rotations at each
  instant.
- `cspice/self-check.json`: CSPICE measured against itself, from the states
  alone. It gives DE441 against DE440 per body, one-iteration light time
  against converged, ECLIPJ2000 against J2000 turned by the fixed
  obliquity, and how far each of-date rotation departs from orthonormal.
  Each is the worst over every instant, with the instant it falls at.
- `manifest.json`: the recording date, the versions, the kernels by URL and
  SHA-256, the instants with the reason each was chosen, and the files'
  hashes.

What to know before comparing:

- **The geometric rung isolates the ephemeris.** A geometric state carries
  no light time, aberration or deflection, and an instant is read as TDB.
  A converged-light-time state (`CN`) is the astrometric place, with the
  instant read as TT and converted by SPICE.
- **CSPICE's `LT` is one iteration.** It costs milliarcseconds against
  converged light time (`CN`) for the inner planets. Both are recorded.
- **SPICE applies no gravitational deflection**, so a `CN+S` state is not an
  apparent place. No band in `tolerances.json` holds an apparent place
  against this half.
- **DE441 is not DE440.** Over DE441 the Moon departs from DE440 by a
  fraction of an arcsecond at the ends of the range. The self-check shows it
  per body, so a comparison can say which ephemeris it was made against.
- **A Horizons half has been recorded and is withheld.** JPL Horizons'
  geometric states and astrometric and apparent places at the same
  instants, with every raw response, have been recorded and measured
  against these states. They stay out of the corpus until JPL has given
  permission to republish what Horizons serves. The recorder keeps the
  code that records them, behind `--horizons`, which is off by default.

To rerun or check the recording:

```sh
python3 -m venv .venv && .venv/bin/pip install spiceypy==8.2.0
.venv/bin/python -I tools/record_jpl.py --kernels KERNELS --de441 DE441
python3 -I tools/record_jpl.py --verify
.venv/bin/python -I tools/record_jpl.py --verify --kernels KERNELS --de441 DE441
```

`KERNELS` holds `de440.bsp` and `naif0012.tls`, and `DE441` holds
`de441_part-1.bsp` and `de441_part-2.bsp`, all from NAIF at the URLs in the
manifest. Recording asks no web service. `--verify` needs only the standard
library: it checks every hash, and checks byte for byte that the self-check
is what the states produce. Given the kernels, it also recomputes the
states byte for byte. `validate.py` runs the same offline checks.

## The contract

- **A fixture carries the settings it was computed under**, complete, not
  as a patch — a fixture must be reproducible from itself — with the hash
  of those settings asserted in the file and in the manifest. Comparing
  numbers computed under different settings is the most common way to be
  confidently wrong.
- **Every expected value is cited**: to a text, to a tool and version, or
  to an institution. `provenance` records the engine, the ephemeris
  library and its data files with their hashes, every time-zone database
  version, and the conventions the numbers follow — which index starts at
  zero, what an angle is measured from, how a day is bounded.
- **Tolerances are central**, in [`tolerances.json`](tolerances.json),
  keyed by field and by the class of ephemeris a run used. Never per
  fixture: a tolerance written beside a fixture is a tolerance that was
  widened to make that fixture pass.
- **A fixture that is not in a manifest is not in the corpus**, and a file
  beside a manifest that it does not list is an error.
- **An absence with a reason is evidence.** What an export asked for and
  did not get stays in the manifest's `failures`.

## Using it

Pin it. As a submodule:

```sh
git submodule add https://github.com/teispace/teistro-conformance fixtures
git -C fixtures checkout v0.12.0
```

or read [`corpus.json`](corpus.json), which names the version, what each
corpus is, where it came from and how much of it there is.

A conformance report follows
[`schema/report.schema.json`](schema/report.schema.json): it says which
corpus version and commit it was run against, which implementation and
which class of ephemeris, and, for every fixture, every field compared
and by how much each missed. A report that lists only its failures cannot
be told from a report that compared nothing.

**Publish your own score, never someone else's.** A score computed for
another implementation by its competitor is not evidence.

## Validating it

```sh
python3 -m venv .venv && .venv/bin/pip install jsonschema
.venv/bin/python validate.py
```

It checks every fixture against its schema, that each carries the
settings hash of the profile it claims, that every section it lists is
present, that the manifest lists every file and no file is unlisted, and
that the tolerance file is well formed. The same script runs in CI on
every push.

## Adding a fixture

1. Say **why** in the fixture's `why` field. An entry nobody can state the
   purpose of is an entry nobody can maintain.
2. Record the whole `provenance`, including the data files' hashes and
   every version that could have moved a number.
3. Put the complete settings in, and the hash.
4. List it in the manifest and run `validate.py`.
5. A fixture that reproduces a defect lands **before** the fix.

Correcting a recorded value is a corpus version bump and a changelog
entry saying what moved and why, under the same rule the consumers use:
does this move any number?

## Versioning

Semantic versioning, independent of any consumer. A **major** bump
changes a schema or removes a fixture; a **minor** bump adds fixtures or
a corpus; a **patch** corrects prose or metadata that moves no number. A
corrected *value* is a minor bump at least, and the changelog says which
values moved.

## Where it came from

Built for the [Teistro SDK](https://github.com/teispace/teistro-sdk),
which consumes it as a pinned submodule and publishes its own score
against it. The SDK is one consumer; the corpus is not its property, and
a fixture is never changed to make a consumer pass.
