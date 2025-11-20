#!/usr/bin/env python3
"""Simple CSV migration helper with a safe --dry-run flag.

This script is intentionally conservative: when `--dry-run` is passed
it only prints the actions it would perform. It does not mutate the DB.

Use for: lightweight CSV -> DB migration tasks or to scaffold a fuller
migration workflow.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import csv
import json

DATA_DIR = Path("data")


def find_csvs():
    if not DATA_DIR.exists():
        return []
    return list(DATA_DIR.glob("*.csv"))


def plan_migration(csv_path: Path):
    # Very small enumerator: read headers and estimate row count.
    with csv_path.open("r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        headers = next(reader, [])
        row_count = sum(1 for _ in reader)
    return {"file": str(csv_path), "headers": headers, "rows": row_count}


def main():
    p = argparse.ArgumentParser(description="Plan or run CSV -> DB migrations")
    p.add_argument("--dry-run", action="store_true", help="Print planned actions without writing to DB")
    p.add_argument("--out-plan", type=str, help="Save the migration plan to a JSON file")
    args = p.parse_args()

    csvs = find_csvs()
    if not csvs:
        print("No CSV files found in data/ to migrate.")
        return

    plans = [plan_migration(pf) for pf in csvs]

    for plan in plans:
        print(f"Found: {plan['file']} -- rows: {plan['rows']} headers: {plan['headers']}")

    if args.out_plan:
        Path(args.out_plan).write_text(json.dumps(plans, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote plan to {args.out_plan}")

    if args.dry_run:
        print("DRY RUN: No changes were made. Review the plan above.")
        return

    # Placeholder for real migration logic. Keep intentionally safe.
    print("No migration logic implemented. This script only plans migrations.\nIf you want automatic migration, extend this script to open DB connections and write rows.")


if __name__ == '__main__':
    main()
