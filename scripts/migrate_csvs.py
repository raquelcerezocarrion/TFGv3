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
import sys
from typing import Dict, Any

from backend.memory import state_store

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
    p.add_argument("--commit", action="store_true", help="Actually write to the database (default: dry-run)")
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

    # --- Implement simple migration for known CSVs ---
    # Recognized CSV names: historical_projects.csv, methodologies.csv, roles_catalog.csv,
    # skills_taxonomy.csv, tasks_catalog.csv
    actions = []
    for pl in plans:
        fname = Path(pl['file']).name
        if fname == 'historical_projects.csv':
            actions.append(('historical_projects', pl))
        elif fname in ('methodologies.csv', 'roles_catalog.csv', 'skills_taxonomy.csv', 'tasks_catalog.csv'):
            actions.append(('catalog', pl))
        else:
            actions.append(('unknown', pl))

    # Show summary
    for act, plan in actions:
        print(f"Action: {act} -> {plan['file']} rows={plan['rows']}")

    if not args.commit:
        print('\nDRY RUN (no writes). To execute migrations use --commit')
        return

    # Perform commits
    for act, plan in actions:
        path = Path(plan['file'])
        print(f"Processing {path} as {act}...")
        if act == 'historical_projects':
            # Expect CSV with headers: id,session_id,requirements,proposal_json,created_at
            with path.open('r', encoding='utf-8') as fh:
                reader = csv.DictReader(fh)
                inserted = 0
                for row in reader:
                    try:
                        sid = row.get('session_id') or f"migr-{inserted}"
                        req = row.get('requirements') or ''
                        pj = row.get('proposal_json')
                        try:
                            pj_obj = json.loads(pj) if pj else {}
                        except Exception:
                            pj_obj = { 'raw': pj }
                        # Use state_store.save_proposal
                        state_store.save_proposal(sid, req, pj_obj)
                        inserted += 1
                    except Exception as e:
                        print(f"  ERROR inserting row: {e}")
                print(f"Inserted {inserted} proposals from {path}")

        elif act == 'catalog':
            # Map filename to kind
            kind = 'unknown'
            if path.name == 'methodologies.csv': kind = 'methodology'
            elif path.name == 'roles_catalog.csv': kind = 'role'
            elif path.name == 'skills_taxonomy.csv': kind = 'skill'
            elif path.name == 'tasks_catalog.csv': kind = 'task'

            with path.open('r', encoding='utf-8') as fh:
                reader = csv.DictReader(fh)
                inserted = 0
                for row in reader:
                    # Choose a key for the catalog entry: try 'id' or 'name' or first header
                    key = row.get('id') or row.get('name') or next(iter(row.values()), '')
                    value = { k: v for k, v in row.items() }
                    try:
                        state_store.create_catalog_entry(kind, str(key), value)
                        inserted += 1
                    except Exception as e:
                        print(f"  ERROR inserting catalog row: {e}")
                print(f"Inserted {inserted} entries into catalog '{kind}' from {path}")

        else:
            print(f"Skipping unknown CSV {path}")

    print('\nMigration complete.')


if __name__ == '__main__':
    main()
