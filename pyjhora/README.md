# PyJHora

Answers recorded from [PyJHora](https://github.com/naturalstupid/pyjhora), an
independent open-source Vedic astrology package, at **evidence rank 3**: a
second opinion on an arithmetic, never a correction of a rank-1 or rank-2
answer. The tool is run as a black box through its published functions; its
outputs are recorded with its version, and nothing of its code is.

## `vimshottari/`

PyJHora 4.8.7 over pyswisseph 2.10.3.2 without ephemeris data files (so
Moshier's analytic ephemeris), in the Lahiri ayanamsha, for every chart of
`baseline/charts/`: the chart's instant and place repeated as `inputs`, the
tool's own geocentric sidereal Moon (`moon_sidereal_deg`), and for each year
duration it answers the year's length in days, the balance at birth written
in years, months and days, and all 81 mahadashas and antardashas, each its two
lords, its start as a Julian day (UT) and its length in that duration's years.

What a consumer should know before comparing:

- **The Moon is the tool's, not the fixture's.** It is geocentric, where most
  baseline fixtures record a topocentric Moon, so compare the dasha
  arithmetic by giving your kernel this Moon, not the fixture's.
- **The tool's `jd` is local time.** The exporter passed the fixture's UT
  plus its zone offset, which reproduces the tool's Moon at the fixture's UT;
  the starts are converted back to UT.
- **The birth mahadasha's antardashas are listed from its start**, before
  birth, and each period's length is its whole share of its mahadasha.
- **The durations are five of the eight the tool offers.** Its default, the
  true sidereal year, measures 0.0 days in this version and its periods
  raise a division by zero; the true tropical and true lunar years vary per
  chart and are not recorded. Its savana year is computed, about 360.004
  days, not a flat 360.
- **Two charts are refused**, the Tromsø pair, whose house computation the
  tool's ephemeris call refuses at 69°N; the manifest lists them with the
  refusal.

`validate.py` checks every file against its schema, its hash and its
fixture's instant and place, the lords against Vimshottari's order, every
period's end against the next one's start, and that each chart is either
answered or refused.
