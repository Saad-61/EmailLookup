"""
lookup_engine.py
----------------
Core reverse email lookup engine.
Runs all data sources concurrently and merges results.
"""

import asyncio
import hashlib
import html
import os
import time
import re
import httpx
import aiosqlite
import sqlite3
import random
from typing import Optional
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GRAVATAR_API_KEY = os.getenv("GRAVATAR_API_KEY", "")
ABSTRACT_API_KEY = os.getenv("ABSTRACT_API_KEY", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def is_clean_human_name(name: Optional[str]) -> bool:
    """Returns True if the string looks like a legitimate human name, not a hash/slug."""
    if not name or not isinstance(name, str):
        return False
    n = name.strip()
    if len(n) < 2 or len(n) > 60:
        return False
    # Filter hex hashes or auto-generated slugs (e.g. radiantaa3dc91377 or g2-e22d1711...)
    if re.search(r"^[a-f0-9]{12,}$", n, re.IGNORECASE):
        return False
    if re.search(r"^g\d-[a-f0-9]{15,}$", n, re.IGNORECASE):
        return False
    if re.search(r"^(radiant|user|profile|hash|anon)[a-z0-9_-]+$", n, re.IGNORECASE):
        return False
    digits = sum(c.isdigit() for c in n)
    letters = sum(c.isalpha() for c in n)
    if digits > 0 and letters > 0 and (digits / (digits + letters)) > 0.25:
        return False
    return True


def detect_email_typo(email: str) -> Optional[str]:
    """
    Detects common TLD or domain typos in email addresses and suggests corrections.
    e.g. 'satyanadella@microsoft.cor' -> 'satyanadella@microsoft.com'
         'user@gmai.com' -> 'user@gmail.com'
    """
    if "@" not in email:
        return None
    local, domain = email.split("@", 1)
    local = local.strip()
    domain = domain.strip().lower()

    # Common TLD typos for .com
    com_typos = ["cor", "cpm", "ocm", "comm", "coom", "con", "cm", "xom", "vom"]
    for typo in com_typos:
        if domain.endswith(f".{typo}"):
            corrected_domain = domain[:-len(typo)] + "com"
            return f"{local}@{corrected_domain}"

    # Common domain typos
    known_domain_typos = {
        "gmai.com": "gmail.com",
        "gamil.com": "gmail.com",
        "gmial.com": "gmail.com",
        "gmaill.com": "gmail.com",
        "yaho.com": "yahoo.com",
        "yahooo.com": "yahoo.com",
        "hotmial.com": "hotmail.com",
        "hotmaill.com": "hotmail.com",
        "outlok.com": "outlook.com",
        "outloo.com": "outlook.com",
        "microsft.com": "microsoft.com",
        "micosoft.com": "microsoft.com",
    }
    if domain in known_domain_typos:
        return f"{local}@{known_domain_typos[domain]}"

    return None


def extract_timezone_from_commit_date(date_str: Optional[str]) -> Optional[str]:
    """
    Extract geographical country / region from an ISO-8601 commit date timezone string.
    e.g. '2024-04-25T17:46:56.000+05:30' -> 'India'
         '2023-05-15T08:01:39.000-07:00' -> 'United States (Mountain)'
         '2024-01-01T12:00:00.000+05:00' -> 'Pakistan'
    """
    if not date_str or not isinstance(date_str, str):
        return None
    tz_match = re.search(r"([+-]\d{2}:\d{2})$", date_str.strip())
    if tz_match:
        offset = tz_match.group(1)
        tz_regions = {
            "-08:00": "United States (Pacific)",
            "-07:00": "United States (Mountain)",
            "-06:00": "United States (Central)",
            "-05:00": "United States (Eastern)",
            "-04:00": "Canada / Atlantic",
            "-03:00": "Brazil / Argentina",
            "+00:00": "United Kingdom",
            "+01:00": "Germany / Western Europe",
            "+02:00": "Eastern Europe",
            "+03:00": "Middle East / Turkey",
            "+03:30": "Iran",
            "+04:00": "United Arab Emirates",
            "+05:00": "Pakistan",
            "+05:30": "India",
            "+05:45": "Nepal",
            "+06:00": "Bangladesh",
            "+07:00": "Vietnam / Thailand",
            "+08:00": "Singapore / China",
            "+09:00": "Japan / South Korea",
            "+09:30": "Australia (Central)",
            "+10:00": "Australia (Eastern)",
            "+12:00": "New Zealand",
        }
        return tz_regions.get(offset, f"UTC{offset}")
    return None


# ── Gravatar ──────────────────────────────────────────────────────────────────

async def lookup_gravatar(email: str, client: httpx.AsyncClient) -> dict:
    """Fetch profile data from Gravatar v3 API using SHA256 hash."""
    email_hash = hashlib.sha256(email.lower().strip().encode()).hexdigest()
    headers = {**BROWSER_HEADERS}
    if GRAVATAR_API_KEY:
        headers["Authorization"] = f"Bearer {GRAVATAR_API_KEY}"

    result = {}
    try:
        # Profile endpoint
        resp = await client.get(
            f"https://api.gravatar.com/v3/profiles/{email_hash}",
            headers=headers,
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            display_name = data.get("display_name") or data.get("name", {}).get("full") or None
            if not is_clean_human_name(display_name):
                first = data.get("name", {}).get("given") or ""
                last = data.get("name", {}).get("family") or ""
                display_name = f"{first} {last}".strip() or None
            if not is_clean_human_name(display_name):
                display_name = None

            about = data.get("description") or data.get("about_me") or data.get("job_title") or None
            location = data.get("location") or None

            result["name"] = display_name
            result["bio"] = about
            result["location"] = location

            # Extract Gravatar handle / slug for cross-referencing
            profile_url = data.get("profile_url") or ""
            slug = profile_url.rstrip("/").split("/")[-1] if profile_url else ""
            raw_display = (data.get("display_name") or "").strip()
            if raw_display and " " not in raw_display and len(raw_display) >= 3:
                result["gravatar_handle"] = raw_display
            elif slug and " " not in slug and len(slug) >= 3:
                result["gravatar_handle"] = slug

            # Extract linked URLs & verified accounts from profile (Gravatar v3 uses verified_accounts)
            raw_accounts = []
            if isinstance(data.get("verified_accounts"), list):
                raw_accounts.extend(data["verified_accounts"])
            if isinstance(data.get("links"), list):
                raw_accounts.extend(data["links"])
            if isinstance(data.get("accounts"), list):
                raw_accounts.extend(data["accounts"])

            for link in raw_accounts:
                if not isinstance(link, dict):
                    continue
                url = link.get("url") or link.get("link_url") or ""
                label = (
                    link.get("service_type")
                    or link.get("service_label")
                    or link.get("label")
                    or link.get("name")
                    or ""
                ).lower()
                if "linkedin" in label or "linkedin.com" in url:
                    result["linkedin"] = url
                elif "github" in label or "github.com" in url:
                    result["github_url"] = url
                elif not result.get("website") and url and not any(k in url for k in ["gravatar.com", "wordpress.com"]):
                    result["website"] = url

        # Only set avatar if verified to exist (HEAD returns 200, not 404 default)
        try:
            av_resp = await client.head(
                f"https://www.gravatar.com/avatar/{email_hash}?d=404",
                headers=BROWSER_HEADERS,
                timeout=4,
            )
            if av_resp.status_code == 200:
                result["avatar"] = f"https://www.gravatar.com/avatar/{email_hash}?s=200"
        except Exception:
            pass

    except Exception:
        pass
    return result


async def fetch_github_readme(username: str, client: httpx.AsyncClient) -> str:
    """Fetch profile README.md content for a GitHub user if it exists."""
    for branch in ["main", "master"]:
        url = f"https://raw.githubusercontent.com/{username}/{username}/{branch}/README.md"
        try:
            resp = await client.get(url, timeout=5)
            if resp.status_code == 200 and len(resp.text) > 10:
                return resp.text
        except Exception:
            pass
    return ""


# ── GitHub ────────────────────────────────────────────────────────────────────

async def lookup_github(email: str, client: httpx.AsyncClient, candidate_username: Optional[str] = None) -> Optional[dict]:
    """
    Find a verified GitHub profile from an email address.
    Strategy 1: Commit search API (100% accurate because Git commits are email-attributed).
    Strategy 2: User search API with verified public email matching.
    Extracts author name, profile URL, bio, repos, and commit timezone offset for geolocation.
    """
    headers = {**BROWSER_HEADERS, "Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    username = None
    author_name_from_commit = None
    commit_tz = None

    # Strategy 1: Commit search (Highest precision)
    try:
        resp = await client.get(
            f'https://api.github.com/search/commits?q=author-email:"{email}"',
            headers={**headers, "Accept": "application/vnd.github.cloak-preview+json"},
            timeout=9,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            for item in items:
                commit_author = item.get("commit", {}).get("author", {})
                c_email = commit_author.get("email", "").lower()
                c_name = commit_author.get("name")
                c_date = commit_author.get("date")

                if c_email == email:
                    if c_name and is_clean_human_name(c_name) and not author_name_from_commit:
                        author_name_from_commit = c_name

                    # Check if GitHub verified account is linked to this commit
                    gh_user = item.get("author")
                    if gh_user and gh_user.get("login"):
                        username = gh_user.get("login")
                        if c_date and not commit_tz:
                            commit_tz = extract_timezone_from_commit_date(c_date)
                        break
    except Exception:
        pass

    # Strategy 2: Exact email handle check (prefers active current primary account matching email prefix)
    local_part = email.split("@")[0].lower() if "@" in email else ""
    if local_part and len(local_part) >= 3:
        try:
            handle_resp = await client.get(f"https://api.github.com/users/{local_part}", headers=headers, timeout=6)
            if handle_resp.status_code == 200:
                h_data = handle_resp.json()
                h_name = (h_data.get("name") or "").strip()
                h_email = (h_data.get("email") or "").strip().lower()

                # Verify handle really belongs to this email owner:
                # 1. Public email matches, OR
                # 2. Candidate full name strictly agrees with commit author name (e.g. Ahtisham Dilawar), OR
                # 3. Handle is a distinctive multi-part username (>=7 chars) with clean human name matching handle parts
                is_name_match = bool(author_name_from_commit and h_name and author_name_from_commit.lower() in h_name.lower())
                is_email_match = bool(h_email == email)
                is_distinctive_handle = len(local_part) >= 8 and is_clean_human_name(h_name)

                personal_domains = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "protonmail.com"}
                domain = email.split("@")[-1].lower() if "@" in email else ""
                is_personal = domain in personal_domains

                if is_email_match or is_name_match:
                    # Upgrade to current primary account
                    username = local_part
                    if h_name:
                        author_name_from_commit = h_name
                elif not username and is_distinctive_handle and is_personal:
                    username = local_part
                    if h_name:
                        author_name_from_commit = h_name
        except Exception:
            pass

    # Strategy 3: User search with strict public email verification
    if not username:
        try:
            resp = await client.get(
                f'https://api.github.com/search/users?q="{email}"+in:email',
                headers=headers, timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    cand_login = items[0].get("login")
                    if cand_login:
                        u_resp = await client.get(f"https://api.github.com/users/{cand_login}", headers=headers, timeout=6)
                        if u_resp.status_code == 200:
                            u_data = u_resp.json()
                            if u_data.get("email", "").lower() == email:
                                username = cand_login
        except Exception:
            pass

    # Strategy 4: Candidate username cross-referenced from Gravatar handle / slug
    if not username and candidate_username:
        cand = candidate_username.strip()
        if re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$", cand):
            try:
                c_resp = await client.get(f"https://api.github.com/users/{cand}", headers=headers, timeout=6)
                if c_resp.status_code == 200:
                    c_data = c_resp.json()
                    c_name = (c_data.get("name") or "").strip()
                    c_email = (c_data.get("email") or "").strip().lower()
                    local_prefix = email.split("@")[0].lower().split(".")[0].split("_")[0]
                    if (
                        c_email == email
                        or (local_prefix and len(local_prefix) >= 4 and (local_prefix in cand.lower() or (c_name and local_prefix in c_name.lower())))
                    ):
                        username = cand
                        if c_name and not author_name_from_commit:
                            author_name_from_commit = c_name
            except Exception:
                pass

    if not username and not author_name_from_commit:
        return None

    if username:
        # Fetch full profile, social accounts, and profile README concurrently
        try:
            resp, social_resp, readme_text = await asyncio.gather(
                client.get(f"https://api.github.com/users/{username}", headers=headers, timeout=8),
                client.get(f"https://api.github.com/users/{username}/social_accounts", headers=headers, timeout=6),
                fetch_github_readme(username, client),
                return_exceptions=True,
            )

            if not isinstance(resp, Exception) and resp.status_code == 200:
                u = resp.json()
                phone = None
                bio_text = u.get("bio") or ""
                blog_text = u.get("blog") or ""
                phone_match = re.search(r"\+?[\d\s\-\(\)]{10,15}", bio_text)
                if phone_match:
                    phone = phone_match.group(0).strip()

                # Extract verified LinkedIn directly from GitHub profile (100% confidence):
                linkedin_direct = None

                # 1. Official GitHub Social Accounts API
                if not isinstance(social_resp, Exception) and getattr(social_resp, "status_code", 0) == 200:
                    try:
                        for acc in social_resp.json():
                            if acc.get("provider") == "linkedin" or "linkedin.com/in" in (acc.get("url") or ""):
                                linkedin_direct = acc.get("url", "").split("?")[0].rstrip("/")
                                break
                    except Exception:
                        pass

                # 2. Bio text link
                if not linkedin_direct and bio_text:
                    m = re.search(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[a-zA-Z0-9_/%-]+", bio_text)
                    if m:
                        linkedin_direct = m.group(0).split("?")[0].rstrip(").,]>")

                # 3. Blog / Website field link
                if not linkedin_direct and blog_text:
                    m = re.search(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[a-zA-Z0-9_/%-]+", blog_text)
                    if m:
                        linkedin_direct = m.group(0).split("?")[0].rstrip(").,]>")

                # 4. Profile README link
                if not linkedin_direct and isinstance(readme_text, str) and readme_text:
                    m = re.search(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[a-zA-Z0-9_/%-]+", readme_text)
                    if m:
                        linkedin_direct = m.group(0).split("?")[0].rstrip(").,]>")

                if not phone and isinstance(readme_text, str) and readme_text:
                    ph_match = re.search(r"\+?\d{1,4}[\s\.-]?\(?\d{2,4}\)?[\s\.-]?\d{3,4}[\s\.-]?\d{3,4}", readme_text)
                    if ph_match:
                        phone = ph_match.group(0).strip()

                gh_name = u.get("name")
                if not is_clean_human_name(gh_name):
                    gh_name = author_name_from_commit

                user_loc = u.get("location") or commit_tz

                return {
                    "url": u.get("html_url"),
                    "username": u.get("login"),
                    "avatar": u.get("avatar_url"),
                    "name": gh_name,
                    "bio": bio_text,
                    "location": user_loc,
                    "explicit_location": u.get("location"),
                    "company": u.get("company"),
                    "repos": u.get("public_repos"),
                    "followers": u.get("followers"),
                    "blog": blog_text or None,
                    "phone_from_bio": phone,
                    "linkedin_url": linkedin_direct,
                    "commit_timezone": commit_tz,
                }
        except Exception:
            pass

    if author_name_from_commit:
        return {
            "name": author_name_from_commit,
            "username": None,
            "url": None,
            "location": None,
            "commit_timezone": None,
        }

    return None


async def fetch_linkedin_details(linkedin_url: Optional[str], client: httpx.AsyncClient) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extracts high-resolution round profile avatar, human location, and full name directly
    from LinkedIn's OpenGraph and page metadata using Twitterbot crawler User-Agent.
    Returns (avatar_url, location, name).
    """
    if not linkedin_url or "linkedin.com/in/" not in linkedin_url:
        return None, None, None

    clean_url = linkedin_url.split("?")[0].rstrip("/")
    avatar_url = None
    location = None
    name = None

    # 1. Direct OpenGraph and metadata extraction via Twitterbot User-Agent
    try:
        resp = await client.get(
            clean_url,
            headers={
                "User-Agent": "Twitterbot/1.0",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=8,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            # Avatar
            m = re.search(r'<meta\s+(?:property|name)=["\']og:image["\']\s+content=["\']([^"\']+)["\']', resp.text)
            if not m:
                m = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\']og:image["\']', resp.text)
            if m:
                img_url = html.unescape(m.group(1))
                if "licdn.com" in img_url and any(k in img_url for k in ("profile-displayphoto", "shrink", "scale", "media")):
                    if "ghost_person" not in img_url and "default_guest_profile" not in img_url:
                        avatar_url = img_url

            # Name from og:title or <title>
            og_t = re.search(r'<meta\s+(?:property|name)=["\']og:title["\']\s+content=["\']([^"\']+)["\']', resp.text)
            if not og_t:
                og_t = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\']og:title["\']', resp.text)
            title_t = re.search(r'<title>([^<]+)</title>', resp.text)

            raw_title = html.unescape(og_t.group(1)) if og_t else (html.unescape(title_t.group(1)) if title_t else "")
            if raw_title:
                cand = raw_title.split(" - ")[0].split(" | ")[0].strip()
                if is_clean_human_name(cand):
                    name = cand

            # Location from meta description
            desc_m = re.search(r'<meta\s+(?:name|property)=["\'](?:description|og:description)["\']\s+content=["\']([^"\']+)["\']', resp.text)
            if desc_m:
                loc_m = re.search(r'Location:\s*([^·\n\r]+?)(?:\s*·|\s*\d+\s+connections|$)', desc_m.group(1))
                if loc_m:
                    loc_val = loc_m.group(1).strip()
                    if loc_val and loc_val.lower() not in ("none", "null", "unknown"):
                        location = loc_val

                # Fallback name from description if not in title
                if not name:
                    vm = re.search(r"View ([^’\'\-]+)[’\']s profile", desc_m.group(1))
                    if vm:
                        cand = html.unescape(vm.group(1)).strip()
                        if is_clean_human_name(cand):
                            name = cand

            # Location fallback from Title
            if not location and raw_title:
                t_loc = re.search(r'-\s*([A-Za-z\s,]+?)\s*\|\s*(?:Professional Profile\s*\|\s*)?LinkedIn', raw_title)
                if t_loc:
                    loc_val = t_loc.group(1).strip()
                    if loc_val and loc_val.lower() not in ("none", "null", "unknown"):
                        location = loc_val

            return avatar_url, location, name
    except Exception:
        pass

    # 2. Fallback: SerpAPI Google Images (avatar only)
    if SERPAPI_KEY and not avatar_url:
        slug = clean_url.split("linkedin.com/in/")[-1].strip("/")
        if slug:
            try:
                resp = await client.get(
                    "https://serpapi.com/search.json",
                    params={
                        "engine": "google_images",
                        "q": f'"{slug}" site:linkedin.com/in/ profile photo',
                        "api_key": SERPAPI_KEY,
                        "num": 5,
                    },
                    timeout=8,
                )
                if resp.status_code == 200:
                    for img in resp.json().get("images_results", []):
                        thumb = img.get("thumbnail") or img.get("original")
                        if thumb and "licdn.com" in thumb and "profile-displayphoto" in thumb:
                            avatar_url = thumb
                            break
            except Exception:
                pass

    return avatar_url, location, name


async def fetch_linkedin_avatar(linkedin_url: Optional[str], client: httpx.AsyncClient) -> Optional[str]:
    av, _, _ = await fetch_linkedin_details(linkedin_url, client)
    return av
async def is_github_default_avatar(avatar_url: Optional[str], client: httpx.AsyncClient) -> bool:
    """
    Detects if a GitHub avatar is an auto-generated identicon (default geometric PNG).
    GitHub identicons are PNG assets under 2,500 bytes.
    """
    if not avatar_url or "avatars.githubusercontent.com" not in avatar_url:
        return False
    try:
        resp = await client.head(avatar_url, timeout=3)
        if resp.status_code == 200:
            cl = int(resp.headers.get("content-length", 0))
            ct = resp.headers.get("content-type", "")
            if "png" in ct and 0 < cl < 2500:
                return True
    except Exception:
        pass
    return False


def is_valid_linkedin_candidate(clean_url: str, title: str, snippet: str, target_handle: str, target_name: str, anchor: str) -> tuple[bool, int]:
    title_l = title.lower()
    snippet_l = snippet.lower()
    url_l = clean_url.lower()
    url_slug = clean_url.split("/in/")[-1].lower().rstrip("/")

    # 1. Handle match
    if target_handle:
        h = target_handle.lower()
        h_no_num = re.sub(r"\d+", "", h)
        if h == url_slug or f"-{h}" in url_slug or f"{h}-" in url_slug:
            return True, 95
        if len(h_no_num) >= 5 and h_no_num in url_slug.replace("-", ""):
            return True, 90
        if len(h) >= 4 and h in title_l:
            return True, 85

    # 2. Name match
    if target_name:
        parts = [p for p in target_name.lower().split() if len(p) >= 2]
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            has_first = first in title_l or first in url_l
            has_last = last in title_l or last in url_l
            if has_first and has_last:
                if anchor and (anchor.lower() in snippet_l or anchor.lower() in title_l):
                    return True, 90
                return True, 80
            if has_first and (last in snippet_l) and anchor and (anchor.lower() in snippet_l or anchor.lower() in title_l):
                return True, 75
        elif len(parts) == 1:
            first = parts[0]
            if (first in title_l or first in url_l) and anchor and (anchor.lower() in title_l or anchor.lower() in snippet_l):
                return True, 70

    return False, 0


# ── Contextual Anchored LinkedIn Search ──────────────────────────────────────

async def search_linkedin_anchored(
    email: str,
    email_type: str,
    domain: str,
    resolved_name: Optional[str],
    resolved_location: Optional[str],
    company_name: Optional[str],
    gh_data: Optional[dict],
    client: httpx.AsyncClient,
) -> Optional[str]:
    """
    Step 1: Contextual Anchored Search for LinkedIn.
    Anchors queries using verified context:
    - Personal email handle: site:linkedin.com/in "{handle}"
    - Corporate email: site:linkedin.com/in "{name}" "{company}"
    - GitHub metadata: site:linkedin.com/in "{gh_name}" "{gh_location}"
    - Name + location: site:linkedin.com/in "{name}" "{location}"
    Strictly verifies candidate name and anchor keywords from title/snippet.
    """
    local_part = email.split("@")[0].lower() if "@" in email else ""
    gh_user = gh_data if isinstance(gh_data, dict) else {}
    gh_username = gh_user.get("username")
    gh_name = gh_user.get("name")
    gh_company = gh_user.get("company")
    gh_location = gh_user.get("location")

    # Filter out timezone pseudo-locations from text search strings
    clean_location = resolved_location
    if clean_location and clean_location.startswith("UTC"):
        clean_location = None

    # Derive company name if corporate email
    corp_anchor = company_name
    if not corp_anchor and email_type == "corporate" and domain:
        corp_anchor = domain.split(".")[0].capitalize()

    # If corporate email and no resolved_name, derive clean name from local_part
    eff_name = resolved_name
    if not eff_name and email_type == "corporate" and local_part:
        if "." in local_part or "_" in local_part:
            eff_name = local_part.replace(".", " ").replace("_", " ").title()
        elif len(local_part) >= 3 and not re.match(r"^(admin|info|sales|support|contact|help|billing|team)", local_part):
            eff_name = local_part.title()

    # Formulate prioritized query candidate list
    queries_to_try = []

    # 1. Corporate Anchored Query (Highest accuracy for business emails)
    if corp_anchor and eff_name:
        queries_to_try.append({
            "q": f'site:linkedin.com/in "{eff_name}" "{corp_anchor}"',
            "target_name": eff_name,
            "anchor": corp_anchor,
            "type": "corporate",
        })

    # 2. GitHub Handle & Local Handle Anchors (Highest accuracy for personal emails)
    if gh_username:
        queries_to_try.append({
            "q": f'site:linkedin.com/in "{gh_username}"',
            "target_handle": gh_username,
            "type": "handle",
        })

    if email_type == "personal" and local_part and len(local_part) >= 4:
        if not re.match(r"^(admin|info|sales|support|contact|help|hello)", local_part):
            queries_to_try.append({
                "q": f'site:linkedin.com/in "{local_part}"',
                "target_handle": local_part,
                "type": "handle",
            })
            # Also try unquoted handle (helps match hyphenated slugs like ahtisham-dilawar)
            queries_to_try.append({
                "q": f'site:linkedin.com/in {local_part}',
                "target_handle": local_part,
                "target_name": eff_name,
                "type": "handle",
            })
            spaced_local = re.sub(r"([a-z])([A-Z])", r"\1 \2", local_part).replace(".", " ").replace("_", " ").title()
            if " " in spaced_local and spaced_local != eff_name:
                queries_to_try.append({
                    "q": f'site:linkedin.com/in "{spaced_local}"',
                    "target_name": spaced_local,
                    "type": "name",
                })

    # 3. GitHub Org / Geo Anchors
    if gh_name:
        if gh_location and not gh_location.startswith("UTC"):
            queries_to_try.append({
                "q": f'site:linkedin.com/in "{gh_name}" "{gh_location}"',
                "target_name": gh_name,
                "anchor": gh_location,
                "type": "github_geo",
            })
        if gh_company:
            clean_comp = gh_company.lstrip("@").strip()
            queries_to_try.append({
                "q": f'site:linkedin.com/in "{gh_name}" "{clean_comp}"',
                "target_name": gh_name,
                "anchor": clean_comp,
                "type": "github_org",
            })

    # 4. Resolved Name + Location Anchor
    if eff_name and clean_location:
        queries_to_try.append({
            "q": f'site:linkedin.com/in "{eff_name}" "{clean_location}"',
            "target_name": eff_name,
            "anchor": clean_location,
            "type": "name_loc",
        })

    # 5. Clean Name Alone
    if eff_name and len(eff_name.split()) >= 2:
        queries_to_try.append({
            "q": f'site:linkedin.com/in "{eff_name}"',
            "target_name": eff_name,
            "type": "name",
        })

    # 6. Direct Email Search
    queries_to_try.append({
        "q": f'"{email}" site:linkedin.com/in',
        "target_email": email,
        "type": "email",
    })

    # Deduplicate queries while preserving order
    seen_q = set()
    unique_queries = []
    for item in queries_to_try:
        q_str = item["q"]
        if q_str not in seen_q:
            seen_q.add(q_str)
            unique_queries.append(item)

    # Execute search queries
    for item in unique_queries:
        query = item["q"]
        target_name = item.get("target_name", "")
        target_handle = item.get("target_handle", "")
        anchor = item.get("anchor", "")

        # ── Strategy 1: SerpAPI (Google) ──
        if SERPAPI_KEY:
            try:
                resp = await client.get(
                    "https://serpapi.com/search.json",
                    params={"q": query, "api_key": SERPAPI_KEY, "num": 5, "hl": "en"},
                    timeout=9,
                )
                if resp.status_code == 200:
                    results = resp.json().get("organic_results", [])
                    for r in results:
                        link = r.get("link", "")
                        if "linkedin.com/in/" not in link or "/in/dir/" in link or "/pub/dir/" in link:
                            continue

                        clean_url = link.split("?")[0].rstrip("/")
                        title = r.get("title", "").lower()
                        snippet = r.get("snippet", "").lower()

                        # Extract location from rich_snippet if present
                        extracted_loc = None
                        extensions = r.get("rich_snippet", {}).get("top", {}).get("extensions", [])
                        for ext in extensions:
                            if isinstance(ext, str) and ("," in ext or any(kw in ext.lower() for kw in ["area", "united states", "california", "york", "pakistan", "india", "kingdom", "germany", "france", "singapore", "canada"])):
                                extracted_loc = ext.strip()
                                break

                        is_valid, conf = is_valid_linkedin_candidate(clean_url, title, snippet, target_handle, target_name, anchor)
                        if is_valid:
                            return clean_url, extracted_loc, conf
            except Exception:
                pass

        # ── Strategy 2: DuckDuckGo Fallback ──
        try:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={**BROWSER_HEADERS, "Accept": "text/html"},
                timeout=8,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.select("a.result__a"):
                    href = a.get("href", "")
                    title = a.get_text(strip=True).lower()
                    if "linkedin.com/in/" in href and "/in/dir/" not in href and "/pub/dir/" not in href:
                        match = re.search(r"(https?://[a-z]{2,3}\.linkedin\.com/in/[^&\s\"]+)", href)
                        if match:
                            clean_url = match.group(1).split("?")[0].rstrip("/")
                            is_valid, conf = is_valid_linkedin_candidate(clean_url, title, "", target_handle, target_name, anchor)
                            if is_valid:
                                return clean_url, None, conf
        except Exception:
            pass

    return None, None, 0


# ── AbstractAPI Email Enrichment & Reputation (Full) ─────────────────────

async def lookup_abstractapi(email: str, client: httpx.AsyncClient) -> dict:
    """
    Call AbstractAPI Email Validation / Reputation endpoint.
    Extracts deliverability, sender name, quality score, risk statuses,
    and detailed breach data with domain names & breach dates.
    """
    result = {}
    if not ABSTRACT_API_KEY:
        return result

    endpoints = [
        "https://emailreputation.abstractapi.com/v1/",
        "https://emailvalidation.abstractapi.com/v1/",
    ]

    for url in endpoints:
        try:
            resp = await client.get(
                url,
                params={"api_key": ABSTRACT_API_KEY, "email": email},
                timeout=10,
            )
            if resp.status_code == 200:
                d = resp.json()

                # ── 1. Breaches ──
                b_info = d.get("email_breaches") or d.get("breaches") or {}
                if isinstance(b_info, dict):
                    result["breach_count"] = b_info.get("total_breaches") or b_info.get("count", 0)
                    result["breach_first"] = b_info.get("date_first_breached") or b_info.get("first_breached")
                    result["breach_last"] = b_info.get("date_last_breached") or b_info.get("last_breached")

                    raw_domains = b_info.get("breached_domains") or []
                    parsed_breaches = []
                    for bd in raw_domains:
                        if isinstance(bd, dict):
                            parsed_breaches.append({
                                "domain": bd.get("domain") or bd.get("name") or "Unknown",
                                "date": bd.get("breach_date") or bd.get("date") or result.get("breach_last")
                            })
                        elif isinstance(bd, str):
                            parsed_breaches.append({"domain": bd, "date": result.get("breach_last")})
                    result["breached_domains_detail"] = parsed_breaches
                    result["breached_domains"] = [item["domain"] for item in parsed_breaches]

                # ── 2. Sender ──
                sender = d.get("email_sender") or d.get("sender") or {}
                if isinstance(sender, dict):
                    result["sender_first"] = sender.get("first_name") or None
                    result["sender_last"] = sender.get("last_name") or None
                    result["sender_provider"] = sender.get("email_provider_name") or sender.get("provider")
                    result["sender_org"] = sender.get("organization_name") or sender.get("organization")
                    result["sender_org_type"] = sender.get("organization_type")

                # ── 3. Deliverability ──
                deliv = d.get("email_deliverability") or d.get("deliverability") or {}
                if isinstance(deliv, dict):
                    result["deliverability"] = deliv.get("status") or deliv.get("status_detail") or ""
                    result["mx_records"] = deliv.get("mx_records", [])
                elif isinstance(deliv, str):
                    result["deliverability"] = deliv

                # ── 4. Quality ──
                qual = d.get("email_quality") or d.get("quality") or {}
                if isinstance(qual, dict):
                    score = qual.get("score") if qual.get("score") is not None else d.get("quality_score")
                    result["quality_score"] = score
                    result["is_free_email"] = qual.get("is_free_email", True)
                    result["is_disposable"] = qual.get("is_disposable", False)
                    result["is_catchall"] = qual.get("is_catchall", False)
                    result["is_role_account"] = qual.get("is_role", False)
                else:
                    result["quality_score"] = d.get("quality_score")

                # ── 5. Risk ──
                risk = d.get("email_risk") or d.get("risk") or {}
                if isinstance(risk, dict):
                    result["address_risk"] = risk.get("address_risk_status") or risk.get("address_risk")
                    result["domain_risk"] = risk.get("domain_risk_status") or risk.get("domain_risk")

                # ── 6. Domain ──
                domain_info = d.get("email_domain") or d.get("domain") or {}
                if isinstance(domain_info, dict):
                    result["domain_age_days"] = domain_info.get("domain_age") or domain_info.get("domain_age_days")
                    result["registrar"] = domain_info.get("registrar")
                    result["live_site"] = domain_info.get("is_live_site") or domain_info.get("live_site")

                if result.get("breach_count", 0) > 0 or result.get("quality_score") is not None:
                    break
        except Exception:
            pass

    return result


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text).strip()


# ── Company enrichment (for corporate emails) ─────────────────────────────────

async def lookup_company(domain: str, client: httpx.AsyncClient) -> Optional[dict]:
    """
    Use Clearbit Logo API (free, no auth) to get basic company info from domain.
    Works only for corporate / company domains (not gmail.com etc.).
    """
    personal_domains = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "icloud.com", "protonmail.com", "aol.com", "zoho.com",
        "mail.com", "yandex.com", "gmx.com", "live.com",
    }
    clean_dom = domain.lower().strip()
    if clean_dom in personal_domains:
        return None

    # Step 1: Check local company_domains SQLite database (0 ms, offline)
    if os.path.exists(PROFILES_DB_PATH):
        try:
            async with aiosqlite.connect(PROFILES_DB_PATH, timeout=10.0) as db:
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.execute("PRAGMA busy_timeout=15000;")
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM company_domains WHERE domain = ? LIMIT 1",
                    (clean_dom,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        r = dict(row)
                        return {
                            "name": r.get("company_name") or clean_dom.split(".")[0].capitalize(),
                            "domain": clean_dom,
                            "logo": f"https://logo.clearbit.com/{clean_dom}",
                            "industry": r.get("industry"),
                            "country": r.get("country"),
                            "rank": r.get("rank"),
                            "email_format": r.get("email_format"),
                            "mx_provider": r.get("mx_provider"),
                        }
        except Exception:
            pass

    # Step 2: Fallback to Clearbit Autocomplete API
    try:
        resp = await client.get(
            f"https://autocomplete.clearbit.com/v1/companies/suggest?query={clean_dom}",
            headers=BROWSER_HEADERS,
            timeout=6,
        )
        if resp.status_code == 200:
            companies = resp.json()
            if companies:
                c = companies[0]
                return {
                    "name": c.get("name"),
                    "domain": c.get("domain"),
                    "logo": c.get("logo"),
                }
    except Exception:
        pass
    return None


PROFILES_DB_PATH = os.path.join(os.path.dirname(__file__), "../data/profiles.db")


async def lookup_wikidata_entity(username: Optional[str] = None, name: Optional[str] = None) -> dict:
    """Check local wikidata_entities table for authoritative cross-links."""
    if not os.path.exists(PROFILES_DB_PATH):
        return {}
    try:
        async with aiosqlite.connect(PROFILES_DB_PATH, timeout=30.0) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA busy_timeout=30000;")
            db.row_factory = aiosqlite.Row
            if username:
                async with db.execute(
                    "SELECT * FROM wikidata_entities WHERE LOWER(github_username) = ? LIMIT 1",
                    (username.lower().strip(),)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return dict(row)
            if name and len(name.split()) >= 2:
                async with db.execute(
                    "SELECT * FROM wikidata_entities WHERE LOWER(name) = ? LIMIT 1",
                    (name.lower().strip(),)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return dict(row)
    except Exception:
        pass
    return {}


async def lookup_harvested_db(email: str) -> dict:
    """Check local profiles.db database for previously scraped profile data."""
    if not os.path.exists(PROFILES_DB_PATH):
        return {}
    try:
        async with aiosqlite.connect(PROFILES_DB_PATH, timeout=30.0) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA busy_timeout=30000;")
            db.row_factory = aiosqlite.Row
            # 1. Direct exact email match
            clean_em = email.lower().strip()
            async with db.execute(
                "SELECT * FROM harvested_profiles WHERE email = ?",
                (clean_em,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

            # 2. SHA-1 reverse hash match (supports GHArchive & BigQuery hashed exports)
            if "@" in clean_em:
                prefix, domain = clean_em.split("@", 1)
                hashed_prefix = hashlib.sha1(prefix.encode("utf-8")).hexdigest()
                hashed_email = f"{hashed_prefix}@{domain}"
                async with db.execute(
                    "SELECT * FROM harvested_profiles WHERE email = ?",
                    (hashed_email,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return dict(row)
    except Exception:
        pass
    return {}


async def save_harvested_profile(
    email: str,
    person: dict,
    profiles: dict,
    company: Optional[dict] = None,
    breaches: Optional[list] = None,
):
    """
    Step 2: Breach & Stealer Log Metadata Mining.
    Automatically saves resolved intelligence, usernames, profiles, and breaches
    into the local SQLite database (data/profiles.db) for long-term intelligence.
    """
    if not email or "@" not in email:
        return
    try:
        os.makedirs(os.path.dirname(PROFILES_DB_PATH), exist_ok=True)
        gh = profiles.get("github") if isinstance(profiles.get("github"), dict) else {}
        comp_name = (company or {}).get("name") if isinstance(company, dict) else None

        for attempt in range(5):
            try:
                async with aiosqlite.connect(PROFILES_DB_PATH, timeout=30.0) as db:
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
                            source      TEXT    DEFAULT 'lookup_enrichment',
                            scraped_at  INTEGER NOT NULL
                        )
                    """)
                    await db.execute("""
                        CREATE TABLE IF NOT EXISTS breach_records (
                            id          INTEGER PRIMARY KEY AUTOINCREMENT,
                            email       TEXT NOT NULL,
                            breach_name TEXT NOT NULL,
                            breach_date TEXT,
                            discovered_at INTEGER NOT NULL
                        )
                    """)
                    await db.execute("""
                        INSERT INTO harvested_profiles
                            (email, name, github_url, username, avatar_url, bio, location,
                             company, blog, followers, public_repos, source, scraped_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(email) DO UPDATE SET
                            name        = COALESCE(excluded.name, name),
                            github_url  = COALESCE(excluded.github_url, github_url),
                            username    = COALESCE(excluded.username, username),
                            avatar_url  = COALESCE(excluded.avatar_url, avatar_url),
                            bio         = COALESCE(excluded.bio, bio),
                            location    = COALESCE(excluded.location, location),
                            company     = COALESCE(excluded.company, company),
                            blog        = COALESCE(excluded.blog, blog),
                            followers   = COALESCE(excluded.followers, followers),
                            public_repos = COALESCE(excluded.public_repos, public_repos),
                            scraped_at  = excluded.scraped_at
                    """, (
                        email.lower().strip(),
                        person.get("name"),
                        gh.get("url"),
                        gh.get("username"),
                        person.get("avatar"),
                        person.get("bio"),
                        person.get("location"),
                        comp_name,
                        person.get("website"),
                        gh.get("followers"),
                        gh.get("repos"),
                        "lookup_enrichment",
                        int(time.time()),
                    ))

                    if breaches:
                        for b in breaches:
                            b_name = b.get("name")
                            if b_name:
                                await db.execute("""
                                    INSERT INTO breach_records (email, breach_name, breach_date, discovered_at)
                                    VALUES (?, ?, ?, ?)
                                """, (email.lower().strip(), b_name, b.get("date"), int(time.time())))

                    await db.commit()
                    return
            except (sqlite3.OperationalError, aiosqlite.OperationalError) as e:
                if ("locked" in str(e).lower() or "busy" in str(e).lower()) and attempt < 4:
                    await asyncio.sleep(0.15 * (2 ** attempt) + random.uniform(0.05, 0.15))
                else:
                    raise
    except Exception:
        pass


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_lookup(email: str) -> dict:
    """
    Run all lookup sources concurrently and merge into a single result dict.
    Anchors LinkedIn search using verified GitHub, company, and real name signals.
    """
    start = time.time()
    email = email.lower().strip()
    if not EMAIL_REGEX.match(email):
        return {
            "email": email,
            "email_type": "invalid",
            "domain": "",
            "query_time_ms": int((time.time() - start) * 1000),
            "person": {"name": None, "avatar": None, "bio": None, "location": None, "website": None},
            "profiles": {},
            "breaches": [],
            "phone": None,
            "address": None,
            "company": None,
            "email_quality": {"deliverability": "invalid"},
        }

    domain = email.split("@")[-1] if "@" in email else ""

    personal_domains = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "icloud.com", "protonmail.com", "aol.com", "zoho.com",
        "mail.com", "yandex.com", "gmx.com", "live.com",
    }
    email_type = "personal" if domain in personal_domains else "corporate"

    async with httpx.AsyncClient(timeout=14) as client:
        # Phase 1: Run all base enrichment sources concurrently
        gravatar, github, abstract_data, company, harvested = await asyncio.gather(
            lookup_gravatar(email, client),
            lookup_github(email, client),
            lookup_abstractapi(email, client),
            lookup_company(domain, client),
            lookup_harvested_db(email),
            return_exceptions=True,
        )

        # Safe fallbacks
        if isinstance(gravatar, Exception): gravatar = {}
        if isinstance(github, Exception): github = None
        if isinstance(abstract_data, Exception): abstract_data = {}
        if isinstance(company, Exception): company = None
        if isinstance(harvested, Exception): harvested = {}

        # Fallback cross-reference: if GitHub was not found by direct email search,
        # but Gravatar revealed a handle or username slug, check GitHub for that candidate
        if not github and isinstance(gravatar, dict) and gravatar.get("gravatar_handle"):
            try:
                cand_gh = await lookup_github(email, client, candidate_username=gravatar.get("gravatar_handle"))
                if cand_gh:
                    github = cand_gh
            except Exception:
                pass

        # ── Resolve name from best source: GitHub > Gravatar > AbstractAPI sender > Harvested DB ──
        ab_first = ((abstract_data or {}).get("sender_first") or "").strip()
        ab_last  = ((abstract_data or {}).get("sender_last") or "").strip()
        if ab_first.lower() in ("none", "null", "unknown"): ab_first = ""
        if ab_last.lower() in ("none", "null", "unknown"): ab_last = ""
        ab_name  = f"{ab_first} {ab_last}".strip() or None

        gh_name = github.get("name") if github else None
        grav_name = gravatar.get("name")

        # If GitHub has a proper multi-word human name, prefer it over a single-word Gravatar handle
        if gh_name and is_clean_human_name(gh_name) and " " in gh_name.strip():
            resolved_name = gh_name
        elif grav_name and is_clean_human_name(grav_name):
            resolved_name = grav_name
        else:
            resolved_name = (
                gh_name
                or ab_name
                or (harvested.get("name") if harvested else None)
            )

        # Format name nicely and strip any 'none' / 'null' artifacts
        if resolved_name:
            resolved_name = re.sub(r"\b(none|null|unknown)\b", "", resolved_name, flags=re.IGNORECASE).strip()
            if resolved_name:
                resolved_name = " ".join(part.capitalize() for part in resolved_name.split())
            else:
                resolved_name = None

        # If resolved_name is a single word, check if local_part starts with it and has remainder
        local_part = email.split("@")[0].lower() if "@" in email else ""
        if resolved_name and len(resolved_name.split()) == 1 and local_part:
            r_lower = resolved_name.lower()
            if local_part.startswith(r_lower) and len(local_part) > len(r_lower) + 1:
                remainder = local_part[len(r_lower):].lstrip("._-")
                if remainder.isalpha():
                    resolved_name = f"{resolved_name} {remainder.capitalize()}"
        elif not resolved_name and local_part:
            if "." in local_part or "_" in local_part:
                clean_parts = local_part.replace(".", " ").replace("_", " ").split()
                if all(p.isalpha() for p in clean_parts):
                    resolved_name = " ".join(p.capitalize() for p in clean_parts)

        resolved_location = (
            gravatar.get("location")
            or (github.get("location") if github else None)
            or (harvested.get("location") if harvested else None)
        )

        # ── Phase 2: Contextual Anchored LinkedIn Resolution ──
        # Priority 1: LinkedIn direct from GitHub (Social Accounts, Bio, Blog, README)
        gh_direct_linkedin = (github.get("linkedin_url") if isinstance(github, dict) else None)
        # Priority 2: Gravatar profile link
        gravatar_linkedin = gravatar.get("linkedin")
        # Priority 3: Local Harvested DB link
        harvested_linkedin = harvested.get("linkedin_url")

        # Priority 4: Wikidata authoritative entity cross-link
        gh_u = (github.get("username") if isinstance(github, dict) else None) or gravatar.get("gravatar_handle") or harvested.get("username")
        wikidata_record = await lookup_wikidata_entity(username=gh_u, name=resolved_name)
        wikidata_linkedin = wikidata_record.get("linkedin_url") if wikidata_record else None

        linkedin_url = gh_direct_linkedin or gravatar_linkedin or harvested_linkedin or wikidata_linkedin
        linkedin_loc = None
        linkedin_confidence = 100 if linkedin_url else 0

        if not linkedin_url:
            comp_name = (company.get("name") if isinstance(company, dict) else None) or (abstract_data.get("sender_org") if isinstance(abstract_data, dict) else None)
            linkedin_url, linkedin_loc, linkedin_confidence = await search_linkedin_anchored(
                email=email,
                email_type=email_type,
                domain=domain,
                resolved_name=resolved_name,
                resolved_location=None,
                company_name=comp_name,
                gh_data=github if isinstance(github, dict) else None,
                client=client,
            )

        # Fetch authentic LinkedIn details (avatar, human location, and fallback human name)
        li_avatar = None
        li_name = None
        if linkedin_url:
            fetched_av, fetched_loc, fetched_name = await fetch_linkedin_details(linkedin_url, client)
            if fetched_av:
                li_avatar = fetched_av
            if fetched_loc:
                linkedin_loc = fetched_loc
            if fetched_name:
                li_name = fetched_name

        # Fallback to LinkedIn name if resolved_name was not found through other channels
        if not resolved_name and li_name:
            resolved_name = li_name

        # ── Location Hierarchy ──
        # Priority 1: LinkedIn profile location (Highest fidelity, user-stated)
        # Priority 2: Explicit GitHub profile location (e.g. "Nairobi")
        # Priority 3: Gravatar profile location
        # Priority 4: Harvested database location
        # Priority 5: GitHub commit timezone region (fallback)
        resolved_location = (
            linkedin_loc
            or (github.get("explicit_location") if github else None)
            or gravatar.get("location")
            or (harvested.get("location") if harvested else None)
            or (github.get("commit_timezone") if github else None)
        )

        # Sanitize location - strip raw timezone tags (e.g. UTC, UTC+05:00) or placeholder tokens
        if resolved_location:
            loc_clean = resolved_location.strip()
            if loc_clean.lower() in ("utc", "none", "null", "unknown", "n/a") or loc_clean.upper().startswith("UTC"):
                resolved_location = None
            else:
                resolved_location = loc_clean

        # ── Profile picture hierarchy ──
        # 1. Gravatar (real verified human photo)
        # 2. LinkedIn avatar (formal headshot via OpenGraph)
        # 3. GitHub custom avatar (if no LinkedIn photo available)
        # 4. Fallback to GitHub default identicon
        gh_avatar = github.get("avatar") if (github and isinstance(github, dict)) else None
        is_gh_default = await is_github_default_avatar(gh_avatar, client) if gh_avatar else False

        resolved_avatar = gravatar.get("avatar")

        if not resolved_avatar:
            if li_avatar:
                resolved_avatar = li_avatar
            elif gh_avatar and not is_gh_default:
                resolved_avatar = gh_avatar
            elif gh_avatar:
                resolved_avatar = gh_avatar

        if not resolved_avatar and harvested:
            resolved_avatar = harvested.get("avatar_url")

    # ── Build person card ──
    person = {
        "name": resolved_name,
        "avatar": resolved_avatar,
        "bio": (gravatar.get("bio") or (github.get("bio") if github else None) or (harvested.get("bio") if harvested else None)),
        "location": resolved_location,
        "website": gravatar.get("website") or (github.get("blog") if github else None),
    }

    # ── Profiles ──
    profiles = {}
    if linkedin_url:
        profiles["linkedin"] = linkedin_url
        profiles["linkedin_confidence"] = linkedin_confidence
        profiles["linkedin_verified"] = (linkedin_confidence == 100)

    # Only include GitHub profile if a verified username exists
    if github and isinstance(github, dict) and github.get("username"):
        profiles["github"] = {
            "url": github.get("url"),
            "username": github.get("username"),
            "avatar": github.get("avatar"),
            "bio": github.get("bio"),
            "location": github.get("location"),
            "repos": github.get("repos"),
            "followers": github.get("followers"),
            "blog": github.get("blog"),
            "commit_timezone": github.get("commit_timezone"),
        }

    # ── Phone from GitHub bio ──
    phone = github.get("phone_from_bio") if github else None

    # ── Breaches from AbstractAPI ──
    breaches = []
    if abstract_data and abstract_data.get("breached_domains_detail"):
        for bd in abstract_data["breached_domains_detail"]:
            breaches.append({
                "name": bd.get("domain", "Unknown Breach"),
                "date": bd.get("date") or abstract_data.get("breach_last"),
                "data_types": ["Credentials", "Stealer Log"],
                "description": f"Exposed in {bd.get('domain')} data breach.",
            })
    elif abstract_data and abstract_data.get("breach_count", 0) > 0:
        for domain_name in (abstract_data.get("breached_domains") or []):
            breaches.append({
                "name": domain_name,
                "date": abstract_data.get("breach_last"),
                "data_types": ["Credentials"],
                "description": f"Exposed in {domain_name} data breach.",
            })

    # ── Email quality & risk ──
    email_quality = {}
    if abstract_data and isinstance(abstract_data, dict):
        email_quality = {
            "quality_score": abstract_data.get("quality_score"),
            "deliverability": abstract_data.get("deliverability"),
            "is_disposable": abstract_data.get("is_disposable", False),
            "is_free_email": abstract_data.get("is_free_email", True),
            "is_catchall": abstract_data.get("is_catchall", False),
            "is_role_account": abstract_data.get("is_role_account", False),
            "smtp_provider": abstract_data.get("smtp_provider"),
            "autocorrect": abstract_data.get("autocorrect"),
            "address_risk": abstract_data.get("address_risk"),
            "domain_risk": abstract_data.get("domain_risk"),
            "domain_age_days": abstract_data.get("domain_age_days"),
            "breach_count": abstract_data.get("breach_count", 0),
            "breach_first": abstract_data.get("breach_first"),
            "breach_last": abstract_data.get("breach_last"),
            "breached_domains": abstract_data.get("breached_domains", []),
        }

    # Detect typos in domain or provider
    autocorrect_suggestion = (abstract_data.get("autocorrect") if isinstance(abstract_data, dict) else None) or detect_email_typo(email)
    if autocorrect_suggestion and autocorrect_suggestion.lower() == email.lower():
        autocorrect_suggestion = None

    # Step 2: Auto-mine discovered profile and breach metadata to local database
    await save_harvested_profile(email, person, profiles, company, breaches)

    return {
        "email": email,
        "email_type": email_type,
        "domain": domain,
        "query_time_ms": int((time.time() - start) * 1000),
        "person": person,
        "profiles": profiles,
        "breaches": breaches,
        "phone": phone,
        "address": None,
        "company": company,
        "email_quality": email_quality,
        "autocorrect": autocorrect_suggestion,
    }
