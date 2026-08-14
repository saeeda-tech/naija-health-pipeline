"""
Compare WHO modelled estimates against DHS survey measurements of under-five
mortality, and test whether the apparent discrepancy survives correcting for
DHS's recall window.

Background
----------
WHO publishes an annual modelled estimate: its 2003 figure describes 2003.
DHS reports childhood mortality for the five years preceding the survey, so a
survey labelled 2003 describes roughly 1998-2003, centred near 2000.

Under-five mortality was falling throughout this period. Matching on survey
year therefore compares a single year against a backward-looking average of a
higher-mortality era, and manufactures a gap that is an artefact of alignment
rather than a disagreement between sources.

This script quantifies that. It reports the naive comparison, then two
corrections, then breaks the corrected result down by era.

Usage:
    python analysis.py
"""

import logging

import duckdb

from load import DB_PATH

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("analysis")

WINDOW_YEARS = 5  # DHS recall window for headline childhood mortality


# --- Shared CTEs -------------------------------------------------------------
#
# Defined once so every comparison below is drawing on identical definitions.
# If the indicator names change, they change in one place.

PAIRS_CTE = """
WITH dhs AS (
    SELECT country_iso3, country_name, year AS survey_year, value AS dhs_value
    FROM fct_health_indicators
    WHERE source = 'DHS' AND indicator = 'under_five_mortality_rate_dhs'
),
who AS (
    SELECT country_iso3, year, value AS who_value
    FROM fct_health_indicators
    WHERE source = 'WHO' AND indicator = 'under_five_mortality_rate'
)
"""


def naive_comparison(con):
    """
    Match on survey year. This is the comparison that produces the headline
    discrepancy, and it is wrong for the reason described in the module
    docstring. Reported so the size of the artefact is visible.
    """
    return con.execute(PAIRS_CTE + """
        SELECT count(*)                                        AS n,
               round(avg(dhs_value - who_value), 1)            AS mean_diff,
               round(avg(100.0*(dhs_value-who_value)/who_value), 1) AS mean_pct,
               sum(CASE WHEN dhs_value > who_value THEN 1 ELSE 0 END) AS dhs_higher
        FROM dhs
        JOIN who USING (country_iso3)
        WHERE who.year = dhs.survey_year
    """).fetchone()


def shifted_comparison(con, shift_years: int):
    """
    Match DHS(Y) against WHO(Y - shift). A crude correction that assumes the
    survey describes a single point in the past rather than a window.

    Run across a range of shifts, this shows how sensitive the result is to
    the alignment assumption. If the gap crosses zero near half the window
    length, the discrepancy is almost entirely an alignment artefact.
    """
    return con.execute(PAIRS_CTE + f"""
        SELECT count(*),
               round(avg(dhs_value - who_value), 1),
               round(avg(100.0*(dhs_value-who_value)/who_value), 1),
               sum(CASE WHEN dhs_value > who_value THEN 1 ELSE 0 END)
        FROM dhs
        JOIN who USING (country_iso3)
        WHERE who.year = dhs.survey_year - {shift_years}
    """).fetchone()


WINDOWED_CTE = PAIRS_CTE + f"""
, windowed AS (
    SELECT d.country_iso3,
           d.country_name,
           d.survey_year,
           d.dhs_value,
           avg(w.who_value) AS who_window
    FROM dhs d
    JOIN who w
      ON w.country_iso3 = d.country_iso3
     AND w.year BETWEEN d.survey_year - {WINDOW_YEARS - 1} AND d.survey_year
    GROUP BY 1, 2, 3, 4
    -- Require a complete window. A partial one would compare a five-year
    -- survey figure against a two- or three-year WHO average and reintroduce
    -- the very bias this correction exists to remove.
    HAVING count(w.who_value) = {WINDOW_YEARS}
)
"""


def windowed_comparison(con):
    """
    Match DHS(Y) against the mean of WHO over the same five years.

    More faithful than shifting: it compares like periods rather than guessing
    a midpoint. Assumes uniform weighting across the window, which DHS's own
    exposure-weighted calculation does not quite do - a documented limitation.
    """
    return con.execute(WINDOWED_CTE + """
        SELECT count(*),
               round(avg(dhs_value - who_window), 1),
               round(avg(100.0*(dhs_value-who_window)/who_window), 1),
               sum(CASE WHEN dhs_value > who_window THEN 1 ELSE 0 END)
        FROM windowed
    """).fetchone()


def by_era(con):
    """Corrected gap split by decade, to test whether it is uniform over time."""
    return con.execute(WINDOWED_CTE + """
        SELECT CASE WHEN survey_year < 2000 THEN 'pre-2000'
                    WHEN survey_year < 2010 THEN '2000s'
                    ELSE '2010+' END AS era,
               count(*),
               round(avg(100.0*(dhs_value-who_window)/who_window), 1)
        FROM windowed
        GROUP BY 1
        ORDER BY min(survey_year)
    """).fetchall()


def largest_remaining(con, limit: int = 6):
    """The biggest gaps that survive correction - the actual finding."""
    return con.execute(WINDOWED_CTE + f"""
        SELECT country_name, survey_year,
               round(dhs_value, 1), round(who_window, 1),
               round(100.0*(dhs_value-who_window)/who_window, 1)
        FROM windowed
        ORDER BY abs(100.0*(dhs_value-who_window)/who_window) DESC
        LIMIT {limit}
    """).fetchall()


# --- Reporting ---------------------------------------------------------------


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(
            f"No database at {DB_PATH}.\n"
            "Run: python ingest.py && python load.py && python transform.py"
        )

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        log.info("WHO vs DHS: under-five mortality")
        log.info("=" * 62)

        n, diff, pct, higher = naive_comparison(con)
        log.info("")
        log.info("1. Naive match (same year)")
        log.info("   n=%d  mean gap=%+.1f per 1,000 (%+.1f%%)  DHS higher in %d/%d",
                 n, diff, pct, higher, n)

        log.info("")
        log.info("2. Sensitivity to alignment")
        log.info("   %-10s %5s  %10s  %8s  %s", "shift", "n", "mean gap", "pct", "DHS higher")
        for k in range(0, WINDOW_YEARS):
            n, diff, pct, higher = shifted_comparison(con, k)
            log.info("   %-10s %5d  %+10.1f  %+7.1f%%  %d/%d",
                     f"{k} year" + ("s" if k != 1 else ""), n, diff, pct, higher, n)
        log.info("   (crossing zero near half the window implies an artefact)")

        n, diff, pct, higher = windowed_comparison(con)
        log.info("")
        log.info("3. Window-average correction (WHO averaged over the same %d years)", WINDOW_YEARS)
        log.info("   n=%d  mean gap=%+.1f per 1,000 (%+.1f%%)  DHS higher in %d/%d",
                 n, diff, pct, higher, n)

        log.info("")
        log.info("4. Corrected gap by era")
        for era, count, pct in by_era(con):
            log.info("   %-10s n=%2d  %+6.1f%%", era, count, pct)

        log.info("")
        log.info("5. Largest gaps surviving correction")
        for country, year, dhs, who, pct in largest_remaining(con):
            log.info("   %-14s %d  DHS=%6.1f  WHO=%6.1f  %+6.1f%%",
                     country, year, dhs, who, pct)

        log.info("")
        log.info("=" * 62)
    finally:
        con.close()


if __name__ == "__main__":
    main()
