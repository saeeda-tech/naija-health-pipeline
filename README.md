[![Health data pipeline](https://github.com/saeeda-tech/naija-health-pipeline/actions/workflows/pipeline.yml/badge.svg)](https://github.com/saeeda-tech/naija-health-pipeline/actions/workflows/pipeline.yml)
# African Health Indicators Pipeline

An automated data pipeline that collects, cleans and publishes public health
indicators for six African countries from two independent international sources.

**Status:** Week 4 of 6 — extraction working. Transformation and dashboard in progress.

---

## Why this exists

Health indicators for African countries are published by several international
bodies, in different formats, on different schedules, using different
methodologies. Comparing them means manual downloads and one-off spreadsheets
that go stale immediately.

This pipeline automates the collection, standardises the output, and runs itself
on a schedule so the numbers are never out of date.

It also makes visible something that manual comparison hides: **WHO and DHS
sometimes report different values for the same indicator, country and year.**
Quantifying and explaining that divergence is a core aim of the project.

## Coverage

**Countries:** Nigeria, Ghana, Kenya, Senegal, Egypt, South Africa

**Sources:**

| Source | What it provides | Access |
|---|---|---|
| [WHO Global Health Observatory](https://www.who.int/data/gho/info/gho-odata-api) | Modelled annual estimates, 2000–present | Open OData API |
| [The DHS Program](https://api.dhsprogram.com/) | Survey-based indicators, per survey round | Open REST API |

**Indicators:** life expectancy, maternal mortality, under-five mortality,
immunisation coverage, health expenditure per capita, antenatal care, facility
delivery, skilled birth attendance, child stunting, contraceptive prevalence.

## Architecture

```
  WHO GHO API ─┐
               ├─→  ingest.py  ─→  data/raw/  ─→  DuckDB  ─→  dbt  ─→  Streamlit
  DHS API ─────┘     (extract)      (dated       (load)     (model)   (dashboard)
                                     JSON)
                          ▲
                   GitHub Actions
                   (weekly schedule)
```

**Design decisions:**

- **Raw data is never modified.** Extraction writes source JSON unchanged, into
  date-partitioned folders. Transformation logic can be corrected and re-run
  without re-fetching, and every run is preserved as a record of what the source
  said on that date.
- **Failures are loud.** A persistent fetch failure exits non-zero and fails the
  scheduled run. Silently writing an empty file would produce an empty dashboard
  with no explanation — the most expensive class of pipeline bug.
- **Configuration is centralised.** All countries, indicators and endpoints live
  in `config.py`. No other module hardcodes them.
- **All requests are filtered server-side.** Some WHO indicators return over
  100,000 rows unfiltered.

## Setup

Requires Python 3.10+.

```bash
git clone <your-repo-url>
cd naija-health-pipeline

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Usage

```bash
python ingest.py                 # both sources
python ingest.py --source who    # WHO only
python ingest.py --source dhs    # DHS only
```

Output lands in `data/raw/YYYY-MM-DD/{who,dhs}/{indicator_name}.json`.

Current run: **3,771 rows across 12 indicators**, in under six seconds.

## Data notes

Things that will bite you if you don't know them:

- **WHO `Dim1` is a sex breakdown**, not a location field. Values are `SEX_MLE`,
  `SEX_FMLE`, `SEX_BTSX`. Some indicators populate it, others leave it null.
  Aggregating without filtering triple-counts.
- **WHO `SpatialDim` mixes countries and regions.** `AFR` is the entire African
  region. Always check `SpatialDimType == 'COUNTRY'`.
- **Use `NumericValue`, not `Value`.** `Value` is a display string such as
  `"61.7 [58.2–65.1]"`.
- **The DHS API paginates.** Reading only the first page is silent data loss.
- **DHS data is per survey round**, not annual. Nigeria has rounds in 1990, 2003,
  2008, 2013, 2018 and 2024. Joining to WHO's annual series requires an explicit
  decision about interpolation — this pipeline does not interpolate.
- **The DHS API serves aggregated indicators only.** Individual-level survey
  microdata requires separate registration at
  [dhsprogram.com](https://dhsprogram.com/data/new-user-registration.cfm).

## Roadmap

- [x] Week 1 — Extraction from both APIs
- [x] Week 2 — Load into DuckDB
- [x] Week 3 — dbt staging and mart models
- [x] Week 4 — Data quality tests and weekly GitHub Actions schedule
- [x] Week 5 — Streamlit dashboard, deployed
- [x] Week 6 — Documentation and write-up

## Sources

Data is used under the terms of the WHO Global Health Observatory and The DHS
Program. This project is not affiliated with or endorsed by either organisation.

