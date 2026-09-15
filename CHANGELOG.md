# Changelog

Every release answers one question first, because it is the only one a
corpus's consumer actually needs:

> **Does this move any recorded value, and by how much?**

A consumer measures itself against these numbers and may have published a
score. So each entry begins with **Values**, and "none" is an answer that
has to be earned by having looked.

## 0.5.0 — 2026-09-15

**Values:** none moved; the Ashtakavarga of 77 charts is new.

`baseline/ashtakavarga/`: the engine's Ashtakavarga for each of the 77
fixtures that record their foundation and positions, computed from the
recorded lagna and seven grahas' signs, which each file repeats as `inputs`:
each graha's bindus by sign, their sum, the sum after the trine reduction,
and under each of the engine's three Ekadhipatya methods (`classical`,
`zero`, `transfer`) the fully reduced sum, the rashi pinda by sign and each
graha's graha and yoga pindas. `validate.py` checks the inputs against the
fixture and the sum against the bindus.

The engine's reductions and pindas are its reading: it reduces the sum of the
seven where BPHS reduces each graha's own Ashtakavarga, and these files record
what it does.

## 0.4.0 — 2026-09-15

**Values:** none moved; 148 are new.

`baseline/kalachakra/`: the engine's Kalachakra dasha for each of the 93
fixtures that record a dasha, under each balance method recorded — the
balance, the tree of 27 mahadashas and their antardashas as `[path,
sign_index, lord, start_jd, end_jd]` rows, and the periods running at the
fixture's two reference instants. The manifest carries the rule data the
engine ran once: every sign's years and the four pada tables with the
nakshatras each serves. Computed from the fixtures' recorded Moon and
nakshatra span, as the dasha systems were; `validate.py` checks each file
against its fixture's Moon, nakshatra and pada, and that the tables serve
every nakshatra once.

The engine's Kalachakra is one reading at several forks where the sources
differ — which table five nakshatras take, the balance, and what follows
the ninth mahadasha — and these files record what it does.

## 0.3.0 — 2026-09-15

**Values:** none moved; 616 are new.

`baseline/rashi-dashas/`: the engine's eight sign-based (Jaimini) dashas —
Chara, Narayana, Padanadhamsa, Trikona, Drig, Shoola, Niryana Shoola and
Mandooka — for each of the 77 fixtures that record their foundation and
positions: the tree to antardashas as `[path, sign_index, lord, start_jd,
end_jd]` rows and the chain of three levels at two reference instants.

Each was computed **from the fixture's recorded chart** — the lagna's sign,
the nine grahas' signs and dignities, and the arudha and navamsha lagnas —
which every file repeats as `inputs`, and `validate.py` checks field by
field against the fixture as well as by hash and schema. The engine's
rules are one reading among several schools for most of these systems;
the files record what it does, not what a text says.

`validate.py`'s two derived corpora now share one checker.

## 0.2.0 — 2026-09-15

**Values:** none moved; 1184 are new.

`baseline/dasha-systems/`: the eight nakshatra-seeded dasha systems beside
Vimshottari — Ashtottari, Yogini, Dwadashottari, Panchottari, Shatabdika,
Chaturashiti-sama, Dwisaptati-sama and Tribhagi — for every one of the 93
fixtures that records a dasha, under each balance method that fixture
records: 1184 answers. Each holds the system's rule data (the sequence, the
reference nakshatra, the count's direction, the window, the offset and, for
Tribhagi, the scale and rounds), the first lord, the balance, the tree to
antardashas and the chain of four levels at the fixture's two reference
instants.

They were computed **from each fixture's recorded inputs** — the Moon's
sidereal longitude, the birth instant and the recorded nakshatra span — by
the same engine version that recorded the charts, so no astronomy was
recomputed and no existing value could move. Two schemas describe the files
and their manifest, and `validate.py` checks every file's hash, its schema,
and that it answers exactly the methods its fixture records.

## 0.1.1 — 2026-09-06

**Values:** none. Documentation only.

`baseline/README.md`: what each of the 55 charts is for, what each of the
13 settings profiles changes and which sections it exports, the whole
provenance the manifest records, and what every section of a fixture
holds, field by field. It was written where the corpus was assembled and
belonged with the corpus rather than with its first consumer.

## 0.1.0 — 2026-09-06

**Values:** the first release; every value is new.

The corpus separated from the Teistro SDK, where it was assembled, into
its own repository under CC0-1.0 with a version of its own. Nothing was
recomputed in the move: every file is byte for byte the file the SDK
carried, and the SDK's own gate proves it after the move as it did
before.

- `baseline/`: 115 fixtures over 55 charts under 13 settings profiles,
  from an established open-source engine over Swiss Ephemeris 2.10.03
  (recorded 2026-09-04), each with the complete profile it was computed
  under, that profile's hash, and provenance down to the ephemeris data
  files' hashes and every time-zone database version.
- `baseline/names.json`: the same engine's entity name tables, 40 types
  and 383 entities in four languages (2026-09-06).
- `official/`: Nepal's national panchanga committee's printed Rashtriya
  Panchangam for BS 2082 and 2083 — 24 sankranti instants, four rows of
  places at sunrise, 22 days of sunrise and sunset, eight tithi ends —
  read from the published page images with the URLs, page numbers and
  reading date recorded (2026-09-05). Rank 1 for the official calendar.
- `teimeris/`: Teimeris 0.1.0 in its corrected profile — 1044 ayanamsha
  rows, 1260 house rows, 128 star records, 176 phenomena rows, 49
  sidereal-time rows — re-recorded 2026-09-06 after six discrepancies
  found against it were fixed upstream.
- `tolerances.json`: the one central tolerance file, keyed by field and
  provider class. Provisional: the bands are stated but not yet measured
  against real runs, and a consumer should say so when reporting against
  them.
- `schema/`: JSON Schemas for a chart fixture, a corpus manifest, the
  tolerance file, and a conformance report.
- `validate.py` and its workflow: the corpus checks itself on every push.
