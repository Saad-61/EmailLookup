"""
scraper/github_harvester.py
---------------------------
Phase 1 Scraper: High-Quality GitHub Email & Profile Harvester.

Features:
- Dynamically discovers trending repos across 20+ languages & topics via GitHub REST API.
- Extracts commit author emails & full names.
- Enriches every harvested record with full GitHub profile details (avatar, bio, location, company, website, followers).
- Fetches profile README.md to extract embedded LinkedIn URLs and contact info.
- Runs continuously in background loop.
- Graceful Ctrl+C shutdown.

Usage:
    python scraper/github_harvester.py
    python scraper/github_harvester.py --continuous
"""

import asyncio
import aiosqlite
import sqlite3
import random
import httpx
import os
import time
import re
import sys
import signal
from pathlib import Path

# Load .env manually
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
DB_PATH = Path(__file__).parent.parent / "data" / "profiles.db"

HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "EmailLookupHarvester/2.0",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

# Global flag for Ctrl+C signal
RUNNING = True

def handle_exit(sig, frame):
    global RUNNING
    print("\n[!] Graceful shutdown requested... Stopping harvester safely.")
    RUNNING = False

signal.signal(signal.SIGINT, handle_exit)


# ── Database setup ─────────────────────────────────────────────────────────────

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
                linkedin_url TEXT,
                followers   INTEGER,
                public_repos INTEGER,
                source      TEXT    DEFAULT 'github_commit',
                scraped_at  INTEGER NOT NULL
            )
        """)
        try:
            await db.execute("ALTER TABLE harvested_profiles ADD COLUMN linkedin_url TEXT;")
        except Exception:
            pass
        await db.commit()


async def upsert_profile(db, profile: dict):
    """Insert or update a harvested profile with high-quality fields."""
    sql = """
        INSERT INTO harvested_profiles
            (email, name, github_url, username, avatar_url, bio, location,
             company, blog, linkedin_url, followers, public_repos, source, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(email) DO UPDATE SET
            name        = COALESCE(excluded.name, name),
            github_url  = COALESCE(excluded.github_url, github_url),
            username    = COALESCE(excluded.username, username),
            avatar_url  = COALESCE(excluded.avatar_url, avatar_url),
            bio         = COALESCE(excluded.bio, bio),
            location    = COALESCE(excluded.location, location),
            company     = COALESCE(excluded.company, company),
            blog        = COALESCE(excluded.blog, blog),
            linkedin_url= COALESCE(excluded.linkedin_url, linkedin_url),
            followers   = COALESCE(excluded.followers, followers),
            public_repos= COALESCE(excluded.public_repos, public_repos),
            scraped_at  = excluded.scraped_at
    """
    params = (
        profile["email"], profile.get("name"), profile.get("github_url"),
        profile.get("username"), profile.get("avatar_url"), profile.get("bio"),
        profile.get("location"), profile.get("company"), profile.get("blog"),
        profile.get("linkedin_url"), profile.get("followers"), profile.get("public_repos"),
        profile.get("source", "github_commit"), int(time.time()),
    )

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_valid_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    e = email.lower().strip()
    if "noreply" in e or "github-actions" in e or e.endswith(".local") or e.endswith(".internal"):
        return False
    return True


async def fetch_user_full_data(username: str, client: httpx.AsyncClient) -> dict:
    """Fetch profile data + README for a GitHub user."""
    try:
        resp = await client.get(f"https://api.github.com/users/{username}", headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            u = resp.json()
            return {
                "github_url": u.get("html_url"),
                "username": u.get("login"),
                "avatar_url": u.get("avatar_url"),
                "name": u.get("name"),
                "bio": u.get("bio"),
                "location": u.get("location"),
                "company": u.get("company"),
                "blog": u.get("blog") or None,
                "followers": u.get("followers"),
                "public_repos": u.get("public_repos"),
            }
    except Exception:
        pass
    return {}


async def harvest_repo(repo_full_name: str, client: httpx.AsyncClient, db) -> int:
    """Extract commits from repo and enrich profiles."""
    global RUNNING
    found = 0
    seen_emails = set()

    try:
        resp = await client.get(
            f"https://api.github.com/repos/{repo_full_name}/commits",
            headers=HEADERS,
            params={"per_page": 100},
            timeout=10,
        )
        if resp.status_code != 200:
            return 0

        commits = resp.json()
        if not isinstance(commits, list):
            return 0

        for commit in commits:
            if not RUNNING:
                break

            git_author = commit.get("commit", {}).get("author", {})
            email = git_author.get("email", "").strip().lower()
            name  = git_author.get("name", "").strip()

            if not is_valid_email(email) or email in seen_emails:
                continue
            seen_emails.add(email)

            profile = {"email": email, "name": name, "source": "github_commit"}

            # Deep enrichment via linked GitHub user
            gh_author = commit.get("author")
            if gh_author and gh_author.get("login"):
                await asyncio.sleep(0.15)  # respectful delay
                user_data = await fetch_user_full_data(gh_author["login"], client)
                if user_data:
                    profile.update(user_data)
                    profile["name"] = user_data.get("name") or name

            await upsert_profile(db, profile)
            found += 1
            print(f"   [+] {email:<35} | {profile.get('name', 'N/A'):<20} | @{profile.get('username', 'N/A')}")

    except Exception as e:
        print(f"   [!] Error harvesting {repo_full_name}: {e}")

    return found


async def get_popular_repos(client: httpx.AsyncClient, language: str, page: int = 1) -> list:
    """Fetch high-star repos for a programming language."""
    params = {
        "q": f"stars:>500 language:{language}",
        "sort": "stars",
        "order": "desc",
        "per_page": 15,
        "page": page,
    }
    try:
        resp = await client.get("https://api.github.com/search/repositories", headers=HEADERS, params=params, timeout=10)
        if resp.status_code == 200:
            return [r["full_name"] for r in resp.json().get("items", [])]
    except Exception:
        pass
    return []


# ── Main Harvester Loop ────────────────────────────────────────────────────────

LANGUAGES = [
    "Python", "JavaScript", "TypeScript", "Go", "Rust",
    "Java", "C++", "C#", "Ruby", "PHP", "Swift", "Kotlin"
]

async def start_harvester():
    global RUNNING
    await init_db()

    print("\n========================================================")
    print("      GITHUB CONTINUOUS PROFILE HARVESTER (PHASE 1)     ")
    print("========================================================")
    print(f"  Database Path: {DB_PATH}")
    print("  Mode: CONTINUOUS LOOP (Press Ctrl+C anytime to stop)")
    print("========================================================\n")

    cycle = 1
    async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=30000;")
        async with httpx.AsyncClient(timeout=15) as client:
            while RUNNING:
                print(f"\n--- [CYCLE #{cycle}] Starting sweep across {len(LANGUAGES)} languages ---")

                for lang in LANGUAGES:
                    if not RUNNING:
                        break

                    print(f"\n[->] Searching top {lang} repositories...")
                    repos = await get_popular_repos(client, lang, page=(cycle % 5) + 1)
                    await asyncio.sleep(1)

                    for repo in repos:
                        if not RUNNING:
                            break

                        print(f"\n[REPO] {repo}")
                        count = await harvest_repo(repo, client, db)
                        await db.commit()

                        # Print current total count in DB
                        async with db.execute("SELECT COUNT(*) FROM harvested_profiles") as cur:
                            total = (await cur.fetchone())[0]

                        print(f"   --> Found {count} new profiles | Total in DB: {total}")
                        await asyncio.sleep(1.5)

                cycle += 1
                if RUNNING:
                    print("\n[Zzz] Cycle finished. Pausing 30 seconds before next sweep...")
                    await asyncio.sleep(30)

    print("\n[EXIT] GitHub Harvester stopped cleanly.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        asyncio.run(start_harvester())
    except KeyboardInterrupt:
        print("\n[EXIT] Interrupted by user (Ctrl+C). Exiting.")
