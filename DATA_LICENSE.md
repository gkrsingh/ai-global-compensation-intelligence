# Data licensing and attribution

The **code** in this repository is MIT-licensed — see [`LICENSE`](LICENSE).
This file covers the **data**: the third-party sources this project reads,
and the figures derived from them.

The two are kept deliberately separate. One data source is copyleft, and
mixing the two licences in one file is how a copyleft obligation ends up
accidentally asserted over a codebase that was never meant to carry it.

**Short version:** the code is MIT and stays MIT. No derived survey data is
committed to this repository, so cloning or reading it triggers no database
obligations. Running the ingestion locally, or deploying this app publicly,
does.

---

## What is and is not committed

This matters, because it decides whether publishing this repository
distributes a database at all. Verified against the actual tracked files
rather than assumed:

| Artifact | Committed? |
| --- | --- |
| Ingestion and aggregation **code** | Yes — MIT |
| Job-family → occupation-code **mappings** (`seed_survey.py`) | Yes — authored by this project, MIT |
| The Stack Overflow **survey release** (~140MB CSV) | **No** — downloaded by the operator |
| **Derived wage aggregates** (`market_data_points` rows) | **No** — produced at ingestion time, in your local database |
| A handful of illustrative figures in **test fixtures** | Yes — see note below |

`seed_survey.py` contains zero wage figures; it seeds only the taxonomy
bridge this project wrote. The derived database exists solely in a local
PostgreSQL instance after you run the ingestion yourself.

**On the test fixtures:** a small number of real aggregate values (three
country medians and a few percentiles) appear in tests so the fixtures stay
recognisable against the real source. This is an insubstantial extract used
for verification, not a redistribution of the database. It is disclosed here
rather than quietly relied upon.

---

## Stack Overflow Annual Developer Survey 2025

- **Source:** <https://survey.stackoverflow.co/2025/>
- **Database licence:** Open Database License (ODbL) v1.0 —
  <https://opendatacommons.org/licenses/odbl/1-0/>
- **Contents licence:** Database Contents License (DbCL) v1.0 —
  <https://opendatacommons.org/licenses/dbcl/1-0/>

> Contains information from the Stack Overflow Annual Developer Survey 2025,
> which is made available under the Open Database License (ODbL) v1.0.

### The obligation, and when it binds

ODbL is **copyleft for databases**. If you publicly use a Derivative Database
built from the survey, you must make that derivative available under ODbL and
keep it open.

This project produces exactly such a derivative when you run:

```bash
python -m app.market_data.ingest_survey <path-to-results.csv>
```

That writes aggregated percentile rows into your database. What follows from
that:

- **Cloning or reading this repository:** no obligation. No derived database
  is distributed here.
- **Running the ingestion locally, for yourself:** no obligation. Private use
  is not public use under ODbL.
- **Deploying this application publicly, or otherwise sharing the derived
  aggregates:** the obligation binds. You must offer the derived database
  under ODbL v1.0, with the attribution above, and keep it open.

This is recorded before it applies rather than after, because the moment it
starts applying is a deployment — not a code change — and nothing in the code
would remind you.

### What the derived figures are

Percentiles computed from real individual survey responses, with disclosed
filtering (employed respondents only; a $1,000/yr plausibility floor) and
sample-size suppression (nothing published under 30 responses; tail
percentiles only at 100+). Amounts are Stack Overflow's own USD conversion at
the exchange rate of 25 June 2025 — not re-converted by this project.

The full methodology, and the honest limitations of this source, are in the
README's "Market data coverage" section.

---

## US Bureau of Labor Statistics — Occupational Employment and Wage Statistics

- **Source:** <https://www.bls.gov/oes/>
- **Status:** Works of the US federal government are in the **public domain**
  in the United States. No licence restricts reuse, and no copyleft
  obligation attaches.

Attribution is given anyway, because a market figure without a citation is
exactly what this project refuses to produce:

> Contains information from the U.S. Bureau of Labor Statistics, Occupational
> Employment and Wage Statistics (OEWS), May 2025.

BLS does not endorse this project, and the analysis and presentation here are
this project's own.

---

## European Central Bank exchange rates (via Frankfurter)

- **Source:** <https://api.frankfurter.dev/> — ECB reference rates
- **Status:** ECB reference rates are published for free public use.

> Exchange rates sourced from the European Central Bank via the Frankfurter
> API.

---

## Tax data

Income tax brackets, thresholds and deductions for India, the United States
and Spain are transcribed from official government publications, each cited
with a source URL on the `TaxRuleSet` row it belongs to (see
`backend/app/reference_data/seed.py`). Statutes and published tax tables are
not copyrightable as facts; the citations exist so any figure can be checked
against its source, which is the point of the project rather than a licensing
requirement.

---

## Summary

| Component | Licence | Copyleft? |
| --- | --- | --- |
| Source code | MIT | No |
| Stack Overflow derived aggregates | ODbL 1.0 | **Yes**, on public use |
| BLS OEWS figures | Public domain | No |
| ECB / Frankfurter rates | Free public use | No |
| Tax bracket data | Facts from cited government sources | No |

Nothing here places the source code under ODbL. The copyleft obligation
attaches to the derived *database* and only when it is publicly used.
