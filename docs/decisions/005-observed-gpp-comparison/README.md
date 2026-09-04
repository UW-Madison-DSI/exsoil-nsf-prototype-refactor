# Observed GPP: comparison resolution and coverage

**Status:** Decided — monthly for bias-type metrics, daily alongside it for
correlation. Amended 2026-08-26 after Jingyi's review.
**Date:** 2026-08-25
**Decides:** issue #12 (observed-GPP filtering policy)
**Affects:** Phase 3 / Hub 2 (#8), Phase 5 validation (#10), fit metrics (#18)

## Context

Hub 2 evaluates model GPP against observed GPP and calibrates via a Kalman
filter. The observations come from the NCAR/NEON eval files
(`storage.neonscience.org/neon-ncar/NEON/eval_files/v1/`), public and
credential-free, 45 monthly files per site covering 2018-01 to 2021-09.

Towers do not measure GPP. They measure **net** ecosystem exchange, and GPP is
derived by estimating respiration and subtracting. When that estimate
overshoots, or the true flux is small relative to instrument noise, the
arithmetic returns a **negative gross photosynthesis** — physically impossible,
and an artifact of the partitioning rather than signal. Model GPP is bounded at
zero by construction, so the two series are not directly comparable.

The question was what to do about it.

## Evidence

All 225 site-months were downloaded and inspected (5 sites x 45 months, 29 MB).

| Site | Months with GPP | Missing | Mean half-hourly neg | Mean daily neg | Negative monthly means |
|---|---|---|---|---|---|
| ABBY | **28/45** | 17 | 26% | 2% | 0 |
| CLBJ | **32/45** | 13 | 29% | 6% | 0 |
| CPER | **36/45** | 9 | 34% | 30% | 10 |
| KONZ | **45/45** | 0 | 36% | 19% | 5 |
| TALL | **43/45** | 2 | 35% | 6% | 0 |

Negatives are not an edge case: **26-36% of half-hourly values**, at every
site, in every season.

### What does not work

Each was tested rather than assumed.

- **Quality-flag filtering.** Keeping only `GPP_fqc == 0` ("measured") still
  leaves **20.8% negatives** at KONZ 2018-07. The flag records gap-filling
  provenance, not physical plausibility.
- **Night masking.** Daytime negatives are common — 34% in a 09:00-15:00
  window at KONZ in July, 57% in January. The "nighttime noise" explanation is
  wrong.
- **Clamping to zero, or dropping negatives.** Both truncate an error
  distribution asymmetrically, and at 26-36% frequency that reshapes the data
  rather than cleaning it. Dropping is worse: negatives concentrate in
  low-flux conditions (winter, dormancy, cloud), so it preferentially deletes
  the periods where the model is hardest to get right, biasing the comparison
  toward easy conditions.

### What does work: aggregate before comparing

Negatives are symmetric noise around a small true value, not a systematic
offset, so they cancel within an averaging window. No truncation, no selection
bias, nothing discarded.

| Resolution | Negative fraction |
|---|---|
| Half-hourly | 26-36% |
| Daily mean | 2-30% by site (CPER worst at 30%, ABBY best at 2%) |
| **Monthly mean** | **15 of 184 (8%)** |

## Amendment, 2026-08-26

Jingyi asked for both resolutions, and the reasoning holds:

> "I wonder whether we can keep both daily and monthly benchmarking/comparison
> options. As ILAMB metrics include something beyond bias (e.g., correlation),
> the negative values still have some merits... There are diurnal signals in ET
> (and sometimes in soil moisture) so it is helpful to include the daily
> comparisons alongside the monthly comparison."

This does not reverse the analysis below; it sharpens what the analysis was
actually about. **Aggregation was needed for bias-type metrics**, where a
negative observation drags the mean and the error is not symmetric in its
effect. **Correlation is insensitive to that offset**, so it can run on
half-hourly or daily data where monthly averaging would destroy the diurnal
structure worth examining.

So the resolution is per-metric, not global:

| Metric | Resolution | Reason |
|---|---|---|
| Bias, RMSE, MAE | monthly | negatives distort the magnitude |
| Correlation, seasonal cycle, interannual variability | daily and monthly | tolerant of the offset; daily preserves diurnal signal |

Two further points from the same reply. The metrics apply to **soil water
content and ET**, not GPP alone — so negative-value handling must not be
GPP-specific. And **ET is absent from the daily stream** (`QFLX_EVAP_TOT`,
`EFLX_LH_TOT`, `QSOIL`, `QVEGE`, `QVEGT` are monthly-only), so daily ET has to
be derived from `FCEV + FCTR + FGEV`.

**Settled 2026-09-04.** Jingyi answered the output-configuration question:
derive ET from the three latent heat components at both resolutions, and
keep the components alongside the total, because he intends to supply
partitioned tower ET later and evaluate the components as well as the sum.
No change to the model's output configuration; the remaining four sites run
as-is. Recorded in #18.

Tracked in #18.

## Decision

**Compare at monthly resolution.** Reported as the headline Hub 2 metric.

Reasons: it reduces the artifact from ~30% to 8%; it matches the model's own
`h0a` monthly stream, so no model-side resampling is needed; and it is the
resolution the seasonal-cycle and interannual-variability scoring in #18 wants
anyway.

### The residual 8%

Fifteen monthly means remain negative. They are not randomly distributed:

| Site-month | Monthly mean GPP (umol/m2/s) |
|---|---|
| KONZ 2019-03 | -0.080 |
| CPER 2019-10 | -0.014 |
| CPER 2019-11 | -0.036 |
| CPER 2019-12 | -0.030 |
| CPER 2020-01 | -0.019 |
| CPER 2020-02 | -0.049 |
| CPER 2020-03 | -0.080 |
| KONZ 2020-03 | -0.103 |
| CPER 2020-09 | -0.033 |
| KONZ 2020-12 | -0.062 |
| CPER 2021-01 | -0.042 |
| KONZ 2021-01 | -0.044 |
| CPER 2021-02 | -0.022 |
| KONZ 2021-02 | -0.026 |
| CPER 2021-03 | -0.077 |
**Fourteen of fifteen fall in September-March**, the dormant season, and every
one is within ±0.104 umol/m2/s of zero — roughly 1% of a typical
growing-season value of 5-20. These are months where true GPP is
approximately zero and noise dominates.

**Policy: report them, do not silently clamp them.** At this magnitude both
model and observation are indistinguishable from zero, so the comparison is
uninformative rather than wrong. Hiding the negatives would misrepresent the
uncertainty; clamping would introduce a small upward bias precisely where the
signal is weakest. Flag dormant-season months as low-signal and let the reader
weigh them.

## Coverage is the bigger constraint

**41 of 225 site-months (18%) contain no GPP at all** — every value NaN.

| Site | 1801 | 1802 | 1803 | 1804 | 1805 | 1806 | 1807 | 1808 | 1809 | 1810 | 1811 | 1812 | 1901 | 1902 | 1903 | 1904 | 1905 | 1906 | 1907 | 1908 | 1909 | 1910 | 1911 | 1912 | 2001 | 2002 | 2003 | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2101 | 2102 | 2103 | 2104 | 2105 | 2106 | 2107 | 2108 | 2109 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ABBY | ● | ◐ | — | — | — | — | — | — | ◐ | ● | ● | ● | ◐ | — | — | — | ◐ | ● | ◐ | — | — | ◐ | ● | ● | ● | ● | ◐ | — | — | — | — | — | — | ◐ | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| CLBJ | — | — | — | — | — | — | — | — | ◐ | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ◐ | — | — | — | ◐ | — | — | ◐ | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| CPER | — | — | ◐ | ● | ◐ | — | — | — | — | — | — | — | ◐ | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| KONZ | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| TALL | ● | ● | ● | ● | ● | ● | ● | ● | ● | ◐ | — | ◐ | ● | ◐ | — | ◐ | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |

Legend: ● full coverage, ◐ partial, — no GPP data.

Two things follow.

**`GPP_fqc` is actively misleading on empty files.** ABBY 2018-07 reports
`fqc = 0` ("measured") for all 1488 timesteps while every GPP value is NaN.
Code that trusts the flag alone will compute statistics over nothing and
report them confidently. Check `np.isfinite` on the values, not the flag.

**Phase 3's five-site scope is optimistic.** Only KONZ has complete coverage
(45/45). ABBY has 28/45, with a contiguous gap from 2018-03 to 2018-08 and
another across 2020-04 to 2020-09. Any cross-site comparison must be scoped to
months where all participating sites have data, which is a materially smaller
set than 5 x 45.

## Revisit later

Finer resolution is deferred, not rejected. Reconsider when:

- a scientific question needs sub-monthly behaviour — diurnal cycles, response
  to individual precipitation events, or the timing of green-up
- the Kalman filter's update cadence needs to be faster than monthly to be
  useful for calibration
- a defensible sub-monthly treatment of the negatives is identified, for
  example an uncertainty-weighted comparison that uses the partitioning error
  estimate rather than discarding or clamping

Daily is already clean in the growing season at ABBY (2%), CLBJ (6%) and TALL
(6%); it is CPER (30%) and KONZ (19%) that would need the extra treatment.

Tracked as a follow-up issue.

## Reproducing

The 225 files are ~29 MB and were fetched directly:

```
https://storage.neonscience.org/neon-ncar/NEON/eval_files/v1/{SITE}/{SITE}_eval_{YYYY-MM}.nc
```

Units are `umol CO2 m-2 s-1`; model GPP is `gC m-2 s-1`. Convert with
**x 12.011e-6**. Getting this wrong produces a five-order-of-magnitude bias
that reads as catastrophic model failure rather than a units error.
