"""
lookup_engine.py
----------------
Core reverse email lookup engine.
Runs all data sources concurrently and merges results.
"""

import asyncio
import base64
import hashlib
import html
import os
import time
import re
import urllib.parse
import httpx
import aiosqlite
import sqlite3
import random
from typing import Optional, List, Tuple, Dict, Any, Set
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"), override=True)
try:
    from social_finder import (
        search_social_candidates,
        jaro_winkler_similarity,
        probe_twitter_profile,
        probe_instagram_profile,
        probe_spotify_profile,
        search_spotify_users_pathfinder,
        probe_facebook_profile,
        probe_tiktok_profile,
        probe_pinterest_profile,
        fetch_facebook_candidate_avatar,
        get_random_proxy_url,
    )
except ImportError:
    from backend.social_finder import (
        search_social_candidates,
        jaro_winkler_similarity,
        probe_twitter_profile,
        probe_instagram_profile,
        probe_spotify_profile,
        search_spotify_users_pathfinder,
        probe_facebook_profile,
        probe_tiktok_profile,
        probe_pinterest_profile,
        fetch_facebook_candidate_avatar,
        get_random_proxy_url,
    )

try:
    from constants import (
        BROWSER_HEADERS, PERSONAL_DOMAINS, INVALID_TYPO_DOMAINS, KNOWN_DOMAIN_TYPOS,
        TITLE_PREFIXES, ROLE_SUFFIXES, COMMON_FIRST_NAMES, COMMON_SURNAMES, LEET_REPLACEMENTS,
        RESERVED_SYSTEM_SLUGS, US_STATES, KNOWN_CITIES, COUNTRY_CANONICAL,
        ALL_COUNTRIES, TZ_REGIONS
    )
except ImportError:
    from backend.constants import (
        BROWSER_HEADERS, PERSONAL_DOMAINS, INVALID_TYPO_DOMAINS, KNOWN_DOMAIN_TYPOS,
        TITLE_PREFIXES, ROLE_SUFFIXES, COMMON_FIRST_NAMES, COMMON_SURNAMES, LEET_REPLACEMENTS,
        RESERVED_SYSTEM_SLUGS, US_STATES, KNOWN_CITIES, COUNTRY_CANONICAL,
        ALL_COUNTRIES, TZ_REGIONS
    )

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GRAVATAR_API_KEY = os.getenv("GRAVATAR_API_KEY", "")


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


INVALID_TYPO_DOMAINS = {
    "gmil.com", "gmai.com", "gamil.com", "gmial.com", "gmaill.com", "gmal.com",
    "gmaik.com", "gmaul.com", "gmajl.com", "gnail.com", "gmaili.com",
    "yaho.com", "yahooo.com", "yaho.co", "yhaoo.com",
    "hotmial.com", "hotmaill.com", "hotmai.com", "hotmil.com",
    "outlok.com", "outloo.com", "outllok.com",
    "iclod.com", "protonmal.com", "microsft.com", "micosoft.com",
}

INVALID_TLD_TYPOS = ["cor", "cpm", "ocm", "comm", "coom", "con", "cm", "xom", "vom"]


def is_valid_email(email: str) -> bool:
    """Validates email format and ensures domain is not a known common typo."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return False
    parts = email.split("@", 1)
    if len(parts) != 2:
        return False
    domain = parts[1].strip().lower()
    if domain in INVALID_TYPO_DOMAINS:
        return False
    for typo in INVALID_TLD_TYPOS:
        if domain.endswith(f".{typo}"):
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
    for typo in INVALID_TLD_TYPOS:
        if domain.endswith(f".{typo}"):
            corrected_domain = domain[:-len(typo)] + "com"
            return f"{local}@{corrected_domain}"

    # Common domain typos
    known_domain_typos = {
        "gmil.com": "gmail.com",
        "gmai.com": "gmail.com",
        "gamil.com": "gmail.com",
        "gmial.com": "gmail.com",
        "gmaill.com": "gmail.com",
        "gmal.com": "gmail.com",
        "yaho.com": "yahoo.com",
        "yahooo.com": "yahoo.com",
        "yaho.co": "yahoo.com",
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


def split_concatenated_name(local_part: str) -> Optional[str]:
    """
    Parses concatenated names from personal email usernames with or without delimiters, titles, and leetspeak numbers.
    e.g. 'tauq33raslam'   -> 'Tauqeer Aslam'
         'saad0asif'      -> 'Saad Asif'
         'saad00'         -> 'Saad'
         'nomanghaffar074' -> 'Noman Ghaffar'
         'ch.fahadahmad11' -> 'Ch Fahad Ahmad'
         'dr.saadasif99'   -> 'Dr Saad Asif'
         'mominawaqar18'   -> 'Momina Waqar'
    """
    if not local_part:
        return None

    # 1. Check for explicit delimiters (., _, -)
    if any(sep in local_part for sep in (".", "_", "-")):
        chunks = [re.sub(r"[\d._+-]+", "", c).strip().lower() for c in re.split(r"[._+-]", local_part)]
        chunks = [c for c in chunks if len(c) >= 2]
        if chunks and chunks[-1] in ROLE_SUFFIXES and len(chunks) >= 2:
            chunks = chunks[:-1]

        title = ""
        if chunks and chunks[0] in TITLE_PREFIXES and len(chunks) >= 2:
            title = chunks[0].capitalize()
            chunks = chunks[1:]

        if len(chunks) >= 2:
            fn = f"{title} {chunks[0].capitalize()}".strip() if title else chunks[0].capitalize()
            return f"{fn} {chunks[1].capitalize()}".strip()
        elif len(chunks) == 1:
            s = chunks[0]
            for fn in sorted(COMMON_FIRST_NAMES, key=len, reverse=True):
                if s.startswith(fn) and len(s) > len(fn):
                    rem = s[len(fn):]
                    if len(rem) >= 2 and rem.isalpha():
                        fn_cap = f"{title} {fn.capitalize()}".strip() if title else fn.capitalize()
                        return f"{fn_cap} {rem.capitalize()}".strip()
            for sn in sorted(COMMON_SURNAMES, key=len, reverse=True):
                if s.endswith(sn) and len(s) > len(sn):
                    prefix = s[:-len(sn)]
                    if len(prefix) >= 3 and prefix.isalpha():
                        fn_cap = f"{title} {prefix.capitalize()}".strip() if title else prefix.capitalize()
                        return f"{fn_cap} {sn.capitalize()}".strip()
            fn_cap = f"{title} {s.capitalize()}".strip() if title else s.capitalize()
            return fn_cap

    # 2. Check if internal digits act as a separator between two name tokens (e.g. saad0asif)
    digit_chunks = [c.strip().lower() for c in re.split(r"\d+", local_part) if c.strip()]
    if len(digit_chunks) >= 2:
        c0, c1 = digit_chunks[0], digit_chunks[1]
        if (c0 in COMMON_FIRST_NAMES or c1 in COMMON_SURNAMES) and len(c0) >= 2 and len(c1) >= 2 and c0.isalpha() and c1.isalpha():
            return f"{c0.capitalize()} {c1.capitalize()}"

    # 3. Direct clean stripped check (e.g. saad00 -> Saad, nomanghaffar074 -> Noman Ghaffar, rohaanashraf -> Rohaan Ashraf)
    clean_stripped = re.sub(r"\d+$", "", local_part).lower().strip()
    clean_alpha = re.sub(r"[\d._+-]+", "", clean_stripped)

    if clean_alpha in COMMON_FIRST_NAMES:
        return clean_alpha.capitalize()

    for fn in sorted(COMMON_FIRST_NAMES, key=len, reverse=True):
        if clean_alpha.startswith(fn) and len(clean_alpha) > len(fn):
            rem = clean_alpha[len(fn):]
            if len(rem) >= 2 and rem.isalpha() and rem not in ("oo", "ee", "o", "e", "a", "i", "s", "t"):
                return f"{fn.capitalize()} {rem.capitalize()}"

    for sn in sorted(COMMON_SURNAMES, key=len, reverse=True):
        if clean_alpha.endswith(sn) and len(clean_alpha) > len(sn):
            prefix = clean_alpha[:-len(sn)]
            if len(prefix) >= 3 and prefix.isalpha():
                return f"{prefix.capitalize()} {sn.capitalize()}"

    # 4. Leetspeak substitution ONLY for internal digits (e.g. tauq33raslam -> Tauqeer Aslam, n0manghaffar -> Noman Ghaffar)
    if any(c.isdigit() for c in clean_stripped):
        curr = clean_stripped
        for num, char in LEET_REPLACEMENTS:
            if num in curr:
                curr = curr.replace(num, char)
        curr_clean = re.sub(r"[\d._+-]+", "", curr).strip()

        if curr_clean in COMMON_FIRST_NAMES:
            return curr_clean.capitalize()

        for fn in sorted(COMMON_FIRST_NAMES, key=len, reverse=True):
            if curr_clean.startswith(fn) and len(curr_clean) > len(fn):
                rem = curr_clean[len(fn):]
                if len(rem) >= 2 and rem.isalpha() and rem not in ("oo", "ee", "o", "e", "a", "i", "s", "t"):
                    return f"{fn.capitalize()} {rem.capitalize()}"

        for sn in sorted(COMMON_SURNAMES, key=len, reverse=True):
            if curr_clean.endswith(sn) and len(curr_clean) > len(sn):
                prefix = curr_clean[:-len(sn)]
                if len(prefix) >= 3 and prefix.isalpha():
                    return f"{prefix.capitalize()} {sn.capitalize()}"

    return clean_alpha.capitalize() if len(clean_alpha) >= 3 else None


def normalize_location(raw_loc: Optional[str], fallback_country: Optional[str] = None) -> Optional[str]:
    """
    Normalizes location strings to guarantee that Country is always included.
    Formats additional info (City, State/Province) in standard form:
    e.g. 'Faisalabad' -> 'Faisalabad, Punjab, Pakistan'
         'Mountain View' -> 'Mountain View, California, United States'
         'San Francisco Bay Area' -> 'San Francisco Bay Area, California, United States'
         'San Francisco, CA' -> 'San Francisco, California, United States'
         'Pakistan' -> 'Pakistan'
    """
    if not raw_loc or not isinstance(raw_loc, str):
        return fallback_country.strip().title() if fallback_country else None

    loc = raw_loc.strip()
    if loc.lower() in ("utc", "none", "null", "unknown", "n/a", "undefined") or loc.upper().startswith("UTC"):
        return fallback_country.strip().title() if fallback_country else None

    # Handle composite timezones e.g. "Singapore / China" -> "Singapore"
    if " / " in loc:
        loc = loc.split(" / ")[0].strip()

    if fallback_country and " / " in fallback_country:
        fallback_country = fallback_country.split(" / ")[0].strip()

    loc_lower = loc.lower().rstrip(",. ")
    if loc_lower in KNOWN_CITIES:
        return KNOWN_CITIES[loc_lower]

    raw_parts = [p.strip() for p in loc.split(",") if p.strip()]
    if not raw_parts:
        return fallback_country.strip().title() if fallback_country else None

    # Deduplicate raw parts preserving order
    parts = []
    seen = set()
    for p in raw_parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            parts.append(p)

    # Check if first part matches known city
    first_part_lower = parts[0].lower()
    if first_part_lower in KNOWN_CITIES and len(parts) == 1:
        return KNOWN_CITIES[first_part_lower]

    last_part_lower = parts[-1].lower()

    # Check if last part is a US state abbreviation (e.g. "CA", "NY")
    if len(parts) >= 2 and last_part_lower in US_STATES:
        state_full = US_STATES[last_part_lower]
        parts[-1] = state_full
        parts.append("United States")
    elif last_part_lower in COUNTRY_CANONICAL:
        parts[-1] = COUNTRY_CANONICAL[last_part_lower]
    elif last_part_lower in [s.lower() for s in US_STATES.values()]:
        parts.append("United States")
    elif not any(p.lower() in ALL_COUNTRIES or p.lower() in COUNTRY_CANONICAL.values() or p.lower() in COUNTRY_CANONICAL for p in parts):
        if fallback_country:
            fb = fallback_country.strip()
            fb_canonical = COUNTRY_CANONICAL.get(fb.lower(), fb.title())
            # If the raw location was just a single unverified word that isn't a known city or state,
            # don't prepend it (e.g. avoid "Kertify, Pakistan"). Just return the valid fallback country!
            if len(parts) == 1 and parts[0].lower() not in KNOWN_CITIES and len(parts[0].split()) == 1 and not any(kw in parts[0].lower() for kw in ("district", "area", "region", "city", "valley", "province")):
                return fb_canonical
            if fb_canonical.lower() not in [p.lower() for p in parts]:
                parts.append(fb_canonical)
        elif first_part_lower in KNOWN_CITIES:
            return KNOWN_CITIES[first_part_lower]

    # Standardize casing, formatting, and final deduplication
    clean_parts = []
    seen_clean = set()
    for p in parts:
        p_strip = p.strip()
        canonical_val = COUNTRY_CANONICAL.get(p_strip.lower())
        if canonical_val:
            c_entry = canonical_val
        elif p_strip.lower() in ALL_COUNTRIES:
            c_entry = p_strip.title()
        else:
            c_entry = p_strip.title()

        if c_entry.lower() not in seen_clean:
            seen_clean.add(c_entry.lower())
            clean_parts.append(c_entry)

    return ", ".join(clean_parts)


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
                    cl = clean_social_url(url, "linkedin")
                    if cl: result["linkedin"] = cl
                elif "github" in label or "github.com" in url:
                    result["github_url"] = url
                elif "twitter" in label or "x.com" in url or "twitter.com" in url:
                    cl = clean_social_url(url, "twitter")
                    if cl: result["twitter_url"] = cl
                elif "instagram" in label or "instagram.com" in url:
                    cl = clean_social_url(url, "instagram")
                    if cl: result["instagram_url"] = cl
                elif "spotify" in label or "spotify.com" in url or "spotify:user" in url:
                    cl = clean_social_url(url, "spotify")
                    if cl: result["spotify_url"] = cl
                elif "youtube" in label or "youtube.com" in url:
                    result["youtube_url"] = url
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


RESERVED_SOCIAL_SLUGS = {
    "https", "http", "www", "com", "net", "org", "null", "undefined",
    "p", "reel", "reels", "stories", "explore", "direct", "accounts", "about", "developer", "legal",
    "dir", "pub", "feed", "jobs", "company", "school", "pulse", "posts", "learning",
    "home", "search", "notifications", "messages", "settings", "i", "privacy", "tos", "intent", "share",
    "sharer", "login", "recover", "help", "policies", "pages", "groups", "events", "watch", "photo", "photos", "video", "videos"
}


def clean_social_url(raw_url: Optional[str], platform: Optional[str] = None) -> Optional[str]:
    """
    Sanitizes raw social media URLs from bios, web pages, or markdown badges.
    Un-nests duplicated/nested schemes (e.g. 'https://linkedin.com/in/https://www.linkedin.com/in/slug').
    Discards invalid protocol slugs (e.g. 'https', 'www', 'dir', 'pub').
    """
    if not raw_url or not isinstance(raw_url, str):
        return None

    s = raw_url.strip().strip(")>]\'\",.")
    if not s:
        return None

    # Un-nest repeated protocols (common typo in markdown badge generators)
    m_nested = list(re.finditer(r"https?:/+", s, re.IGNORECASE))
    if len(m_nested) > 1:
        s = s[m_nested[-1].start():]
    # Normalize malformed https:/ to https://
    s = re.sub(r"^(https?):/+([^\s/])", r"\1://\2", s, flags=re.IGNORECASE)

    clean_low = s.lower()

    # 1. LinkedIn
    if "linkedin.com/in/" in clean_low and (platform is None or platform == "linkedin"):
        m = re.search(r"linkedin\.com/in/([a-zA-Z0-9_/%-]+)", s, re.IGNORECASE)
        if m:
            raw_slug = m.group(1).split("?")[0].split("#")[0].rstrip("/").strip()
            slug = raw_slug.split("/")[0].strip()
            if slug.lower() not in RESERVED_SOCIAL_SLUGS and len(slug) >= 3:
                return f"https://www.linkedin.com/in/{slug}"
        return None

    # 2. Instagram
    if "instagram.com/" in clean_low and (platform is None or platform == "instagram"):
        m = re.search(r"instagram\.com/([a-zA-Z0-9_.]{2,30})", s, re.IGNORECASE)
        if m:
            handle = m.group(1).split("?")[0].rstrip("/").strip().lstrip("@")
            if handle.lower() not in RESERVED_SOCIAL_SLUGS and len(handle) >= 2:
                return f"https://www.instagram.com/{handle}/"
        return None

    # 3. Twitter / X
    if any(dom in clean_low for dom in ("twitter.com/", "x.com/")) and (platform is None or platform == "twitter"):
        m = re.search(r"(?:x\.com|twitter\.com)/([a-zA-Z0-9_]{1,25})", s, re.IGNORECASE)
        if m:
            handle = m.group(1).split("?")[0].rstrip("/").strip().lstrip("@")
            if handle.lower() not in RESERVED_SOCIAL_SLUGS and len(handle) >= 2:
                return f"https://x.com/{handle}"
        return None

    # 4. Facebook
    if "facebook.com/" in clean_low and (platform is None or platform == "facebook"):
        m_ppl = re.search(r"facebook\.com/people/([^/?#]+)/(\d+)", s, re.IGNORECASE)
        if m_ppl:
            return f"https://www.facebook.com/people/{m_ppl.group(1)}/{m_ppl.group(2)}/"
        m = re.search(r"facebook\.com/([a-zA-Z0-9_.]{3,50})", s, re.IGNORECASE)
        if m:
            handle = m.group(1).split("?")[0].rstrip("/").strip()
            if handle.lower() not in RESERVED_SOCIAL_SLUGS and len(handle) >= 3:
                return f"https://www.facebook.com/{handle}"
        return None

    # 5. Spotify
    if ("spotify.com/user/" in clean_low or "spotify:user:" in clean_low) and (platform is None or platform == "spotify"):
        m = re.search(r"(?:spotify\.com/user/|spotify:user:)([a-zA-Z0-9_.-]{2,50})", s, re.IGNORECASE)
        if m:
            handle = m.group(1).split("?")[0].rstrip("/").strip()
            if handle.lower() not in RESERVED_SOCIAL_SLUGS and len(handle) >= 2:
                return f"https://open.spotify.com/user/{handle}"
        return None

    return None


def extract_clean_social_links_from_text(text: str) -> dict[str, str]:
    """Extract and sanitize social profile URLs from bio, blog, or README text."""
    if not text:
        return {}
    results = {}
    raw_urls = re.findall(r"https?://[^\s)\]\"'>]+", text)
    for raw in raw_urls:
        if not results.get("linkedin"):
            cl = clean_social_url(raw, platform="linkedin")
            if cl: results["linkedin"] = cl
        if not results.get("instagram"):
            cl = clean_social_url(raw, platform="instagram")
            if cl: results["instagram"] = cl
        if not results.get("twitter"):
            cl = clean_social_url(raw, platform="twitter")
            if cl: results["twitter"] = cl
        if not results.get("facebook"):
            cl = clean_social_url(raw, platform="facebook")
            if cl: results["facebook"] = cl
        if not results.get("spotify"):
            cl = clean_social_url(raw, platform="spotify")
            if cl: results["spotify"] = cl
    return results


# ── GitHub ────────────────────────────────────────────────────────────────────

async def lookup_github(
    email: str,
    client: httpx.AsyncClient,
    candidate_username: Optional[str] = None,
    cand_name: Optional[str] = None,
    cand_company: Optional[str] = None,
) -> Optional[dict]:
    """
    Find a verified GitHub profile from an email address.
    Strategy 1: Commit search API (100% accurate because Git commits are email-attributed).
    Strategy 2: User search API with verified public email matching.
    Extracts author name, profile URL, bio, repos, and commit timezone offset for geolocation.
    """
    headers = {**BROWSER_HEADERS, "Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    local_part = email.split("@")[0].lower() if "@" in email else ""
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

                domain = email.split("@")[-1].lower() if "@" in email else ""
                is_personal = domain in PERSONAL_DOMAINS

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

    # Strategy 5: Wikidata authoritative entity cross-reference
    if not username and cand_name:
        try:
            w_rec = await lookup_wikidata_entity(name=cand_name)
            if w_rec and w_rec.get("github_username"):
                username = w_rec.get("github_username")
                if not author_name_from_commit:
                    author_name_from_commit = w_rec.get("name")
        except Exception:
            pass

    # Strategy 6: Candidate full name and company/domain user search correlation
    if not username and cand_name and len(cand_name.split()) >= 2:
        try:
            search_q = f'"{cand_name}" in:name'
            resp = await client.get("https://api.github.com/search/users", params={"q": search_q}, headers=headers, timeout=6)
            if resp.status_code == 200:
                for item in resp.json().get("items", [])[:4]:
                    cand_login = item.get("login")
                    if cand_login:
                        u_resp = await client.get(f"https://api.github.com/users/{cand_login}", headers=headers, timeout=6)
                        if u_resp.status_code == 200:
                            u_dat = u_resp.json()
                            u_name = (u_dat.get("name") or "").strip()
                            if u_name.lower() == cand_name.lower():
                                u_comp = (u_dat.get("company") or "").lower()
                                u_bio = (u_dat.get("bio") or "").lower()
                                u_blog = (u_dat.get("blog") or "").lower()
                                target_comp = (cand_company or "").lower()
                                domain_anchor = email.split("@")[-1].split(".")[0].lower() if "@" in email else ""
                                if (target_comp and target_comp in u_comp) or (domain_anchor and domain_anchor in u_comp) or (target_comp and target_comp in u_bio) or (domain_anchor and domain_anchor in u_bio) or (domain_anchor and domain_anchor in u_blog):
                                    username = cand_login
                                    if u_name and not author_name_from_commit:
                                        author_name_from_commit = u_name
                                    break
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

                # Extract verified social links directly from GitHub profile (100% confidence):
                linkedin_direct = None
                twitter_direct = None
                if u.get("twitter_username"):
                    twitter_direct = f"https://x.com/{u['twitter_username'].strip()}"
                instagram_direct = None
                facebook_direct = None

                # 1. Official GitHub Social Accounts API
                if not isinstance(social_resp, Exception) and getattr(social_resp, "status_code", 0) == 200:
                    try:
                        for acc in social_resp.json():
                            prov = (acc.get("provider") or "").lower()
                            a_url = acc.get("url") or ""
                            if not linkedin_direct and (prov == "linkedin" or "linkedin.com/in" in a_url.lower()):
                                linkedin_direct = clean_social_url(a_url, platform="linkedin")
                            elif not twitter_direct and (prov in ("twitter", "x") or "twitter.com/" in a_url.lower() or "x.com/" in a_url.lower()):
                                twitter_direct = clean_social_url(a_url, platform="twitter")
                            elif not instagram_direct and (prov == "instagram" or "instagram.com/" in a_url.lower()):
                                instagram_direct = clean_social_url(a_url, platform="instagram")
                            elif not facebook_direct and (prov == "facebook" or "facebook.com/" in a_url.lower()):
                                facebook_direct = clean_social_url(a_url, platform="facebook")
                    except Exception:
                        pass

                # 2. Bio, blog, and README markdown links (with un-nesting)
                combined_texts = [bio_text, blog_text, (readme_text if isinstance(readme_text, str) else "")]
                for text_block in combined_texts:
                    if not text_block:
                        continue
                    extracted = extract_clean_social_links_from_text(text_block)
                    if not linkedin_direct and extracted.get("linkedin"):
                        linkedin_direct = extracted["linkedin"]
                    if not twitter_direct and extracted.get("twitter"):
                        twitter_direct = extracted["twitter"]
                    if not instagram_direct and extracted.get("instagram"):
                        instagram_direct = extracted["instagram"]
                    if not facebook_direct and extracted.get("facebook"):
                        facebook_direct = extracted["facebook"]

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
                    "twitter_url": twitter_direct,
                    "instagram_url": instagram_direct,
                    "facebook_url": facebook_direct,
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




async def fetch_linkedin_details(
    linkedin_url: Optional[str], client: httpx.AsyncClient
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[dict], Optional[dict], str]:
    """
    Extracts high-resolution round profile avatar, human location, full name,
    headline, current company/workplace, education/school, and persona role type
    directly from LinkedIn's OpenGraph and public page metadata using Twitterbot crawler.
    Returns (avatar_url, location, name, headline, company_data, education_data, role_type).
    """
    if not linkedin_url or "linkedin.com/in/" not in linkedin_url:
        return None, None, None, None, None, None, "individual"

    clean_url = clean_social_url(linkedin_url, platform="linkedin")
    if not clean_url:
        return None, None, None, None, None, None, "individual"
    avatar_url = None
    location = None
    name = None
    headline = None
    company_data = None
    education_data = None
    role_type = "individual"

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
            soup = BeautifulSoup(resp.text, "html.parser")

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

            # ── Extract Current Company (Workplace) ──
            top_comp = soup.find("a", attrs={"data-tracking-control-name": "public_profile_topcard-current-company"})
            if top_comp:
                name_el = top_comp.find(class_=lambda c: c and "top-card-link__description" in c)
                c_name = name_el.get_text(strip=True) if name_el else top_comp.get_text(strip=True)
                c_logo = None
                div_img = top_comp.find("div", attrs={"data-delayed-url": True})
                if div_img:
                    c_logo = div_img.get("data-delayed-url")
                elif top_comp.find("img"):
                    c_logo = top_comp.find("img").get("src")
                if c_name:
                    company_data = {
                        "name": c_name,
                        "logo": c_logo,
                        "url": top_comp.get("href", "").split("?")[0],
                        "type": "company",
                    }

            # ── Extract Education / School ──
            top_school = soup.find("a", attrs={"data-tracking-control-name": "public_profile_topcard-school"})
            if top_school:
                s_name_el = top_school.find(class_=lambda c: c and "top-card-link__description" in c)
                s_name = s_name_el.get_text(strip=True) if s_name_el else top_school.get_text(strip=True)
                s_logo = None
                div_s_img = top_school.find("div", attrs={"data-delayed-url": True})
                if div_s_img:
                    s_logo = div_s_img.get("data-delayed-url")
                elif top_school.find("img"):
                    s_logo = top_school.find("img").get("src")
                if s_name:
                    education_data = {
                        "name": s_name,
                        "logo": s_logo,
                        "url": top_school.get("href", "").split("?")[0],
                        "type": "school",
                    }

            # Fallbacks from meta description for company and education
            if not company_data and desc_m:
                exp_m = re.search(r"Experience:\s*([^·\n\r]+)", desc_m.group(1))
                if exp_m:
                    c_cand = exp_m.group(1).strip()
                    if c_cand:
                        company_data = {"name": c_cand, "logo": None, "url": None, "type": "company"}

            if not education_data and desc_m:
                edu_m = re.search(r"Education:\s*([^·\n\r]+)", desc_m.group(1))
                if edu_m:
                    s_cand = edu_m.group(1).strip()
                    if s_cand:
                        education_data = {"name": s_cand, "logo": None, "url": None, "type": "school"}

            # Headline extraction
            if raw_title:
                h_parts = [p.strip() for p in raw_title.split(" - ") if p.strip()]
                if len(h_parts) >= 2:
                    headline = h_parts[1].split(" | ")[0].strip()
            if not headline and desc_m:
                headline = desc_m.group(1).split(" · ")[0].strip()

            # ── Persona Role Classification ──
            h_lower = (headline or "").lower()
            student_kw = ["student", "undergraduate", "postgraduate", "bachelor", "master's", "candidate", "intern", "studying at"]
            faculty_kw = ["professor", "assistant professor", "associate professor", "lecturer", "instructor", "teacher", "faculty", "dean", "research fellow", "postdoc", "head of department", "hod"]

            if any(kw in h_lower for kw in faculty_kw):
                role_type = "faculty"
            elif any(kw in h_lower for kw in student_kw) or (education_data and not company_data):
                role_type = "student"
            elif company_data:
                role_type = "employee"

            # Normalize location with Country guarantee
            if location:
                location = normalize_location(location)

            return avatar_url, location, name, headline, company_data, education_data, role_type
    except Exception:
        pass

    if location:
        location = normalize_location(location)

    return avatar_url, location, name, headline, company_data, education_data, role_type


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


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text).strip()


def format_company_name_from_domain(stem: str) -> str:
    """Formats raw domain stems into proper company display names (e.g. contentarcade -> Content Arcade)."""
    if not stem:
        return ""
    if any(sep in stem for sep in ("-", "_", ".")):
        return " ".join(w.capitalize() for w in re.split(r"[-_.]", stem) if w)

    known_words = {
        "content", "arcade", "cloud", "tech", "soft", "system", "systems", "lab", "labs",
        "studio", "studios", "digital", "media", "data", "link", "net", "web", "app", "apps",
        "pay", "group", "holdings", "solutions", "global", "venture", "ventures", "capital",
        "secure", "security", "stream", "flow", "box", "hub", "stack", "point", "works",
        "kraft", "base", "smart", "wave", "logic", "logics", "matrix", "vision", "prime",
        "byte", "bytes", "code", "dev", "peak", "spark", "forge", "craft", "alpha", "beta",
        "space", "mind", "pulse", "care", "health", "life", "auto", "moto", "travel",
        "market", "shop", "store", "deal", "deals", "trade", "corp", "power", "energy"
    }

    s = stem.lower()
    for w in sorted(known_words, key=len, reverse=True):
        if s.startswith(w) and len(s) > len(w):
            rem = s[len(w):]
            if len(rem) >= 3 and (rem in known_words or rem.isalpha()):
                return f"{w.capitalize()} {rem.capitalize()}"

    return stem.capitalize()


PERSONAL_PORTFOLIO_TLDS = {".me", ".bio", ".page", ".link", ".site", ".dev", ".fyi", ".space", ".name"}


# ── Company enrichment (for corporate emails) ─────────────────────────────────

async def lookup_company(
    domain: str,
    client: httpx.AsyncClient,
    company_hint: Optional[str] = None,
) -> Optional[dict]:
    """
    Look up company intelligence from local company_domains (5.48M records)
    or fallback to Clearbit live autocomplete API with corporate domain synthesis guarantee.
    Works for corporate domains AND personal emails with company hints.
    """
    clean_dom = domain.lower().strip() if domain else ""
    is_personal = clean_dom in PERSONAL_DOMAINS or not clean_dom

    # Filter out personal portfolio domains from being treated as companies
    if company_hint:
        hint_low = company_hint.lower().strip()
        if any(hint_low.endswith(tld) or f"{tld}/" in hint_low for tld in PERSONAL_PORTFOLIO_TLDS):
            return None

    if is_personal and not company_hint:
        return None

    stem = clean_dom.split(".")[0] if clean_dom else ""

    # Step 1: Check local company_domains SQLite database (5.48M records, 0 ms offline)
    if os.path.exists(PROFILES_DB_PATH):
        try:
            async with aiosqlite.connect(PROFILES_DB_PATH, timeout=10.0) as db:
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.execute("PRAGMA busy_timeout=15000;")
                db.row_factory = aiosqlite.Row

                # Direct domain match (exact or stem)
                if not is_personal and clean_dom:
                    async with db.execute(
                        "SELECT * FROM company_domains WHERE domain = ? OR domain = ? LIMIT 1",
                        (clean_dom, f"{stem}.com")
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            r = dict(row)
                            c_dom = clean_dom or r.get("domain")
                            return {
                                "name": r.get("company_name") or format_company_name_from_domain(stem),
                                "domain": c_dom,
                                "logo": f"https://unavatar.io/{c_dom}",
                                "industry": r.get("industry"),
                                "country": r.get("country"),
                                "rank": r.get("rank"),
                                "email_format": r.get("email_format"),
                                "mx_provider": r.get("mx_provider"),
                                "source": "database",
                            }

                # Match by company_hint
                if company_hint:
                    hint = company_hint.strip()
                    if hint.startswith("@"):
                        hint = hint[1:].strip()
                    clean_h = re.sub(r"^(the|a)\s+", "", hint, flags=re.IGNORECASE)
                    clean_h = re.sub(r"\s+(inc\.?|llc\.?|ltd\.?|corp\.?|corporation|group|technologies|solutions|services|pvt\.?)$", "", clean_h, flags=re.IGNORECASE).strip()
                    if len(clean_h) >= 3:
                        h_clean = clean_h.lower()
                        h_slug = re.sub(r"\s+", "", h_clean)
                        async with db.execute(
                            """SELECT * FROM company_domains
                               WHERE domain = ? OR domain = ? OR domain = ? OR domain = ?
                                  OR LOWER(company_name) = ? OR LOWER(company_name) = ? OR LOWER(company_name) LIKE ?
                               ORDER BY rank ASC NULLS LAST LIMIT 1""",
                            (
                                f"{h_slug}.com", f"{h_clean}.com", h_slug, h_clean,
                                h_clean, f"the {h_clean}", f"%{h_clean}%"
                            )
                        ) as cursor:
                            row = await cursor.fetchone()
                            if row:
                                r = dict(row)
                                c_dom = r.get("domain") or f"{h_slug}.com"
                                return {
                                    "name": r.get("company_name") or hint.title(),
                                    "domain": c_dom,
                                    "logo": f"https://unavatar.io/{c_dom}",
                                    "industry": r.get("industry"),
                                    "country": r.get("country"),
                                    "rank": r.get("rank"),
                                    "email_format": r.get("email_format"),
                                    "mx_provider": r.get("mx_provider"),
                                    "source": "database",
                                }
        except Exception:
            pass

    # Step 2: Fallback to Clearbit Autocomplete API (Live fetching)
    query_candidates = []
    if company_hint and len(company_hint) >= 3:
        query_candidates.append(company_hint)
    elif not is_personal and clean_dom:
        query_candidates.append(clean_dom)
        if stem and stem != clean_dom:
            query_candidates.append(stem)

    for query_str in query_candidates:
        try:
            resp = await client.get(
                f"https://autocomplete.clearbit.com/v1/companies/suggest?query={query_str}",
                headers=BROWSER_HEADERS,
                timeout=5,
            )
            if resp.status_code == 200:
                companies = resp.json()
                for c in companies:
                    c_dom = c.get("domain") or ""
                    # Ensure candidate is not a personal portfolio domain
                    if any(c_dom.lower().endswith(tld) for tld in PERSONAL_PORTFOLIO_TLDS):
                        continue
                    return {
                        "name": c.get("name") or format_company_name_from_domain(stem),
                        "domain": clean_dom if not is_personal else c_dom,
                        "logo": c.get("logo") or (f"https://unavatar.io/{clean_dom or c_dom}"),
                        "industry": None,
                        "country": None,
                        "rank": None,
                        "email_format": None,
                        "mx_provider": None,
                        "source": "clearbit",
                    }
        except Exception:
            pass

    # Step 3: Synthesis Guarantee for Corporate Domains
    if not is_personal and clean_dom:
        return {
            "name": format_company_name_from_domain(stem),
            "domain": clean_dom,
            "logo": f"https://unavatar.io/{clean_dom}",
            "industry": None,
            "country": None,
            "rank": None,
            "email_format": None,
            "mx_provider": None,
            "source": "synthesis",
        }

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
        has_socials = bool(profiles.get("linkedin") or profiles.get("github"))
        dom = email.split("@")[-1].lower() if "@" in email else ""
        is_corp = bool(dom and dom not in PERSONAL_DOMAINS)
        comp_name = (company or {}).get("name") if (isinstance(company, dict) and (has_socials or is_corp)) else None

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
                        INSERT INTO harvested_profiles
                            (email, name, github_url, username, avatar_url, bio, location,
                             company, blog, followers, public_repos, linkedin_url, source, scraped_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(email) DO UPDATE SET
                            name         = COALESCE(excluded.name, name),
                            github_url   = COALESCE(excluded.github_url, github_url),
                            username     = COALESCE(excluded.username, username),
                            avatar_url   = COALESCE(excluded.avatar_url, avatar_url),
                            bio          = COALESCE(excluded.bio, bio),
                            location     = COALESCE(excluded.location, location),
                            company      = excluded.company,
                            blog         = COALESCE(excluded.blog, blog),
                            followers    = COALESCE(excluded.followers, followers),
                            public_repos = COALESCE(excluded.public_repos, public_repos),
                            linkedin_url = COALESCE(excluded.linkedin_url, linkedin_url),
                            scraped_at   = excluded.scraped_at
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
                        profiles.get("linkedin"),
                        "lookup_enrichment",
                        int(time.time()),
                    ))
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
    if not is_valid_email(email):
        return {
            "email": email,
            "email_type": "invalid",
            "domain": "",
            "query_time_ms": int((time.time() - start) * 1000),
            "person": {"name": None, "avatar": None, "bio": None, "location": None, "website": None},
            "profiles": {},
            "social_candidates": [],
            "social_candidates_by_platform": {},
            "phone": None,
            "address": None,
            "company": None,
            "deliverability": "invalid",
            "autocorrect": None,
        }

    domain = email.split("@")[-1] if "@" in email else ""
    local_part = email.split("@")[0].lower().strip() if "@" in email else ""

    email_type = "personal" if domain in PERSONAL_DOMAINS else "corporate"

    print(f"\n[Lookup Engine] >>> Starting reverse lookup for: {email} ({email_type.upper()})", flush=True)

    limits = httpx.Limits(max_connections=80, max_keepalive_connections=35)
    async with httpx.AsyncClient(timeout=8.0, limits=limits) as client:
        print("[Lookup Engine] Querying base sources (Gravatar, GitHub, Company DB)...", flush=True)
        # Phase 1: Run all base enrichment sources concurrently
        gravatar, github, company, harvested = await asyncio.gather(
            lookup_gravatar(email, client),
            lookup_github(email, client),
            lookup_company(domain, client),
            lookup_harvested_db(email),
            return_exceptions=True,
        )

        # Safe fallbacks
        if isinstance(gravatar, Exception): gravatar = {}
        if isinstance(github, Exception): github = None
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

        # ── Resolve name from best source: GitHub > Gravatar > Harvested DB ──
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
            if "." in local_part or "_" in local_part or "-" in local_part:
                raw_parts = [re.sub(r"\d+", "", p).strip("._-") for p in re.split(r"[._+-]", local_part)]
                clean_parts = [p for p in raw_parts if p and len(p) >= 2]
                if clean_parts:
                    parsed_chunks = []
                    for i, cp in enumerate(clean_parts):
                        if i == 0 and cp.lower() in TITLE_PREFIXES:
                            parsed_chunks.append(cp.capitalize())
                            continue
                        sub_split = split_concatenated_name(cp)
                        if sub_split:
                            parsed_chunks.extend(sub_split.split())
                        elif cp.isalpha():
                            parsed_chunks.append(cp.capitalize())
                    if parsed_chunks and parsed_chunks[-1].lower() in ROLE_SUFFIXES and len(parsed_chunks) >= 3:
                        parsed_chunks = parsed_chunks[:-1]
                    if len(parsed_chunks) >= 2 or (parsed_chunks and parsed_chunks[0].lower() not in TITLE_PREFIXES):
                        resolved_name = " ".join(parsed_chunks)

        # Parse concatenated names without delimiters (e.g. hassanrashid55 -> Hassan Rashid, chfahadahmad11 -> Ch Fahad Ahmad)
        if not resolved_name or not is_clean_human_name(resolved_name):
            cat_name = split_concatenated_name(local_part)
            if cat_name:
                resolved_name = cat_name

        # Fallback: if resolved_name is not yet found, check if GitHub username is CamelCase (e.g. AtisamHameed)
        if not resolved_name and github and isinstance(github, dict) and github.get("username"):
            gh_cand = github["username"]
            split_u = re.sub(r"([a-z])([A-Z])", r"\1 \2", gh_cand).strip()
            if " " in split_u and is_clean_human_name(split_u):
                resolved_name = split_u

        resolved_location = (
            gravatar.get("location")
            or (github.get("location") if github else None)
            or (harvested.get("location") if harvested else None)
        )

        # ── Phase 2: Contextual Anchored LinkedIn & Entity Resolution ──
        gh_u = (github.get("username") if isinstance(github, dict) else None) or (gravatar.get("gravatar_handle") if isinstance(gravatar, dict) else None) or (harvested.get("username") if isinstance(harvested, dict) else None)
        wikidata_record = await lookup_wikidata_entity(username=gh_u, name=resolved_name)

        # If GitHub profile was not resolved in Phase 1, try with resolved_name and wikidata
        if not github:
            cand_gh_user = wikidata_record.get("github_username") if wikidata_record else None
            comp_hint = company.get("name") if isinstance(company, dict) else None
            try:
                gh_lookup = await lookup_github(
                    email=email,
                    client=client,
                    candidate_username=cand_gh_user,
                    cand_name=resolved_name,
                    cand_company=comp_hint,
                )
                if gh_lookup:
                    github = gh_lookup
                    if not resolved_name and gh_lookup.get("name"):
                        resolved_name = gh_lookup.get("name")
            except Exception:
                pass

        # Priority 1: LinkedIn direct from GitHub (Social Accounts, Bio, Blog, README)
        gh_direct_linkedin = (github.get("linkedin_url") if isinstance(github, dict) else None)
        # Priority 2: Gravatar profile link
        gravatar_linkedin = gravatar.get("linkedin")
        # Priority 3: Local Harvested DB link
        harvested_linkedin = harvested.get("linkedin_url")
        # Priority 4: Wikidata authoritative entity cross-link
        wikidata_linkedin = wikidata_record.get("linkedin_url") if wikidata_record else None

        linkedin_source = None
        if gh_direct_linkedin:
            linkedin_url = gh_direct_linkedin
            linkedin_source = "github"
        elif gravatar_linkedin:
            linkedin_url = gravatar_linkedin
            linkedin_source = "gravatar"
        elif wikidata_linkedin:
            linkedin_url = wikidata_linkedin
            linkedin_source = "wikidata"
        elif harvested_linkedin:
            linkedin_url = harvested_linkedin
            linkedin_source = "harvested"
        else:
            linkedin_url = None

        linkedin_loc = None
        linkedin_confidence = 100 if linkedin_url else 0

        # If not direct/authoritative, LinkedIn candidate discovery is handled concurrently in Phase 3 (Social Discovery)

        # Fetch authentic LinkedIn details (avatar, human location, full name, headline, company, education, role)
        li_avatar = None
        li_name = None
        li_headline = None
        li_comp = None
        li_edu = None
        li_role = "individual"

        if linkedin_url:
            f_av, f_loc, f_name, f_head, f_comp, f_edu, f_role = await fetch_linkedin_details(linkedin_url, client)
            if f_av: li_avatar = f_av
            if f_loc: linkedin_loc = f_loc
            if f_name: li_name = f_name
            if f_head: li_headline = f_head
            if f_comp: li_comp = f_comp
            if f_edu: li_edu = f_edu
            if f_role: li_role = f_role

        # ── Name Sanity / Conflict Guard for External LinkedIn Profile ──
        # If the fetched LinkedIn profile has a clean human name that completely conflicts with all known identity clues
        # (e.g. GitHub name, Gravatar name, or email prefix), reject this LinkedIn profile as a mismatched or hijacked link.
        is_li_name_conflict = False
        target_name_clues = []
        if resolved_name:
            target_name_clues.append(resolved_name)
        if github and isinstance(github, dict) and github.get("name"):
            target_name_clues.append(github["name"])
        if github and isinstance(github, dict) and github.get("username"):
            target_name_clues.append(github["username"])
        if local_part:
            target_name_clues.append(local_part)

        if li_name and target_name_clues and is_clean_human_name(li_name):
            li_tokens = set(re.findall(r"[a-zA-Z]{3,}", li_name.lower()))
            clue_tokens = set()
            for clue in target_name_clues:
                for tok in re.findall(r"[a-zA-Z]{3,}", clue.lower()):
                    clue_tokens.add(tok)

            has_token_overlap = bool(li_tokens & clue_tokens)
            has_sub_match = any(
                any(t in c or c in t for c in clue_tokens if len(c) >= 4)
                for t in li_tokens if len(t) >= 4
            )

            if not has_token_overlap and not has_sub_match:
                sim = jaro_winkler_similarity(li_name.lower(), resolved_name.lower()) if resolved_name else 0.0
                if sim < 0.60:
                    is_li_name_conflict = True
                    print(f"[Lookup Engine] [WARN] Rejecting LinkedIn profile {linkedin_url} due to severe name conflict: LinkedIn='{li_name}' vs Target clues={target_name_clues}", flush=True)

        if is_li_name_conflict:
            linkedin_url = None
            linkedin_source = None
            linkedin_loc = None
            linkedin_confidence = 0
            li_avatar = None
            li_name = None
            li_headline = None
            li_comp = None
            li_edu = None
            li_role = "individual"

        # Fallback to LinkedIn name if resolved_name was not found through other channels
        if not resolved_name and li_name:
            resolved_name = li_name

        # ── Persona Role and Workplace / Education Card Resolution ──
        has_verified_li = bool(linkedin_url and linkedin_confidence == 100 and linkedin_source in ("github", "gravatar", "wikidata", "harvested"))

        # Check if the domain is a personal portfolio / vanity domain or synthetic domain
        is_synthetic_dom = bool(company and isinstance(company, dict) and company.get("source") == "synthesis")
        is_vanity_domain = bool(
            is_synthetic_dom
            or (domain and gh_u and (domain.startswith(gh_u.lower()) or gh_u.lower() in domain))
            or (domain and resolved_name and "".join(c for c in resolved_name.lower() if c.isalnum()) in domain.replace(".", ""))
            or (domain and any(domain.lower().endswith(tld) for tld in PERSONAL_PORTFOLIO_TLDS))
        )
        is_corporate_domain_company = bool(
            email_type == "corporate"
            and company
            and isinstance(company, dict)
            and not is_vanity_domain
            and company.get("source") in ("database", "clearbit")
            and (company.get("rank") is not None or company.get("industry") is not None)
        )

        # Priority 1: If verified LinkedIn provides a specific employer/workplace or student status,
        # prioritize it over synthetic/vanity domain fallbacks.
        if not is_corporate_domain_company or (has_verified_li and li_comp and li_comp.get("name") and is_vanity_domain):
            if li_role == "student" and li_edu:
                s_name = li_edu.get("name", "University")
                s_logo = li_edu.get("logo")
                s_dom = "fast.nu.edu.pk" if ("fast" in s_name.lower() or "emerging sciences" in s_name.lower()) else None
                company = {
                    "name": s_name,
                    "domain": s_dom,
                    "logo": s_logo or (f"https://www.google.com/s2/favicons?domain={s_dom}&sz=128" if s_dom else None),
                    "type": "education",
                    "role": "Student",
                    "industry": "Higher Education",
                    "country": None,
                    "rank": None,
                    "email_format": None,
                    "mx_provider": None,
                    "source": "linkedin",
                }
            elif li_role == "faculty" and (li_edu or li_comp):
                f_target = li_edu or li_comp
                f_name = f_target.get("name", "University")
                f_logo = f_target.get("logo")
                f_dom = "fast.nu.edu.pk" if ("fast" in f_name.lower() or "emerging sciences" in f_name.lower()) else None
                company = {
                    "name": f_name,
                    "domain": f_dom,
                    "logo": f_logo or (f"https://www.google.com/s2/favicons?domain={f_dom}&sz=128" if f_dom else None),
                    "type": "academic_workplace",
                    "role": "Faculty / Academic",
                    "industry": "Higher Education & Research",
                    "country": None,
                    "rank": None,
                    "email_format": None,
                    "mx_provider": None,
                    "source": "linkedin",
                }
            else:
                # Corporate employee or regular workplace
                if li_comp and li_comp.get("name") and has_verified_li:
                    c_name = li_comp["name"]
                    c_logo = li_comp.get("logo")
                    c_slug = li_comp.get("url", "").split("/company/")[-1].strip("/") if li_comp.get("url") else None
                    c_res = await lookup_company(domain="", client=client, company_hint=c_name)
                    c_dom = (c_res.get("domain") if c_res else None) or c_slug or (company.get("domain") if isinstance(company, dict) and not is_vanity_domain else "")
                    company = {
                        "name": c_name,
                        "domain": c_dom,
                        "logo": c_logo or (c_res.get("logo") if c_res else None) or (f"https://www.google.com/s2/favicons?domain={c_dom}&sz=128" if c_dom else None),
                        "industry": c_res.get("industry") if c_res else None,
                        "country": c_res.get("country") if c_res else None,
                        "rank": c_res.get("rank") if c_res else None,
                        "type": "workplace",
                        "alma_mater": li_edu.get("name") if li_edu else None,
                        "email_format": None,
                        "mx_provider": None,
                        "source": "linkedin",
                    }
                elif not company and harvested and harvested.get("company"):
                    h_c_name = harvested["company"]
                    c_res = await lookup_company(domain="", client=client, company_hint=h_c_name)
                    c_dom = (c_res.get("domain") if c_res else "") or ""
                    company = {
                        "name": h_c_name,
                        "domain": c_dom,
                        "logo": (c_res.get("logo") if c_res else None) or (f"https://www.google.com/s2/favicons?domain={c_dom}&sz=128" if c_dom else None),
                        "industry": c_res.get("industry") if c_res else None,
                        "country": c_res.get("country") if c_res else None,
                        "type": "workplace",
                        "alma_mater": li_edu.get("name") if li_edu else None,
                        "email_format": None,
                        "mx_provider": None,
                    }
                elif company and isinstance(company, dict):
                    if not company.get("logo") and li_comp and li_comp.get("logo"):
                        company["logo"] = li_comp["logo"]
                    if li_edu and not company.get("alma_mater"):
                        company["alma_mater"] = li_edu.get("name")
        else:
            # Corporate email domain is authoritative: only enrich non-conflicting metadata
            if company and isinstance(company, dict):
                if not company.get("logo") and li_comp and li_comp.get("logo") and has_verified_li:
                    company["logo"] = li_comp["logo"]
                if li_edu and not company.get("alma_mater"):
                    company["alma_mater"] = li_edu.get("name")

        # ── Location Hierarchy with Country Normalization Guarantee ──
        raw_location = (
            (linkedin_loc if has_verified_li else None)
            or (github.get("explicit_location") if github else None)
            or gravatar.get("location")
            or (harvested.get("location") if harvested else None)
            or (github.get("commit_timezone") if github else None)
        )
        fb_country = github.get("commit_timezone") if github else None
        resolved_location = normalize_location(raw_location, fallback_country=fb_country)

        # ── Profile picture hierarchy (Highest Priority: Verified LinkedIn) ──
        gh_avatar = github.get("avatar") if (github and isinstance(github, dict)) else None
        is_gh_default = await is_github_default_avatar(gh_avatar, client) if gh_avatar else False
        harvested_li_avatar = harvested.get("avatar_url") if (harvested and "licdn.com" in (harvested.get("avatar_url") or "")) else None

        if li_avatar and has_verified_li:
            resolved_avatar = li_avatar
        elif harvested_li_avatar:
            resolved_avatar = harvested_li_avatar
            print(f"[Lookup Engine] Using verified LinkedIn headshot from database: {harvested_li_avatar[:60]}...", flush=True)
        elif gh_avatar and not is_gh_default:
            resolved_avatar = gh_avatar
        elif harvested and harvested.get("avatar_url") and not ("gravatar.com" in (harvested.get("avatar_url") or "")):
            resolved_avatar = harvested.get("avatar_url")
        elif gravatar.get("avatar") and not ("gravatar.com/avatar" in gravatar.get("avatar") and "d=mp" in gravatar.get("avatar")):
            resolved_avatar = gravatar.get("avatar")
        elif gh_avatar:
            resolved_avatar = gh_avatar
        else:
            resolved_avatar = None

        # ── Fallback Company Resolution (from GitHub / Harvested / Email keywords) ──
        if not company:
            gh_comp = github.get("company") if isinstance(github, dict) else None
            h_comp = (
                harvested.get("company")
                if (isinstance(harvested, dict) and (harvested.get("source") != "lookup_enrichment" or (github or linkedin_url)))
                else None
            )
            cand_comp = gh_comp or h_comp

            if cand_comp:
                company = await lookup_company(domain="", client=client, company_hint=cand_comp)

            if not company and email_type == "corporate" and local_part:
                name_parts = set(re.findall(r"\w+", (resolved_name or "").lower()))
                for chunk in re.split(r"[._+-]", local_part):
                    if len(chunk) >= 4 and not chunk.isdigit() and chunk not in name_parts:
                        c_test = await lookup_company(domain="", client=client, company_hint=chunk)
                        if c_test:
                            company = c_test
                            break

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
        profiles["linkedin"] = {
            "url": linkedin_url,
            "confidence": linkedin_confidence,
            "verified": (linkedin_confidence == 100),
            "source": linkedin_source or "search",
            "avatar_url": li_avatar if isinstance(li_avatar, str) else None,
            "avatar": li_avatar if isinstance(li_avatar, str) else None,
        }
        profiles["linkedin_confidence"] = linkedin_confidence
        profiles["linkedin_verified"] = (linkedin_confidence == 100)
        profiles["linkedin_source"] = linkedin_source or "search"

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

    # Direct socials from verified GitHub & Gravatar profiles (100% confirmed)
    dir_twitter = (github.get("twitter_url") if isinstance(github, dict) else None) or (gravatar.get("twitter_url") if isinstance(gravatar, dict) else None)
    dir_instagram = (github.get("instagram_url") if isinstance(github, dict) else None) or (gravatar.get("instagram_url") if isinstance(gravatar, dict) else None)
    dir_facebook = (github.get("facebook_url") if isinstance(github, dict) else None)
    dir_spotify = gravatar.get("spotify_url") if isinstance(gravatar, dict) else None
    dir_tiktok = gravatar.get("tiktok_url") if isinstance(gravatar, dict) else None
    dir_pinterest = gravatar.get("pinterest_url") if isinstance(gravatar, dict) else None
    dir_youtube = gravatar.get("youtube_url") if isinstance(gravatar, dict) else None

    # Probe direct verified profile links concurrently for authentic avatars & display names
    # Uses the same probe engines and Pathfinder GraphQL queries as candidate discovery
    async def probe_direct_profile(plat, url, dir_client):
        if not url:
            return None
        try:
            handle = url.rstrip("/").split("/")[-1].replace("@", "")
            if plat == "twitter" and handle:
                return await probe_twitter_profile(handle, dir_client)
            elif plat == "instagram" and handle:
                # Use a dedicated proxy client for Instagram — direct IPs get bot-blocked
                proxy_url = get_random_proxy_url()
                if proxy_url:
                    try:
                        async with httpx.AsyncClient(proxy=proxy_url, timeout=5.0, follow_redirects=True, verify=False) as px:
                            return await probe_instagram_profile(handle, px)
                    except Exception:
                        pass
                # Fallback to direct client if no proxy available
                return await probe_instagram_profile(handle, dir_client)
            elif plat == "spotify" and handle:
                # Primary: Use Spotify Pathfinder GraphQL search (identical to candidate pipeline)
                try:
                    pf_results = await search_spotify_users_pathfinder(handle, dir_client, limit=5)
                    if pf_results:
                        for u in pf_results:
                            if u.get("handle") == handle or u.get("avatar_url"):
                                return u
                except Exception:
                    pass
                # Secondary fallback: scrape open.spotify.com profile
                return await probe_spotify_profile(handle, dir_client)
            elif plat == "facebook" and handle:
                d = await probe_facebook_profile(handle, dir_client)
                if d:
                    return d
                fb_av = await fetch_facebook_candidate_avatar(url, dir_client)
                return {"avatar_url": fb_av} if fb_av else None
            elif plat == "tiktok" and handle:
                return await probe_tiktok_profile(handle, dir_client)
            elif plat == "pinterest" and handle:
                return await probe_pinterest_profile(handle, dir_client)
        except Exception:
            pass
        return None

    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as dir_client:
        tw_res, ig_res, fb_res, sp_res, tt_res, pin_res = await asyncio.gather(
            probe_direct_profile("twitter", dir_twitter, dir_client),
            probe_direct_profile("instagram", dir_instagram, dir_client),
            probe_direct_profile("facebook", dir_facebook, dir_client),
            probe_direct_profile("spotify", dir_spotify, dir_client),
            probe_direct_profile("tiktok", dir_tiktok, dir_client),
            probe_direct_profile("pinterest", dir_pinterest, dir_client),
            return_exceptions=True,
        )

    if dir_twitter and isinstance(tw_res, dict) and tw_res.get("name"):
        tw_d = tw_res
        tw_av = tw_d.get("avatar_url")
        tw_name = tw_d.get("name")
        tw_handle = tw_d.get("handle") or dir_twitter.rstrip("/").split("/")[-1].replace("@", "")
        profiles["twitter"] = {
            "url": dir_twitter,
            "handle": f"@{tw_handle}" if tw_handle else "@twitter",
            "name": tw_name,
            "source": "github" if (github and github.get("twitter_url")) else "gravatar",
            "confidence": 100,
            "verified": True,
            "avatar_url": tw_av if isinstance(tw_av, str) else None,
            "avatar": tw_av if isinstance(tw_av, str) else None,
        }

    if dir_instagram and isinstance(ig_res, dict) and ig_res.get("name"):
        ig_d = ig_res
        ig_av = ig_d.get("avatar_url")
        ig_name = ig_d.get("name")
        ig_handle = ig_d.get("handle") or dir_instagram.rstrip("/").split("/")[-1].replace("@", "")
        profiles["instagram"] = {
            "url": dir_instagram,
            "handle": f"@{ig_handle}" if ig_handle else "@instagram",
            "name": ig_name,
            "source": "github" if (github and github.get("instagram_url")) else "gravatar",
            "confidence": 100,
            "verified": True,
            "avatar_url": ig_av if isinstance(ig_av, str) else None,
            "avatar": ig_av if isinstance(ig_av, str) else None,
        }

    if dir_facebook and isinstance(fb_res, dict) and (fb_res.get("name") or fb_res.get("avatar_url")):
        fb_d = fb_res
        fb_av = fb_d.get("avatar_url")
        fb_name = fb_d.get("name")
        fb_handle = dir_facebook.rstrip("/").split("/")[-1].replace("@", "")
        profiles["facebook"] = {
            "url": dir_facebook,
            "handle": f"@{fb_handle}" if fb_handle else "@facebook",
            "name": fb_name,
            "source": "github",
            "confidence": 100,
            "verified": True,
            "avatar_url": fb_av if isinstance(fb_av, str) else None,
            "avatar": fb_av if isinstance(fb_av, str) else None,
        }

    if dir_spotify and isinstance(sp_res, dict) and sp_res.get("name"):
        sp_d = sp_res
        sp_av = sp_d.get("avatar_url")
        sp_name = sp_d.get("name")
        sp_handle = sp_d.get("handle") or dir_spotify.rstrip("/").split("/")[-1].replace("@", "")
        profiles["spotify"] = {
            "url": dir_spotify,
            "handle": f"@{sp_handle}" if sp_handle else "Profile",
            "name": sp_name,
            "source": "gravatar",
            "confidence": 100,
            "verified": True,
            "avatar_url": sp_av if isinstance(sp_av, str) else None,
            "avatar": sp_av if isinstance(sp_av, str) else None,
        }

    if dir_tiktok and isinstance(tt_res, dict) and tt_res.get("name"):
        tt_d = tt_res
        tt_av = tt_d.get("avatar_url")
        tt_name = tt_d.get("name")
        tt_handle = tt_d.get("handle") or dir_tiktok.rstrip("/").split("/")[-1].replace("@", "")
        profiles["tiktok"] = {
            "url": dir_tiktok,
            "handle": f"@{tt_handle}" if tt_handle else "@tiktok",
            "name": tt_name,
            "source": "gravatar",
            "confidence": 100,
            "verified": True,
            "avatar_url": tt_av if isinstance(tt_av, str) else None,
            "avatar": tt_av if isinstance(tt_av, str) else None,
        }

    if dir_pinterest and isinstance(pin_res, dict) and pin_res.get("name"):
        pin_d = pin_res
        pin_av = pin_d.get("avatar_url")
        pin_name = pin_d.get("name")
        pin_handle = pin_d.get("handle") or dir_pinterest.rstrip("/").split("/")[-1].replace("@", "")
        profiles["pinterest"] = {
            "url": dir_pinterest,
            "handle": f"@{pin_handle}" if pin_handle else "@pinterest",
            "name": pin_name,
            "source": "gravatar",
            "confidence": 100,
            "verified": True,
            "avatar_url": pin_av if isinstance(pin_av, str) else None,
            "avatar": pin_av if isinstance(pin_av, str) else None,
        }

    if dir_youtube:
        profiles["youtube"] = {
            "url": dir_youtube,
            "source": "gravatar",
            "confidence": 100,
            "verified": True,
            "avatar_url": None,
        }

    if github and isinstance(github, dict) and github.get("username"):
        print(f"[GitHub] [+] Found user: @{github['username']} (repos={github.get('repos')}, followers={github.get('followers')})", flush=True)
    else:
        print("[GitHub] [-] No verified profile found.", flush=True)

    if gravatar and (gravatar.get("avatar") or gravatar.get("name")):
        print(f"[Gravatar] [+] Verified Gravatar profile found (name='{gravatar.get('name')}')", flush=True)

    if linkedin_url:
        print(f"[LinkedIn] [+] Corroborated LinkedIn: {linkedin_url} (Confidence: {linkedin_confidence}%, Source: {linkedin_source})", flush=True)

    if company and company.get("name"):
        print(f"[Company] [+] Workplace identified: {company['name']} ({company.get('domain', '')})", flush=True)

    # ── Discover Candidate Social Accounts (LinkedIn, Twitter/X, Instagram, Facebook) ──
    gh_user = github.get("username") if (github and isinstance(github, dict)) else None
    comp_name = company.get("name") if (company and isinstance(company, dict)) else None
    social_candidates = []
    # Compute set of platforms that already have a verified profile link
    verified_platforms = set()
    if has_verified_li:
        verified_platforms.add("linkedin")
    for p, data in profiles.items():
        if data and (isinstance(data, dict) and (data.get("verified") or data.get("source") in ("github", "gravatar", "wikidata", "harvested"))):
            verified_platforms.add(p)

    phase1_elapsed_ms = int((time.time() - start) * 1000)
    print(f"\n[Lookup Engine] Base Enrichment (Phase 1 & 2) completed in {phase1_elapsed_ms}ms (Gravatar, GitHub, Wikidata, Company, DB)", flush=True)
    print(f"[Lookup Engine] Launching Phase 3: High-Concurrency Social Discovery...", flush=True)

    try:
        raw_candidates, by_plat = await search_social_candidates(
            email=email,
            resolved_name=resolved_name,
            resolved_location=resolved_location,
            gh_username=gh_user,
            company_name=comp_name,
            client=client,
            has_verified_linkedin=has_verified_li,
            verified_platforms=verified_platforms,
            anchor_avatar=resolved_avatar or person.get("avatar"),
            anchor_website=person.get("website"),
            anchor_profiles=profiles,
        )

        # If a search-discovered LinkedIn candidate was found during base checks, add it to candidates list if not present
        if linkedin_url and not has_verified_li:
            li_slug = linkedin_url.split("linkedin.com/in/")[-1].strip("/")
            existing_li_urls = [c.get("url") for c in by_plat.get("linkedin", [])]
            if linkedin_url not in existing_li_urls:
                cand_li = {
                    "platform": "linkedin",
                    "platform_label": "LinkedIn",
                    "handle": f"@{li_slug}",
                    "name": resolved_name or li_slug,
                    "url": linkedin_url,
                    "snippet": f"LinkedIn profile for {resolved_name or li_slug}",
                    "score": linkedin_confidence or 80,
                    "confidence_badge": "",
                    "confidence_level": "strong" if (linkedin_confidence or 80) >= 70 else "potential",
                    "reasons": [f"Discovered via name anchor search ({linkedin_source})"],
                    "avatar_url": li_avatar,
                }
                by_plat.setdefault("linkedin", []).insert(0, cand_li)
                raw_candidates.insert(0, cand_li)

        # ── Zero Duplicate Platform Rule ──
        for p in ["linkedin", "github", "stackoverflow", "medium", "instagram", "twitter", "facebook", "tiktok", "pinterest", "spotify"]:
            prof = profiles.get(p)
            is_direct_verified = False
            if p == "github":
                is_direct_verified = bool(prof)
            elif isinstance(prof, dict):
                is_direct_verified = (
                    prof.get("verified") is True
                    or prof.get("source") in ("github", "gravatar", "wikidata", "harvested")
                )
            elif isinstance(prof, str) and p == "linkedin":
                is_direct_verified = has_verified_li

            if is_direct_verified:
                # Ensure direct verified profile carries an avatar_url if available from candidate probes or person avatar
                if isinstance(prof, dict):
                    if not prof.get("avatar_url") and not prof.get("avatar"):
                        p_url = (prof.get("url") or "").rstrip("/").lower()
                        p_handle = p_url.split("/").pop().replace("@", "")
                        for cand in raw_candidates:
                            if cand.get("platform") == p and cand.get("avatar_url"):
                                c_url = (cand.get("url") or "").rstrip("/").lower()
                                c_handle = (cand.get("handle") or "").replace("@", "").lower()
                                if (p_handle and c_handle == p_handle) or (p_url and (p_url in c_url or c_url in p_url)):
                                    prof["avatar_url"] = cand["avatar_url"]
                    # Note: We do not copy person.avatar across platforms so each verified chip only shows its own platform avatar if found.

                # Platform is already confirmed and verified in top profiles — clear candidate accordion
                by_plat[p] = []
            else:
                if p != "github":
                    # No confirmed direct profile exists — remove from top profiles so it only appears in candidate accordion
                    profiles.pop(p, None)
                    profiles.pop(f"{p}_confidence", None)
                    profiles.pop(f"{p}_verified", None)
                    profiles.pop(f"{p}_source", None)

        social_candidates = raw_candidates
        candidates_by_platform = by_plat
    except Exception as e:
        print(f"[Social Discovery] Candidate search error: {e}", flush=True)
        social_candidates = []
        candidates_by_platform = {"linkedin": [], "github": [], "stackoverflow": [], "medium": [], "instagram": [], "twitter": [], "facebook": [], "tiktok": [], "pinterest": [], "spotify": []}

    # ── Fallback Person Display Name from Clean Email Username ──
    # Note: Speculative social candidates are never promoted to the person card to prevent unverified data pollution
    if not person.get("name") and local_part:
        concatenated_name = split_concatenated_name(local_part)
        if concatenated_name:
            person["name"] = concatenated_name
            print(f"[Lookup Engine] Inferred name from email username: '{concatenated_name}'", flush=True)

    # ── Strict Company Visibility Policy ──
    # If this is a personal email (gmail, hey, proton, etc.) or vanity domain, ONLY show company/workplace data if verified by
    # a confirmed LinkedIn employment/education record, verified database company, or verified GitHub company record.
    has_verified_employment = bool(
        has_verified_li
        or (github and isinstance(github, dict) and github.get("company"))
        or (company and isinstance(company, dict) and (company.get("type") in ("education", "academic_workplace") or company.get("source") in ("database", "clearbit", "linkedin")))
    )
    if (email_type == "personal" or is_vanity_domain) and not has_verified_employment:
        company = None

    # ── Phone from GitHub bio ──
    phone = github.get("phone_from_bio") if github else None

    elapsed_ms = int((time.time() - start) * 1000)
    print(f"[Lookup Engine] <<< Reverse lookup complete for '{email}' in {elapsed_ms}ms.\n", flush=True)

    return {
        "email": email,
        "email_type": email_type,
        "domain": domain,
        "query_time_ms": elapsed_ms,
        "person": person,
        "profiles": profiles,
        "social_candidates": social_candidates,
        "social_candidates_by_platform": candidates_by_platform,
        "phone": phone,
        "address": None,
        "company": company,
        "autocorrect": None,
    }

