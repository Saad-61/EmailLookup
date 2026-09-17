"""
migrations/migrate_db.py
------------------------
Non-destructive migration script for data/profiles.db.

Changes:
1. Adds `linkedin_url`, `twitter_url`, `domain`, and `country` to `harvested_profiles`.
2. Backfills `domain` for existing records from `email`.
3. Creates high-performance B-Tree indexes on `username`, `domain`, and `linkedin_url`.
4. Creates `wikidata_entities` table for verified cross-links (GitHub <-> LinkedIn <-> Name <-> Website).
5. Creates `company_domains` table for corporate domain intelligence.
"""

import sqlite3
import os
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "profiles.db"

def run_migration():
    if not DB_PATH.exists():
        print(f"[!] Database not found at {DB_PATH}")
        sys.exit(1)

    print(f"[*] Connecting to {DB_PATH} with 30s busy timeout...")
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    cur = conn.cursor()

    # ── 1. Check & Add Columns to harvested_profiles ──
    cur.execute("PRAGMA table_info(harvested_profiles);")
    existing_cols = {row[1] for row in cur.fetchall()}
    print(f"[*] Existing columns in harvested_profiles: {existing_cols}")

    columns_to_add = [
        ("linkedin_url", "TEXT"),
        ("twitter_url", "TEXT"),
        ("domain", "TEXT"),
        ("country", "TEXT"),
    ]

    for col_name, col_type in columns_to_add:
        if col_name not in existing_cols:
            print(f"[+] Adding column: {col_name} ({col_type})")
            cur.execute(f"ALTER TABLE harvested_profiles ADD COLUMN {col_name} {col_type};")
        else:
            print(f"[-] Column {col_name} already exists. Skipping.")

    # ── 2. Backfill domain for records where domain is NULL ──
    print("[*] Backfilling domain from email addresses...")
    cur.execute("""
        UPDATE harvested_profiles
        SET domain = LOWER(SUBSTR(email, INSTR(email, '@') + 1))
        WHERE (domain IS NULL OR domain = '') AND email LIKE '%@%';
    """)
    updated_domains = cur.rowcount
    print(f"[+] Backfilled domain for {updated_domains} profiles.")

    # ── 3. High-Performance Indexes ──
    print("[*] Creating B-tree indexes...")
    indexes = [
        ("idx_profiles_username", "harvested_profiles(username)"),
        ("idx_profiles_domain", "harvested_profiles(domain)"),
        ("idx_profiles_name", "harvested_profiles(name)"),
        ("idx_profiles_linkedin", "harvested_profiles(linkedin_url)"),
    ]

    for idx_name, idx_target in indexes:
        print(f"[+] Creating index: {idx_name}")
        cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_target};")

    # ── 4. Create wikidata_entities Table ──
    print("[*] Creating wikidata_entities table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wikidata_entities (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            wikidata_id     TEXT UNIQUE,
            name            TEXT,
            github_username TEXT,
            linkedin_url    TEXT,
            twitter_handle  TEXT,
            website         TEXT,
            country         TEXT,
            imported_at     INTEGER NOT NULL
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wikidata_github ON wikidata_entities(github_username);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wikidata_linkedin ON wikidata_entities(linkedin_url);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wikidata_name ON wikidata_entities(name);")

    # ── 5. Create company_domains Table ──
    print("[*] Creating company_domains table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_domains (
            domain          TEXT PRIMARY KEY,
            company_name    TEXT,
            email_format    TEXT,
            mx_provider     TEXT,
            rank            INTEGER,
            country         TEXT,
            industry        TEXT,
            updated_at      INTEGER NOT NULL
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_company_name ON company_domains(company_name);")

    conn.commit()
    conn.close()
    print("\n[SUCCESS] All database migrations completed cleanly!")


if __name__ == "__main__":
    run_migration()
