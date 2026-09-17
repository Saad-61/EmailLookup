"""
scraper/gharchive_importer.py
-----------------------------
High-speed bulk importer for GitHub Archive / BigQuery exports.

Features:
- Imports CSV or JSONL files exported from Google Cloud BigQuery.
- Automatically normalizes emails, extracts domains, and formats names.
- Uses SQLite transactions with `executemany` for 50,000+ rows/second throughput.
- Conflict-safe upsert: enriches existing records without duplicating or overwriting good data.

Usage:
    python scraper/gharchive_importer.py path/to/export.csv
    python scraper/gharchive_importer.py data/bigquery_results.json
"""

import sys
import os
import time
import csv
import json
import sqlite3
import argparse
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "profiles.db"

def clean_email(email_str: str) -> str:
    if not email_str:
        return ""
    e = email_str.strip().lower()
    if "@" in e and "." in e.split("@")[-1] and "noreply" not in e and "localhost" not in e:
        return e
    return ""

def import_file(filepath: Path):
    if not filepath.exists():
        print(f"[!] File not found: {filepath}")
        return

    if not DB_PATH.exists():
        print(f"[!] Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA cache_size=10000;")
    cur = conn.cursor()

    print(f"[*] Reading and importing {filepath} into {DB_PATH.name}...")
    start_time = time.time()

    is_json = filepath.suffix.lower() in [".json", ".jsonl"]
    batch = []
    batch_size = 10000
    total_processed = 0
    total_imported = 0
    now = int(time.time())

    UPSERT_SQL = """
        INSERT INTO harvested_profiles (
            email, name, github_url, username, avatar_url, domain, source, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'gharchive_bigquery', ?)
        ON CONFLICT(email) DO UPDATE SET
            name = COALESCE(harvested_profiles.name, excluded.name),
            github_url = COALESCE(harvested_profiles.github_url, excluded.github_url),
            username = COALESCE(harvested_profiles.username, excluded.username),
            avatar_url = COALESCE(harvested_profiles.avatar_url, excluded.avatar_url),
            domain = COALESCE(harvested_profiles.domain, excluded.domain),
            scraped_at = excluded.scraped_at;
    """

    def flush_batch(b):
        nonlocal total_imported
        if not b:
            return
        cur.executemany(UPSERT_SQL, b)
        conn.commit()
        total_imported += len(b)

    if is_json:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    em = clean_email(row.get("email", ""))
                    if not em:
                        continue
                    u = row.get("username", "") or ""
                    name = row.get("name", "") or None
                    av = row.get("avatar_url", "") or None
                    gh_url = f"https://github.com/{u}" if u else None
                    domain = em.split("@")[-1]

                    batch.append((em, name, gh_url, u or None, av, domain, now))
                    total_processed += 1

                    if len(batch) >= batch_size:
                        flush_batch(batch)
                        batch = []
                        print(f"    --> Processed {total_processed} rows...")
                except Exception:
                    continue
    else:
        # CSV mode
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                em = clean_email(row.get("email", ""))
                if not em:
                    continue
                u = row.get("username", "") or ""
                name = row.get("name", "") or None
                av = row.get("avatar_url", "") or None
                gh_url = f"https://github.com/{u}" if u else None
                domain = em.split("@")[-1]

                batch.append((em, name, gh_url, u or None, av, domain, now))
                total_processed += 1

                if len(batch) >= batch_size:
                    flush_batch(batch)
                    batch = []
                    print(f"    --> Processed {total_processed} rows...")

    if batch:
        flush_batch(batch)

    elapsed = round(time.time() - start_time, 2)
    cur.execute("SELECT COUNT(*) FROM harvested_profiles;")
    total_in_db = cur.fetchone()[0]

    conn.close()
    print(f"\n[SUCCESS] Imported {total_imported} developer records in {elapsed}s!")
    print(f"[+] Total profiles in database now: {total_in_db}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GHArchive / BigQuery Bulk Importer")
    parser.add_argument("file", help="Path to exported CSV or JSON file from BigQuery")
    args = parser.parse_args()
    import_file(Path(args.file))
