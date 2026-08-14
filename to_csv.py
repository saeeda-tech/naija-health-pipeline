"""
Convert the raw JSON files into one flat CSV you can open in Excel.

This is a convenience tool for inspecting the data by eye. It is NOT part of
the pipeline - the real transformation happens in DuckDB and dbt later. Nothing
downstream depends on this file.

Usage:
    python to_csv.py
"""

import csv
import json
from pathlib import Path

import config

OUTPUT = config.PROJECT_ROOT / "data" / "preview.csv"

# Columns worth looking at, per source. The raw files have far more.
WHO_FIELDS = ["SpatialDim", "TimeDim", "Dim1", "NumericValue", "Low", "High"]
DHS_FIELDS = ["CountryName", "SurveyYear", "CharacteristicLabel", "Value"]


def latest_run_dir() -> Path:
    """Find the most recent dated folder under data/raw."""
    runs = sorted(d for d in config.RAW_DIR.iterdir() if d.is_dir())
    if not runs:
        raise SystemExit("No data found. Run 'python ingest.py' first.")
    return runs[-1]


def main() -> None:
    run_dir = latest_run_dir()
    rows_out = []

    for path in sorted(run_dir.rglob("*.json")):
        payload = json.loads(path.read_text())
        source = payload["source"]
        name = payload["indicator_name"]

        for row in payload["rows"]:
            if source == "who":
                rows_out.append({
                    "source": "WHO",
                    "indicator": name,
                    "country": row.get("SpatialDim"),
                    "year": row.get("TimeDim"),
                    "breakdown": row.get("Dim1"),
                    "value": row.get("NumericValue"),
                    "low": row.get("Low"),
                    "high": row.get("High"),
                })
            else:
                rows_out.append({
                    "source": "DHS",
                    "indicator": name,
                    "country": row.get("CountryName"),
                    "year": row.get("SurveyYear"),
                    "breakdown": row.get("CharacteristicLabel"),
                    "value": row.get("Value"),
                    "low": None,
                    "high": None,
                })

    # Sort so related rows sit together - much easier to scan by eye.
    rows_out.sort(key=lambda r: (
        r["source"], r["indicator"], str(r["country"]), r["year"] or 0
    ))

    fields = ["source", "indicator", "country", "year", "breakdown",
              "value", "low", "high"]

    # utf-8-sig so Excel on Windows reads accented characters correctly.
    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Wrote {len(rows_out):,} rows to {OUTPUT}")
    print("Open it in Excel to browse the data.")


if __name__ == "__main__":
    main()
