"""
Transform the staging tables into one unified fact table.

This is where the filtering decisions live. Every rule below was chosen after
querying the staging tables, not assumed in advance - the comments record what
the data showed and why the rule follows from it.

Output table: fct_health_indicators
    country_iso3, country_name, year, indicator, source, value,
    value_low, value_high, recall_period, ingested_at

One row = one country, one year, one indicator, one source.

Usage:
    python transform.py
"""

import logging

import duckdb

import config
from load import DB_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("transform")


# --- Filtering decisions -----------------------------------------------------
#
# WHO sex dimension
#   Four values exist: SEX_BTSX, SEX_MLE, SEX_FMLE, and NULL. The nulls are not
#   missing data - maternal mortality, DTP3 immunisation and health expenditure
#   are simply not sex-disaggregated, so WHO leaves Dim1 empty. Filtering on
#   'SEX_BTSX' alone would silently drop all 534 of those rows.
#
# WHO wealth quintile (Dim3)
#   Only under-five mortality uses it, and it produces six rows per country-year:
#   five wealth bands plus a WEALTHQUINTILE_TOTL national figure. Keeping the
#   total and discarding the bands gives the headline series; the bands are
#   valuable but belong in a separate inequality analysis, not the main table.
#
# DHS recall period
#   Chosen on coverage first, then statistical power, then convention:
#     - Maternal-care indicators use "Three years preceding the survey".
#       Two and three years both cover all 43 surveys (1986-2024); five years
#       was discontinued after 2019 and loses 6-8 surveys. Of the two survivors,
#       three years has ~50% more births in the denominator than two, which
#       matters for smaller samples like Senegal.
#     - Under-five mortality uses "Five years preceding the survey".
#       Both five and ten cover all 45 surveys, so coverage does not decide.
#       Five is the DHS convention for headline childhood mortality, and a
#       ten-year window would smear a decade of change into one point - making
#       DHS and WHO look further apart for reasons of our own construction.
#     - Basic vaccination, child stunting and modern contraceptive use are
#       point-in-time measures with no recall period at all (empty string).

WHO_SEX_FILTER = "(sex_dimension = 'SEX_BTSX' OR sex_dimension IS NULL)"
WHO_WEALTH_FILTER = "(dim3 = 'WEALTHQUINTILE_TOTL' OR dim3 IS NULL)"

DHS_RECALL_RULES = {
    "antenatal_care_4plus_visits": "Three years preceding the survey",
    "delivery_in_health_facility": "Three years preceding the survey",
    "skilled_birth_attendance": "Three years preceding the survey",
    "under_five_mortality_rate_dhs": "Five years preceding the survey",
    # No recall period - point-in-time measures. Empty string, not NULL.
    "basic_vaccination_coverage": "",
    "child_stunting_rate": "",
    "modern_contraceptive_use": "",
}


# --- Country mapping ---------------------------------------------------------


def create_country_map(con) -> None:
    """
    Build a lookup joining DHS two-letter codes to WHO ISO3 codes.

    Sourced from config.COUNTRIES so the two code systems can never drift
    apart - adding a country in one place updates both.
    """
    con.execute("DROP TABLE IF EXISTS dim_country")
    con.execute("""
        CREATE TABLE dim_country (
            country_iso3 VARCHAR,
            country_dhs  VARCHAR,
            country_name VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO dim_country VALUES (?,?,?)",
        [(c["iso3"], c["dhs"], name) for name, c in config.COUNTRIES.items()],
    )


# --- Fact table --------------------------------------------------------------


def build_fact_table(con) -> None:
    """
    Create fct_health_indicators by filtering and unioning both sources.

    recall_period is carried through rather than dropped. A reader of the
    output should be able to see which window a DHS figure describes without
    reading this file.
    """
    recall_cases = " ".join(
        f"WHEN '{ind}' THEN '{period}'"
        for ind, period in DHS_RECALL_RULES.items()
    )

    con.execute("DROP TABLE IF EXISTS fct_health_indicators")
    con.execute(f"""
        CREATE TABLE fct_health_indicators AS

        -- WHO: modelled annual estimates
        SELECT
            w.country_iso3,
            d.country_name,
            w.year,
            w.indicator,
            'WHO'            AS source,
            w.value,
            w.value_low,
            w.value_high,
            NULL             AS recall_period,
            w.ingested_at
        FROM stg_who w
        JOIN dim_country d USING (country_iso3)
        WHERE w.spatial_type = 'COUNTRY'
          AND {WHO_SEX_FILTER}
          AND {WHO_WEALTH_FILTER}
          AND w.value IS NOT NULL

        UNION ALL

        -- DHS: survey measurements, one recall period per indicator
        SELECT
            d.country_iso3,
            d.country_name,
            s.year,
            s.indicator,
            'DHS'            AS source,
            s.value,
            NULL             AS value_low,   -- DHS API does not expose CIs
            NULL             AS value_high,
            s.recall_period,
            s.ingested_at
        FROM stg_dhs s
        JOIN dim_country d ON d.country_dhs = s.country_dhs
        WHERE s.characteristic = 'Total'
          AND s.value IS NOT NULL
          AND s.recall_period = CASE s.indicator {recall_cases} END
    """)


# --- Quality checks ----------------------------------------------------------


def run_checks(con) -> bool:
    """
    Assert the output is shaped the way the design intends.

    These are not tests of the source data - they are tests of our own logic.
    A failure here means a filter is wrong, not that WHO published bad numbers.
    """
    checks = [
        (
            "no duplicate country-year-indicator-source",
            """SELECT count(*) FROM (
                   SELECT country_iso3, year, indicator, source
                   FROM fct_health_indicators
                   GROUP BY 1,2,3,4 HAVING count(*) > 1
               )""",
        ),
        ("no null values", "SELECT count(*) FROM fct_health_indicators WHERE value IS NULL"),
        ("no null countries", "SELECT count(*) FROM fct_health_indicators WHERE country_iso3 IS NULL"),
        ("no null years", "SELECT count(*) FROM fct_health_indicators WHERE year IS NULL"),
        (
            "years within a sane range",
            "SELECT count(*) FROM fct_health_indicators WHERE year < 1930 OR year > 2030",
        ),
        (
            "percentage indicators between 0 and 100",
            """SELECT count(*) FROM fct_health_indicators
               WHERE indicator IN ('dtp3_immunization_coverage',
                                   'antenatal_care_4plus_visits',
                                   'delivery_in_health_facility',
                                   'skilled_birth_attendance',
                                   'basic_vaccination_coverage',
                                   'child_stunting_rate',
                                   'modern_contraceptive_use')
                 AND (value < 0 OR value > 100)""",
        ),
    ]

    all_passed = True
    for name, sql in checks:
        failures = con.execute(sql).fetchone()[0]
        if failures:
            log.error("FAIL  %-46s %d offending rows", name, failures)
            all_passed = False
        else:
            log.info("pass  %s", name)

    return all_passed


# --- Orchestration -----------------------------------------------------------


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    try:
        create_country_map(con)
        build_fact_table(con)

        total = con.execute("SELECT count(*) FROM fct_health_indicators").fetchone()[0]
        log.info("fct_health_indicators: %d rows", total)

        for source, n in con.execute(
            "SELECT source, count(*) FROM fct_health_indicators GROUP BY 1 ORDER BY 1"
        ).fetchall():
            log.info("  %-4s %5d", source, n)

        log.info("--- quality checks ---")
        if not run_checks(con):
            raise SystemExit("Quality checks failed. Fact table is not trustworthy.")

        log.info("All checks passed.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
