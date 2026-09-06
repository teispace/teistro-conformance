# Changelog

Every release answers one question first, because it is the only one a
corpus's consumer actually needs:

> **Does this move any recorded value, and by how much?**

A consumer measures itself against these numbers and may have published a
score. So each entry begins with **Values**, and "none" is an answer that
has to be earned by having looked.

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
