# The baseline corpus

115 fixtures over 55 charts under 13 settings profiles, recorded from an
established open-source astrology engine (version 1.8.0) computing over
Swiss Ephemeris 2.10.03. Evidence rank 2.

The charts were chosen to be adversarial rather than typical, and each
fixture says in its `why` field what it is there for.

```text
baseline/
  manifest.json      provenance, the thirteen settings profiles with their hashes, every fixture
  charts/            55 fixtures under the default profile, one per chart: <id>-<place>-<date>.json
  variants/          60 fixtures of the same charts under twelve alternative profiles: <id>-<place>-<date>--<profile>.json
```

The export script lives in the recording engine's own repository, in that
repository's language, and reads its built packages and its ephemeris data
files. It is not part of this repository. The names
exporter beside it (`export-name-tables.mjs`) writes `names.json` from
the engine's entity registry the same way. To regenerate:
run it with `--out <a scratch directory>`, copy `charts/`, `variants/`
and `manifest.json` here, and run `python validate.py`. A
regeneration under a newer engine version is a corpus version bump, never
a silent overwrite (ADR-0022).

`dasha-systems/` is written by a third exporter beside those
(`export-dasha-vectors.mjs --corpus <this directory>`), which reads the
fixtures here rather than the ephemeris; see "The dasha systems" below.

## Provenance

Recorded in `manifest.json` and repeated in every fixture:

- engine version 1.8.0; Swiss Ephemeris 2.10.03 through its Node
  binding, with the three `.se1` files that cover 1800 to 2399 and their
  SHA-256 hashes; calculation flags `SEFLG_SWIEPH | SEFLG_SPEED |
  SEFLG_SIDEREAL`, plus `SEFLG_TOPOCTR` when the profile is topocentric;
  Delta T from the library's default model;
- time zones from tzdb 2026a as compiled into the Node runtime's ICU, the
  zone looked up from the coordinates; local mean time from the longitude
  when the input says so;
- the runtime (Node 26) and the decimal library the engine classifies
  with.

## The chart set

Fifty-five charts, chosen to be adversarial rather than typical. The
`tags` field of each fixture says why it is there.

| group | charts | what they exercise |
|---|---|---|
| Nepal and India | c001 to c012 | the default profile's home ground: pre-sunrise and post-sunset births, civil midnight, the +05:30 to +05:45 change of 1986 (and the fifteen minutes that did not exist), a leap day, local-mean-time eras (+05:41:16, +05:21:10), explicit LMT |
| unusual and half-hour zones | c013 to c015, c017, c022, c034 | +06:30, +04:30, +07:30, -10:30, +03:30 |
| southern hemisphere and the equator | c017, c018 to c021, c032, c033, c040 to c042, c044, c045 | southern seasons, the equator at 0.18°S, the date line at +13 and +14, the day Samoa skipped |
| Europe and history | c023 to c026, c030, c038 | LMT London 1830, British double summer time, Paris mean time at the 1900 century turn, 1945 summer time, the day Turkey stopped changing clocks, New York on local mean time |
| daylight-saving edges | c014, c031, c035 to c037, c045 | the first summer-time hour, the last half hour before a gap, an ambiguous local time resolved both ways, a southern fall-back ambiguity |
| high latitude and polar | c027 to c029, c043, c044 | 64°N at midsummer midnight, polar day and polar night at 69.6°N, 64.8°N, 54.8°S |
| altitude | c039, c041, c042 | 2 240 m, 3 640 m and 2 850 m: the topocentric Moon |
| the range of the data files | c046 to c048 | 2350, the first day of 1800, the last days of 2399 |
| found by search | c049 to c055 | instants placed to the second at a boundary, in the topocentric frame the natal chart uses: the Moon at a nakshatra edge and at a pada edge where the geocentric Moon is still on the other side (so the dasha lord or the pada depends on the frame), the last second before and the first after the Sun's sidereal Aries ingress of 2020, the first second after a Mercury station, the ascendant at a sign edge, the first second after a new moon |

Every chart is inside 1800 to 2399, so every position comes from the
`.se1` files; `foundation.ephemeris_source` proves it per fixture.

## The settings profiles

`default` is the recording engine's shipped default: Lahiri, sidereal,
whole-sign houses, drik, the mean node, sunrise at the refracted disc
edge, the spatial dasha balance, eight chara karakas, the classical
ekadhipatya reduction, topocentric positions. Twelve variants change one
thing each (or the ayanamsha) and export only the sections that thing
affects:

| profile | change | sections | charts |
|---|---|---|---|
| `temporal` | dasha balance by the Moon's real entry and exit instants | foundation, dashas | 10 |
| `true-node` | the true node | positions, vargas | 6 |
| `geocentric` | no topocentric correction | positions, vargas, dashas | 6 |
| `placidus` | Placidus houses | houses | 8 |
| `raman`, `krishnamurti`, `true-chitra`, `fagan-bradley` | the ayanamsha | all | 4 each |
| `tropical` | the tropical zodiac | positions, houses, vargas | 4 |
| `surya-bija` | the classical Surya Siddhanta engine with the node correction | foundation, positions, vargas, panchanga, dashas | 4 |
| `surya` | the same engine, uncorrected | as above | 2 |
| `sunrise-geometric` | sunrise at the disc centre on the true horizon | foundation | 4 |

## The fixture schema (`teistro-conformance/baseline-chart/1`)

Top level: `schema`, `id`, `chart`, `title`, `tags`, `why`, `provenance`,
`input`, `settings`, `settings_hash`, `sections`, then one object per
listed section.

- `input.place` (coordinates, altitude in metres), `input.local` (the
  civil date and time as entered, the LMT flag, the daylight-saving
  choice), `input.search` (for the searched charts: the body, the target
  longitude, the crossing instant found and the whole second chosen) and
  `input.resolved` (the UTC instant, the Julian Day in UT, the zone
  offset in whole minutes, the zone id, the resolver's source and era,
  its warning codes).
- `settings` names every knob; `settings_hash.canonical` is the sorted
  `key=value` list the engine hashes and `settings_hash.value` its
  SHA-256 truncated to 16 hex characters, so the recipe is reproducible.
- `foundation`: the Julian Day, Delta T, the ayanamsha value, the
  ephemeris source, sunrise and sunset for the local civil day and its
  neighbours, the sunrise that anchors the Lagna, the Lagna, the
  panchanga day (which half-arc holds the birth, its bounds, the weekday),
  the hora and abda lords, the upagrahas, the arudha and navamsha Lagna
  signs, the birth timing (ishtakaal, bhayat, bhabhoga in ghati and pala)
  and the engine's own version block with its profile hash.
- `positions.bodies`: the ten bodies in canonical order, each with the
  sidereal and tropical longitudes, latitude, speed, distance, degrees in
  sign, sign, whole-sign house, nakshatra, its lord, pada and akshara,
  retrograde, dignity, moolatrikona, combustion, distance from the Sun,
  vargottama, the three friendship views, the baladi avastha, the
  boundary flags and the jagradadi, deeptadi and lajjitadi avasthas with
  planetary war. `positions.outer`: Uranus, Neptune and Pluto, geocentric.
- `houses`: the selected system's cusps, ascendant, MC and degeneracy
  flag, the same for all 22 systems the engine offers (`all_systems`),
  the Bhava Chalit result, the special lagnas, the arudha padas and the
  chara karakas under both schemes.
- `vargas`: for each of the 21 divisional charts, the sign of every body.
- `panchanga`: the five limbs at the birth instant, from the natal
  (topocentric) Sun and Moon.
- `panchanga_day`: the daily panchanga of the local civil date at the
  place: sunrise and sunset, every tithi, nakshatra, yoga and karana with
  its start and end instants, the inauspicious periods, the choghadiya and
  hora sequences, Abhijit and Brahma muhurta, the lunar month under both
  conventions, panchaka, moonrise and moonset, the Moon and Sun signs,
  the ayana, the disha shool and the five muhurta yogas, plus the Bikram
  Sambat date.
- `dashas`: Vimshottari with the year length (365.25 days), the sequence,
  the starting lord and the Moon's elapsed nakshatra fraction, then per
  balance method (`spatial` and `temporal` under the default profile): the
  remaining fraction, the nakshatra's real entry and exit instants
  (temporal), the balance breakdown, the tree as pre-order rows `[path,
  lord, start_jd, end_jd]` to depth 3 (spatial) or 2 (temporal), the
  direct children at chosen paths down to level 5, and the active chain
  of five levels at two reference instants (birth plus 10 000 days, and
  2026-09-04T00:00:00Z).

Conventions: angles are degrees as computed, `f64`, never rounded;
instants are Julian Days in UT; sign index 0 is Aries; nakshatra index 0
is Ashwini; pada 1 to 4; houses 1 to 12; `weekday_swe` counts Monday as
0. Longitudes are sidereal unless the field says tropical. A body's
nakshatra, pada and sign in the fixture are the engine's classification
of its own `f64`, made with decimal arithmetic and lower-inclusive
boundaries; the harness classifies the same `f64` with the SDK's integer
path (ADR-0016) and expects the same answer.

## The dasha systems (`teistro-conformance/baseline-dasha-systems/1`)

`dasha-systems/charts/` and `dasha-systems/variants/` hold one file for each
fixture that records `dashas`, under the fixture's own file name. Each file
answers the eight nakshatra-seeded systems beside Vimshottari from **the
fixture's recorded inputs**: the Moon's sidereal longitude
(`dashas.moon_sidereal_longitude_deg`), the birth instant
(`input.resolved.jd_ut`) and, for a temporal balance, the Moon's recorded
span in its nakshatra (`dashas.methods.temporal.nakshatra_span`). The
engine's balance service is replaced by one that answers from those values
with the engine's own formula, so these files are a property of the dasha
arithmetic and cannot drift with the ephemeris.

Per system: the rule data (`sequence` of lords and years, `total_years` the
sub-period shares are over, `reference_nakshatra`, `count` from or to it,
the `span` of nakshatras a lord covers, the `offset` added before taking the
group round the sequence, and Tribhagi's `scale`: two thirds, twice round);
then per recorded balance method the `first_lord`, the `balance` written as
the chart fixtures write it, the tree as pre-order rows `[path, lord,
start_jd, end_jd]` to depth 2, and the chain of four levels at each of the
fixture's `reference_instants_jd` as rows `[level, index, lord, start_jd,
end_jd]`, empty once the cycle has ended.

| system | lords | years | reference | count | span | offset |
|---|---|---|---|---|---|---|
| Ashtottari | 8 | 108 | Ardra | from | 3 | 0 |
| Yogini | 8 | 36 | Ashwini | from | 1 | 3 |
| Dwadashottari | 8 | 112 | Revati | to | 1 | 0 |
| Panchottari | 7 | 105 | Anuradha | from | 1 | 0 |
| Shatabdika | 7 | 100 | Revati | from | 1 | 0 |
| Chaturashiti-sama | 7 | 84 | Swati | from | 1 | 0 |
| Dwisaptati-sama | 8 | 72 | Mula | from | 1 | 0 |
| Tribhagi | 9 | 120 × 2/3, twice | Ashwini | from | 1 | 0 |

`dasha-systems/manifest.json` lists every file with its SHA-256, its fixture
and the methods it answers.

## The rashi dashas (`teistro-conformance/baseline-rashi-dashas/1`)

`rashi-dashas/charts/` and `rashi-dashas/variants/` hold one file for each
fixture that records its `foundation` and `positions`, under the fixture's
own file name, written by `export-rashi-dasha-vectors.mjs --corpus <this
directory>`. Each answers the engine's eight sign-based dashas from the
fixture's recorded chart, which the file repeats as `inputs`: the birth
instant, the lagna's sign, the arudha and navamsha lagnas' signs, and each
graha's sign and dignity. No year length is chosen per system: every one
uses 365.25 days (`year_length_days`), and none has a balance at birth.

Per system: the tree as pre-order rows `[path, sign_index, lord, start_jd,
end_jd]` to depth 2, and the chain of three levels at each of the
fixture's `reference_instants_jd` (the dasha fixtures' own, otherwise birth
plus 10 000 days and 2026-09-04T00:00:00Z) as rows `[level, index,
sign_index, lord, start_jd, end_jd]`, empty past the end of the cycle.

| system | starts from | order | years a sign |
|---|---|---|---|
| Chara | lagna | through the signs, forward for an odd lagna | the footed count to the stronger Jaimini lord |
| Narayana | lagna | as Chara | as Chara, one more for an exalted lord and one fewer for a debilitated one |
| Padanadhamsa | arudha lagna | as Chara, by the arudha lagna's parity | as Chara |
| Trikona | lagna | the trine groups from the lagna's, each group reversed for an even lagna | as Chara |
| Drig | the ninth house | the ninth, tenth and eleventh houses, each followed by the signs it aspects | as Chara |
| Shoola | lagna | as Chara | 9 |
| Niryana Shoola | navamsha lagna | as Chara, by its parity | 9 |
| Mandooka | lagna | back two signs at a time from the lagna, then from the sign before it | 7 movable, 8 fixed, 9 dual |

Every mahadasha divides into twelve equal antardashas starting from its own
sign, forward for an odd sign and back for an even one. Where a period is
counted to its lord, and in Mandooka, a mahadasha names the stronger of
Scorpio's or Aquarius's two lords (the one in a kendra from the sign when
only one is, else Ketu or Rahu); Shoola's and Niryana Shoola's mahadashas,
and every antardasha, name the first lord. Drig appends, in the zodiac's
order, any sign its houses and their aspects leave out.
`rashi-dashas/manifest.json` lists every file with its SHA-256.

## The Kalachakra (`teistro-conformance/baseline-kalachakra/1`)

`kalachakra/charts/` and `kalachakra/variants/` hold one file for each
fixture that records `dashas`, written by `export-kalachakra-vectors.mjs
--corpus <this directory>` from the same recorded inputs the dasha systems
read. Each records the Moon's longitude, nakshatra and pada, then per
recorded balance method the balance, the tree to antardashas as `[path,
sign_index, lord, start_jd, end_jd]` rows, and the periods running at the
two reference instants as `[level, index, sign_index, lord, start_jd,
end_jd]`.

`kalachakra/manifest.json` carries the rules once: `sign_years` (Aries to
Pisces) and four `tables`, each with the nakshatras it serves and its four
padas' nine signs. The Moon's nakshatra picks a table and its pada a row;
the first sign runs the unelapsed part of the pada of its years; after the
nine, the same nine run reversed, three cycles in all; each mahadasha's nine
antardashas begin from its own place and share it by their signs' years.

## The Ashtakavarga (`teistro-conformance/baseline-ashtakavarga/1`)

`ashtakavarga/charts/` and `ashtakavarga/variants/` hold one file for each
fixture that records its `foundation` and `positions`, written by
`export-ashtakavarga-vectors.mjs --corpus <this directory>` from the recorded
lagna and seven grahas' signs, repeated as `inputs`. Signs index from Aries.

`bav` holds each graha's bindus by sign, `sav` their sum and `sav_trikona` the
sum after the trine reduction (the least of each trine taken from all three).
`ekadhipatya` holds, for each of the engine's three methods, `sav_reduced`
(the sum after the Ekadhipatya reduction as well), `rashi_pinda` (the reduced
sum times each sign's measure, Virgo's 8) and each graha's `graha_pinda` (its
raw bindus times its measure) and `yoga_pinda` (that plus the rashi pinda of
its sign). The engine makes both reductions on the sum of the seven; BPHS
makes them in each graha's own Ashtakavarga, so these are the engine's values
and not the text's.

## The Vimshopaka (`teistro-conformance/baseline-vimshopaka/1`)

`vimshopaka/charts/` and `vimshopaka/variants/` hold one file for each fixture
that records its divisional charts through the D60, written by
`export-vimshopaka-vectors.mjs --corpus <this directory>` from the seven
grahas' recorded signs in the sixteen vargas (D1, D2, D3, D4, D7, D9, D10,
D12, D16, D20, D24, D27, D30, D40, D45, D60), repeated as `inputs`.

`dignity` is what the engine scores each graha by in each varga: exaltation,
debilitation, moolatrikona and own sign by sign alone, then the natural
friendship with the sign's lord. `scores` holds each graha's score under the
four schemes: the sum over the scheme's vargas of that dignity's Saptavargaja
virupas (45, 30, 22.5, 15, 7.5, 3.75, 1.875, 0) over 45 times the varga's
weight, rounded to hundredths. `vimshopaka/manifest.json` carries the weights.

## The Shadbala (`teistro-conformance/baseline-shadbala/1`)

`shadbala/charts/` and `shadbala/variants/` hold one file for each fixture that
records its foundation, positions, houses and divisional charts, written by
`export-shadbala-vectors.mjs --corpus <this directory>` from the recorded
chart, repeated as `inputs`: each of the seven grahas' sidereal longitude,
speed, house, sign and degrees in the sign; their signs in the D1, D2, D3, D7,
D9, D12 and D30; the birth instant and whether the engine counted it a day
birth; the weekday (`weekday_swe`, Monday 0); the day's sunrise and sunset and
the next day's sunrise; the ayanamsha; the hora and abda lords; the lagna's
longitude; and the house system, with the first, fourth, seventh and tenth
cusps unless it is whole-sign.

`shadbala` holds, for each graha, in shashtiamshas: `sthana` by component
(uccha, saptavargiya, ojayugma, kendra, drekkana) and in total, `dig`, `kaala`
by component (nathonnatha, paksha, tribhaga, abda, masa, vara, hora, ayana)
and in total, `cheshta`, `naisargika` and `drik`; then the sum of the six in
shashtiamshas and in rupas (over 60), the rupas the engine requires, and
whether the sum reaches them. `shadbala/manifest.json` carries the natural
strengths, the required rupas and the Saptavargaja's vargas.

## The Bhava bala (`teistro-conformance/baseline-bhava-bala/1`)

`bhava-bala/charts/` and `bhava-bala/variants/` hold one file for each fixture
the Shadbala corpus holds, written by
`export-bhava-bala-vectors.mjs --corpus <this directory>` from the recorded
lagna's sign, the nine grahas' recorded houses and the engine's Shadbala of
the same recorded chart (each graha's total and Drik), repeated as `inputs`.

`aspected_by` names, for each house, the grahas the engine counts as
aspecting it: every graha's seventh house, and Mars's fourth and eighth,
Jupiter's fifth and ninth and Saturn's third and tenth. `bhavas` holds the
twelve houses in order, each in virupas rounded to hundredths: `bhavadhipati`,
the lord's Shadbala; `dig`, ten virupas a house from the house the bhava's
sign class makes weakest; `drishti`, a quarter of `dig` added when only
benefics aspect it and taken away when only malefics do, with Jupiter's and
Mercury's Drik added when they aspect it; and `total`, the three together.

