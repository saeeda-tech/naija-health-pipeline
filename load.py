"""
Load the raw JSON files into DuckDB as staging tables.

This is the load step. It reads the most recent ingest run and creates two
tables - stg_who and stg_dhs - holding the source data with light typing and
no business logic applied. Filtering and reconciliation happen in the next step.

Why DuckDB:
    A single file on disk, no server to install or run, and fast enough that a
    project this size never waits on it.

Why staging tables:
    Separating "get the data into SQL" from "make the data correct" means a bug
    in the cleaning logic is a query to fix, not a re-ingest.

Why explicit columns rather than schema inference:
    Inference guesses, and guesses change when the data changes. Naming the
    columns and their types means a surprise in the source shows up here as a
    loud error rather than silently as a different column type downstream.

Usage:
    python load.py
"""

import json
import logging
from pathlib import Path

import duckdb

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("load")

DB_PATH = config.PROJECT_ROOT / "data" / "health.duckdb"


# --- Helpers -----------------------------------------------------------------


def latest_run_dir() -> Path:
    """Return the most recent dated folder under data/raw."""
    runs = sorted(d for d in config.RAW_DIR.iterdir() if d.is_dir())
    if not runs:
        raise SystemExit("No raw data found. Run 'python ingest.py' first.")
    return runs[-1]


def read_source(run_dir: Path, source: str):
    """Yield (indicator_name, ingested_at, row) for every row of one source."""
    source_dir = run_dir / source
    if not source_dir.exists():
        log.warning("No %s data in %s", source, run_dir.name)
        return

    for path in sorted(source_dir.glob("*.json")):
        payload = json.loads(path.read_text())
        for row in payload["rows"]:
            yield payload["indicator_name"], payload["ingested_at"], row


def as_float(value):
    """Coerce to float, returning None for missing or unparseable values."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def as_int(value):
    """Coerce to int, returning None for missing or unparseable values."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# --- WHO ---------------------------------------------------------------------

WHO_SCHEMA = """
    CREATE TABLE stg_who (
        indicator      VARCHAR,
        country_iso3   VARCHAR,
        spatial_type   VARCHAR,
        year           INTEGER,
        sex_dimension  VARCHAR,
        value          DOUBLE,
        value_low      DOUBLE,
        value_high     DOUBLE,
        ingested_at    VARCHAR
    )
"""


def load_who(con, run_dir: Path) -> int:
    """Create and populate stg_who. No rows are dropped at this stage."""
    con.execute("DROP TABLE IF EXISTS stg_who")
    con.execute(WHO_SCHEMA)

    rows = [
        (
            indicator,
            r.get("SpatialDim"),
            r.get("SpatialDimType"),
            as_int(r.get("TimeDim")),
            r.get("Dim1"),
            as_float(r.get("NumericValue")),
            as_float(r.get("Low")),
            as_float(r.get("High")),
            ingested_at,
        )
        for indicator, ingested_at, r in read_source(run_dir, "who")
    ]

    con.executemany("INSERT INTO stg_who VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


# --- DHS ---------------------------------------------------------------------

DHS_SCHEMA = """
    CREATE TABLE stg_dhs (
        indicator      VARCHAR,
        country_dhs    VARCHAR,
        country_name   VARCHAR,
        year           INTEGER,
        survey_id      VARCHAR,
        characteristic VARCHAR,
        recall_period  VARCHAR,
        value          DOUBLE,
        ingested_at    VARCHAR
    )
"""


def load_dhs(con, run_dir: Path) -> int:
    """
    Create and populate stg_dhs.

    recall_period is kept deliberately: it holds values like "Three years
    preceding the survey", which is why one country-year can legitimately
    appear more than once. Dropping it would make those rows look duplicated.
    """
    con.execute("DROP TABLE IF EXISTS stg_dhs")
    con.execute(DHS_SCHEMA)

    rows = [
        (
            indicator,
            r.get("DHS_CountryCode"),
            r.get("CountryName"),
            as_int(r.get("SurveyYear")),
            r.get("SurveyId"),
            r.get("CharacteristicLabel"),
            r.get("ByVariableLabel"),
            as_float(r.get("Value")),
            ingested_at,
        )
        for indicator, ingested_at, r in read_source(run_dir, "dhs")
    ]

    con.executemany("INSERT INTO stg_dhs VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


# --- Orchestration -----------------------------------------------------------


def main() -> None:
    run_dir = latest_run_dir()
    log.info("Loading run %s into %s", run_dir.name, DB_PATH.name)

    con = duckdb.connect(str(DB_PATH))
    try:
        n_who = load_who(con, run_dir)
        n_dhs = load_dhs(con, run_dir)

        log.info("stg_who  %5d rows", n_who)
        log.info("stg_dhs  %5d rows", n_dhs)
        log.info("Done. %d rows total in %s", n_who + n_dhs, DB_PATH)
    finally:
        con.close()


if __name__ == "__main__":
    main()
