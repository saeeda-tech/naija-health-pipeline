"""
Ingest health indicators from the WHO GHO and DHS Program APIs.

This is the extract step. It fetches raw JSON and writes it to disk, unchanged.
No cleaning, no reshaping, no filtering of columns. Those happen downstream.

Why keep raw data raw:
    If your transformation logic turns out to be wrong three weeks from now, you
    re-run the transformation against files you already have, instead of hitting
    a public API a few thousand more times. Raw files are also the only record of
    what the source actually said on a given day.

Usage:
    python ingest.py              # both sources
    python ingest.py --source who
    python ingest.py --source dhs
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest")


# --- Shared HTTP handling ----------------------------------------------------


def get_with_retries(url: str, params: dict) -> dict:
    """
    GET a URL, retrying on transient failures.

    Raises after the final attempt rather than returning empty. A scheduled run
    that fails loudly is debuggable; one that silently writes an empty file
    produces an empty dashboard and no explanation.
    """
    last_error: Exception | None = None

    for attempt in range(1, config.RETRIES + 1):
        try:
            response = requests.get(
                url, params=params, timeout=config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < config.RETRIES:
                log.warning(
                    "  attempt %d/%d failed (%s), retrying in %ds",
                    attempt,
                    config.RETRIES,
                    exc.__class__.__name__,
                    config.BACKOFF_SECONDS,
                )
                time.sleep(config.BACKOFF_SECONDS)

    raise RuntimeError(f"Failed to fetch {url} after {config.RETRIES} attempts") from last_error


def write_raw(source: str, name: str, code: str, rows: list[dict], run_date: str) -> Path:
    """Write raw rows to a dated, source-partitioned JSON file."""
    out_dir = config.RAW_DIR / run_date / source
    out_dir.mkdir(parents=True, exist_ok=True)

    path = out_dir / f"{name}.json"
    payload = {
        "source": source,
        "indicator_code": code,
        "indicator_name": name,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "rows": rows,
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


# --- Source 1: WHO -----------------------------------------------------------


def fetch_who(code: str) -> list[dict]:
    """
    Fetch one WHO indicator for the configured countries.

    The OData $filter takes a chain of 'or' clauses. Filtering server-side keeps
    the response small - some WHO indicators return 100k+ rows unfiltered.
    """
    country_filter = " or ".join(
        f"SpatialDim eq '{iso3}'" for iso3 in config.ISO3_CODES
    )
    payload = get_with_retries(
        f"{config.WHO_BASE_URL}/{code}", {"$filter": country_filter}
    )
    return payload.get("value", [])


# --- Source 2: DHS -----------------------------------------------------------


def fetch_dhs(code: str) -> list[dict]:
    """
    Fetch one DHS indicator for the configured countries.

    The DHS API paginates. Always walk every page - taking only page 1 is a
    silent data-loss bug that is very easy to miss.
    """
    all_rows: list[dict] = []
    page = 1

    while True:
        payload = get_with_retries(
            f"{config.DHS_BASE_URL}/data",
            {
                "countryIds": ",".join(config.DHS_CODES),
                "indicatorIds": code,
                "f": "json",
                "perpage": 1000,
                "page": page,
            },
        )
        rows = payload.get("Data", [])
        all_rows.extend(rows)

        total_pages = payload.get("TotalPages", 1) or 1
        if page >= total_pages or not rows:
            break
        page += 1

    return all_rows


# --- Orchestration -----------------------------------------------------------


def run_source(source: str, indicators: dict, fetcher, run_date: str) -> int:
    """Fetch and write every indicator for one source. Returns total row count."""
    log.info("--- %s (%d indicators) ---", source.upper(), len(indicators))
    total = 0

    for code, name in indicators.items():
        rows = fetcher(code)
        write_raw(source, name, code, rows, run_date)
        total += len(rows)

        if not rows:
            log.warning("%-34s 0 rows - check the indicator code", name)
        else:
            log.info("%-34s %5d rows", name, len(rows))

    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest health indicators.")
    parser.add_argument(
        "--source",
        choices=["who", "dhs", "both"],
        default="both",
        help="Which source to ingest (default: both)",
    )
    args = parser.parse_args()

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info("Ingest run %s | countries: %s", run_date, ", ".join(config.COUNTRIES))

    grand_total = 0
    try:
        if args.source in ("who", "both"):
            grand_total += run_source("who", config.WHO_INDICATORS, fetch_who, run_date)
        if args.source in ("dhs", "both"):
            grand_total += run_source("dhs", config.DHS_INDICATORS, fetch_dhs, run_date)
    except RuntimeError as exc:
        log.error("Ingest failed: %s", exc)
        sys.exit(1)

    log.info("Done. %d rows written to %s", grand_total, config.RAW_DIR / run_date)


if __name__ == "__main__":
    main()
