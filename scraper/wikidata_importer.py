"""
scraper/wikidata_importer.py
----------------------------
Imports verified cross-links from Wikidata's SPARQL Knowledge Graph.

Features:
- Extracts public figures, developers, and founders with verified GitHub handles,
  LinkedIn profile IDs, Twitter handles, and personal websites.
- Inserts into `wikidata_entities` table in data/profiles.db.
- Cross-references existing `harvested_profiles` by username/name and enriches
  them with authoritative LinkedIn URLs.
- Zero API keys required; 100% free and open.

Usage:
    python scraper/wikidata_importer.py
    python scraper/wikidata_importer.py --limit 5000
"""

import sys
import os
import time
import re
import sqlite3
import argparse
import httpx
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "profiles.db"
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"

HEADERS = {
    "User-Agent": "EmailLookupBot/1.0 (https://github.com/Saad-61/EmailLookup; contact: dev@emaillookup.local)",
    "Accept": "application/sparql-results+json",
}

def clean_linkedin_url(val: str) -> str:
    if not val:
        return ""
    val = val.strip()
    if val.startswith("http"):
        return val.split("?")[0].rstrip("/")
    return f"https://www.linkedin.com/in/{val}".rstrip("/")

def clean_twitter_handle(val: str) -> str:
    if not val:
        return ""
    val = val.strip().lstrip("@")
    return val

def run_import(limit: int = 0):
    if not DB_PATH.exists():
        print(f"[!] Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    cur = conn.cursor()

    print("[*] Querying Wikidata for tech professionals with GitHub + LinkedIn cross-links...")

    # Query 1: High-precision developers with BOTH GitHub and LinkedIn
    sparql_both = """
    SELECT DISTINCT ?item ?name ?github ?linkedin ?twitter ?website WHERE {
      ?item wdt:P31 wd:Q5 .
      ?item wdt:P2037 ?github .
      ?item wdt:P6634 ?linkedin .
      OPTIONAL { ?item rdfs:label ?name . FILTER(LANG(?name) = "en") }
      OPTIONAL { ?item wdt:P2002 ?twitter }
      OPTIONAL { ?item wdt:P856 ?website }
    }
    """
    if limit > 0:
        sparql_both += f" LIMIT {limit}"

    client = httpx.Client(headers=HEADERS, timeout=45.0)

    try:
        resp = client.get(WIKIDATA_ENDPOINT, params={"query": sparql_both})
        if resp.status_code != 200:
            print(f"[!] Wikidata returned status {resp.status_code}: {resp.text[:300]}")
            return

        bindings = resp.json().get("results", {}).get("bindings", [])
        print(f"[+] Retrieved {len(bindings)} authoritative profiles from Wikidata.")

        imported_count = 0
        now = int(time.time())

        for b in bindings:
            item_url = b.get("item", {}).get("value", "")
            wikidata_id = item_url.split("/")[-1] if item_url else ""
            name = b.get("name", {}).get("value", "").strip()
            github = b.get("github", {}).get("value", "").strip()
            linkedin_raw = b.get("linkedin", {}).get("value", "").strip()
            twitter_raw = b.get("twitter", {}).get("value", "").strip()
            website = b.get("website", {}).get("value", "").strip()

            linkedin_url = clean_linkedin_url(linkedin_raw)
            twitter = clean_twitter_handle(twitter_raw)

            if not github and not linkedin_url:
                continue

            # 1. Upsert into wikidata_entities
            cur.execute("""
                INSERT INTO wikidata_entities (
                    wikidata_id, name, github_username, linkedin_url, twitter_handle, website, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(wikidata_id) DO UPDATE SET
                    name = COALESCE(wikidata_entities.name, excluded.name),
                    github_username = COALESCE(excluded.github_username, wikidata_entities.github_username),
                    linkedin_url = COALESCE(excluded.linkedin_url, wikidata_entities.linkedin_url),
                    twitter_handle = COALESCE(excluded.twitter_handle, wikidata_entities.twitter_handle),
                    website = COALESCE(excluded.website, wikidata_entities.website),
                    imported_at = excluded.imported_at;
            """, (wikidata_id, name or None, github or None, linkedin_url or None, twitter or None, website or None, now))

            # 2. Enrich any existing harvested_profiles that match this GitHub username
            if github and linkedin_url:
                cur.execute("""
                    UPDATE harvested_profiles
                    SET linkedin_url = ?
                    WHERE username = ? AND (linkedin_url IS NULL OR linkedin_url = '');
                """, (linkedin_url, github))

            imported_count += 1

        conn.commit()

        # Count total in wikidata_entities
        cur.execute("SELECT COUNT(*) FROM wikidata_entities;")
        total = cur.fetchone()[0]

        # Count how many harvested_profiles now have linkedin_url
        cur.execute("SELECT COUNT(*) FROM harvested_profiles WHERE linkedin_url IS NOT NULL AND linkedin_url != '';")
        enriched_count = cur.fetchone()[0]

        print(f"\n[SUCCESS] Imported/Updated {imported_count} Wikidata entities.")
        print(f"[+] Total Wikidata records in DB: {total}")
        print(f"[+] Total harvested profiles with verified LinkedIn: {enriched_count}")

    except Exception as e:
        print(f"[!] Error during Wikidata import: {e}")
    finally:
        conn.close()
        client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wikidata SPARQL Importer")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on rows")
    args = parser.parse_args()
    run_import(limit=args.limit)
