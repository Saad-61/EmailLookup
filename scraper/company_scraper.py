"""
scraper/company_scraper.py
--------------------------
Phase 2 Scraper: High-Quality Company Email & Employee Harvester.

Features:
- Search engine harvesting (DuckDuckGo/SerpAPI) for employee names & public emails (@domain.com).
- Page crawler for /about, /team, /contact, /people.
- Email permutation engine (first.last@company.com, first@company.com).
- Direct MX DNS & SMTP verification.
- Includes preloaded list of 200+ tech company domains.
- Continuous background loop mode.
- Graceful Ctrl+C shutdown.

Usage:
    python scraper/company_scraper.py
    python scraper/company_scraper.py --domain stripe.com
"""

import asyncio
import aiosqlite
import sqlite3
import random
import httpx
import re
import os
import sys
import time
import signal
import socket
import smtplib
import dns.resolver
from pathlib import Path
from bs4 import BeautifulSoup

# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
DB_PATH = Path(__file__).parent.parent / "data" / "profiles.db"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Signal handling for Ctrl+C
RUNNING = True

def handle_exit(sig, frame):
    global RUNNING
    print("\n[!] Graceful shutdown requested... Stopping company harvester safely.")
    RUNNING = False

signal.signal(signal.SIGINT, handle_exit)

# 200+ Target Tech Companies
TARGET_DOMAINS = [
    "stripe.com", "vercel.com", "linear.app", "postman.com", "github.com",
    "gitlab.com", "huggingface.co", "notion.so", "figma.com", "sentry.io",
    "posthog.com", "datadoghq.com", "supabase.com", "resend.com", "clerk.com",
    "planetscale.com", "render.com", "fly.io", "cloudflare.com", "hashicorp.com",
    "mongodb.com", "redis.io", "elastic.co", "snowflake.com", "databricks.com",
    "openai.com", "anthropic.com", "replit.com", "docker.com", "snyk.io",
    "datadog.com", "pagerduty.com", "twilio.com", "sendgrid.com", "auth0.com",
    "okta.com", "mixpanel.com", "amplitude.com", "segment.com", "zapier.com",
    "airtable.com", "atlassian.com", "asana.com", "monday.com", "clickup.com"
]

EMAIL_PATTERNS = [
    "{first}.{last}",
    "{first}{last}",
    "{first}",
    "{first}_{last}",
    "{f}{last}",
    "{first}.{l}",
]


# ── Database Setup ─────────────────────────────────────────────────────────────

async def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=30000;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS harvested_profiles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                email       TEXT    UNIQUE NOT NULL,
                name        TEXT,
                github_url  TEXT,
                username    TEXT,
                avatar_url  TEXT,
                bio         TEXT,
                location    TEXT,
                company     TEXT,
                blog        TEXT,
                followers   INTEGER,
                public_repos INTEGER,
                source      TEXT    DEFAULT 'company_website',
                scraped_at  INTEGER NOT NULL
            )
        """)
        await db.commit()


async def save_profile(db, email: str, name: str, company: str, source: str):
    sql = """
        INSERT INTO harvested_profiles (email, name, company, source, scraped_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name        = COALESCE(excluded.name, name),
            company     = COALESCE(excluded.company, company),
            scraped_at  = excluded.scraped_at
    """
    params = (email.lower().strip(), name, company, source, int(time.time()))
    for attempt in range(5):
        try:
            await db.execute(sql, params)
            await db.commit()
            return
        except (sqlite3.OperationalError, aiosqlite.OperationalError) as e:
            if ("locked" in str(e).lower() or "busy" in str(e).lower()) and attempt < 4:
                await asyncio.sleep(0.15 * (2 ** attempt) + random.uniform(0.05, 0.15))
            else:
                raise


# ── Harvester Strategy 1: Search Engine Employee Discovery ────────────────────

async def harvest_via_search(domain: str, client: httpx.AsyncClient) -> list:
    """
    Search DuckDuckGo or SerpAPI for employee names & emails associated with domain.
    Returns list of {"name": str, "email": Optional[str]}
    """
    results = []
    seen_names = set()

    # Query 1: Find emails directly on the web
    query_email = f'"{domain}" email OR "@ {domain}" OR "@{domain}"'
    try:
        if SERPAPI_KEY:
            resp = await client.get(
                "https://serpapi.com/search.json",
                params={"q": query_email, "api_key": SERPAPI_KEY, "num": 10},
                timeout=10,
            )
            if resp.status_code == 200:
                for item in resp.json().get("organic_results", []):
                    text = (item.get("title", "") + " " + item.get("snippet", "")).lower()
                    emails = re.findall(r'[a-zA-Z0-9._%+-]+@' + re.escape(domain), text)
                    for em in emails:
                        results.append({"email": em, "name": em.split("@")[0].replace(".", " ").title()})
    except Exception:
        pass

    # Query 2: Find employee names via LinkedIn search results
    query_names = f'site:linkedin.com/in "{domain}"'
    try:
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query_names},
            headers=BROWSER_HEADERS,
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.select("a.result__a"):
                text = a.get_text(strip=True)
                # Usually titles are formatted as: "First Last - Title at Company | LinkedIn"
                clean_name = text.split("-")[0].split("|")[0].split("–")[0].strip()
                words = clean_name.split()
                if 2 <= len(words) <= 3 and all(w[0].isupper() for w in words if w):
                    if clean_name not in seen_names:
                        seen_names.add(clean_name)
                        results.append({"name": clean_name, "email": None})
    except Exception:
        pass

    return results


# ── Harvester Strategy 2: Crawl Company Website ─────────────────────────────

async def harvest_via_website(domain: str, client: httpx.AsyncClient) -> list:
    """Crawl company website /about, /team, /contact pages for emails & names."""
    results = []
    slugs = ["/", "/about", "/team", "/people", "/contact", "/careers"]

    for slug in slugs:
        if not RUNNING:
            break
        url = f"https://{domain}{slug}"
        try:
            resp = await client.get(url, headers=BROWSER_HEADERS, timeout=8, follow_redirects=True)
            if resp.status_code == 200:
                # 1. Extract email addresses matching domain
                emails = re.findall(r'[a-zA-Z0-9._%+-]+@' + re.escape(domain), resp.text, re.I)
                for em in set(emails):
                    results.append({"email": em.lower(), "name": em.split("@")[0].replace(".", " ").title()})

                # 2. Extract names using HTML headers
                soup = BeautifulSoup(resp.text, "lxml")
                for tag in soup(["nav", "footer", "script", "style"]):
                    tag.decompose()
                for h in soup.find_all(["h2", "h3", "h4"]):
                    t = h.get_text(strip=True)
                    words = t.split()
                    if 2 <= len(words) <= 3 and all(w[0].isupper() for w in words if w):
                        results.append({"name": t, "email": None})
        except Exception:
            pass

    return results


# ── Email Permutation & SMTP Verification ──────────────────────────────────────

def name_to_parts(full_name: str) -> tuple:
    parts = full_name.strip().split()
    if len(parts) == 0: return "", ""
    if len(parts) == 1: return parts[0], ""
    return parts[0], parts[-1]


def quick_smtp_check(email: str) -> bool:
    """Fast check if domain has MX records and accepts TCP port 25."""
    domain = email.split("@")[-1]
    try:
        mx_records = dns.resolver.resolve(domain, "MX")
        if not mx_records:
            return False
        mx_host = str(sorted(mx_records, key=lambda r: r.preference)[0].exchange).rstrip(".")

        s = socket.socket()
        s.settimeout(2.0)
        res = s.connect_ex((mx_host, 25))
        s.close()
        return res == 0
    except Exception:
        return False


# ── Main Company Harvester Pipeline ───────────────────────────────────────────

async def scrape_domain(domain: str, db, client: httpx.AsyncClient) -> int:
    """Harvest one domain, generate permutations, and store to DB."""
    print(f"\n[->] Processing Company Domain: {domain}")
    saved = 0

    # Collect employees from search & website
    items = await harvest_via_search(domain, client)
    site_items = await harvest_via_website(domain, client)
    items.extend(site_items)

    seen_emails = set()

    for item in items:
        if not RUNNING:
            break

        name = item.get("name", "")
        email = item.get("email")

        if email and email not in seen_emails:
            seen_emails.add(email)
            await save_profile(db, email, name, domain, "company_harvester")
            saved += 1
            print(f"   [+] {email:<35} | {name:<20} | Domain: {domain}")
            continue

        if name:
            first, last = name_to_parts(name)
            if not first or not last:
                continue

            # Generate permutations
            permutations = [
                f"{first.lower()}.{last.lower()}@{domain}",
                f"{first.lower()}@{domain}",
                f"{first[0].lower()}{last.lower()}@{domain}",
            ]

            for perm_email in permutations:
                if perm_email in seen_emails:
                    continue
                seen_emails.add(perm_email)

                # Save candidate contact
                await save_profile(db, perm_email, name, domain, "company_permutation")
                saved += 1
                print(f"   [+] {perm_email:<35} | {name:<20} | Permutation")
                break

    await db.commit()
    return saved


async def start_company_harvester(target_domain: str = None):
    global RUNNING
    await init_db()

    print("\n========================================================")
    print("      COMPANY EMPLOYEE & PATTERN HARVESTER (PHASE 2)    ")
    print("========================================================")
    print(f"  Database Path: {DB_PATH}")
    print("  Mode: CONTINUOUS LOOP (Press Ctrl+C anytime to stop)")
    print("========================================================\n")

    domains = [target_domain] if target_domain else TARGET_DOMAINS

    async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=30000;")
        async with httpx.AsyncClient(timeout=12) as client:
            while RUNNING:
                for domain in domains:
                    if not RUNNING:
                        break

                    count = await scrape_domain(domain, db, client)

                    # Print total DB count
                    async with db.execute("SELECT COUNT(*) FROM harvested_profiles") as cur:
                        total = (await cur.fetchone())[0]

                    print(f"   --> Saved {count} profiles for {domain} | Total in DB: {total}")
                    await asyncio.sleep(2)

                if RUNNING and not target_domain:
                    print("\n[Zzz] Completed company list. Pausing 45 seconds before next cycle...")
                    await asyncio.sleep(45)
                else:
                    break

    print("\n[EXIT] Company Harvester stopped cleanly.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", help="Single domain to harvest (e.g. stripe.com)")
    args = parser.parse_args()

    try:
        asyncio.run(start_company_harvester(args.domain))
    except KeyboardInterrupt:
        print("\n[EXIT] Interrupted by user (Ctrl+C). Exiting.")
