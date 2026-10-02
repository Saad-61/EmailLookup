"""
social_finder.py
----------------
Discovers and scores candidate accounts on LinkedIn, Instagram, TikTok, Pinterest,
Twitter/X, Facebook, and GitHub using:
1. High-concurrency direct OpenGraph / crawler probing across 5 platforms.
2. Clean single-site search queries via SearXNG (Yandex + Startpage).
3. Smart compound name parsing (e.g. nomanghaffar074 -> Noman Ghaffar).
4. Multi-anchor scoring with Jaro-Winkler similarity, surname disambiguation,
   and company/location corroboration.
"""

import asyncio
import os
import random
import re
import html
import urllib.parse
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
import io
from typing import List, Optional, Dict, Any, Tuple, Set
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"), override=True)

try:
    from constants import (
        TITLE_PREFIXES, ROLE_SUFFIXES, COMMON_FIRST_NAMES, COMMON_SURNAMES,
        LEET_REPLACEMENTS, RESERVED_SYSTEM_SLUGS
    )
except ImportError:
    from backend.constants import (
        TITLE_PREFIXES, ROLE_SUFFIXES, COMMON_FIRST_NAMES, COMMON_SURNAMES,
        LEET_REPLACEMENTS, RESERVED_SYSTEM_SLUGS
    )

# ==========================================
# Spotify Token Cache (sp_dc auto-refresh)
# ==========================================
_spotify_token_cache: Dict[str, Any] = {
    "access_token": "",
    "client_token": "",
    "expires_at": 0.0,  # Unix timestamp
}
_spotify_refresh_lock = asyncio.Lock()


# ==========================================
# 1. STRING SIMILARITY & JARO-WINKLER
# ==========================================
def jaro_similarity(s1: str, s2: str) -> float:
    """Compute standard Jaro similarity between two strings."""
    if not s1 or not s2:
        return 1.0 if s1 == s2 else 0.0
    if s1 == s2:
        return 1.0

    len1, len2 = len(s1), len(s2)
    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    transpositions //= 2
    return (matches / len1 + matches / len2 + (matches - transpositions) / matches) / 3.0


def jaro_winkler_similarity(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    """
    Compute Jaro-Winkler similarity with prefix bonus.
    Accounts for common transliterations and minor spelling variations.
    """
    s1_clean = (s1 or "").strip().lower()
    s2_clean = (s2 or "").strip().lower()
    if not s1_clean or not s2_clean:
        return 1.0 if s1_clean == s2_clean else 0.0
    if s1_clean == s2_clean:
        return 1.0

    j_sim = jaro_similarity(s1_clean, s2_clean)

    prefix_len = 0
    for c1, c2 in zip(s1_clean[:4], s2_clean[:4]):
        if c1 == c2:
            prefix_len += 1
        else:
            break

    return min(1.0, j_sim + (prefix_len * prefix_weight * (1.0 - j_sim)))


# ==========================================
# 2. DYNAMIC RESIDENTIAL PROXY POOL
# ==========================================
PROXY_USER = os.getenv("PROXY_USERNAME", "").strip()
PROXY_PASS = os.getenv("PROXY_PASSWORD", "").strip()
RAW_IPS = os.getenv("PROXY_IPS", "").strip()
ALL_PROXY_IPS = [ip.strip() for ip in RAW_IPS.split(",") if ip.strip()]
PROXY_IPS = ALL_PROXY_IPS


class DynamicProxyPool:
    """
    Manages residential proxy IPs with automatic rate-limit cooldown, progressive backoff, and latency-based ranking.
    - Tracks temporary 202 blocks with an adaptive expiration timestamp (e.g. 10m -> 30m for repeat offenders).
    - Automatically measures roundtrip response time on every query to route requests to the fastest nodes.
    - When cooldown expires, the proxy automatically re-joins the active pool.
    """
    def __init__(self, ip_list: List[str], cooldown_seconds: int = 600):
        self.all_ips = list(ip_list)
        self.cooldown_seconds = cooldown_seconds
        self.cooldowns: Dict[str, float] = {}
        self.failures: Dict[str, int] = {ip: 0 for ip in self.all_ips}
        # ip -> estimated latency in ms (pre-seeded with default 1500ms)
        self.latencies: Dict[str, float] = {ip: 1500.0 for ip in self.all_ips}

    def get_clean_ips(self) -> List[str]:
        """Returns all IPs whose cooldown has expired, ranked by lowest latency first."""
        now = time.time()
        clean = [ip for ip in self.all_ips if self.cooldowns.get(ip, 0) <= now]
        if not clean and self.all_ips:
            return sorted(self.all_ips, key=lambda ip: self.cooldowns.get(ip, 0))[:5]
        # Rank by latency with slight jitter for balanced load distribution
        return sorted(clean, key=lambda ip: self.latencies.get(ip, 2000.0) + random.uniform(0, 150))

    def mark_challenged(self, ip: str, duration: Optional[int] = None):
        """Flag an IP that encountered a 202 challenge or block with progressive backoff."""
        self.failures[ip] = self.failures.get(ip, 0) + 1
        # Progressive backoff: 10m -> 20m -> 30m for chronic failures
        multiplier = min(3, self.failures[ip])
        cd = duration or (self.cooldown_seconds * multiplier)
        self.cooldowns[ip] = time.time() + cd
        self.latencies[ip] = 9999.0
        remaining = len(self.get_clean_ips())
        print(f"  [ProxyPool] [COOLDOWN] IP {ip} flagged ({self.failures[ip]} fails) with {cd}s cooldown ({remaining} clean IPs remaining in pool)", flush=True)

    def mark_healthy(self, ip: str, elapsed_ms: Optional[int] = None):
        """Confirm an IP is clean, reset failure counters, and update its moving-average latency score."""
        if ip in self.cooldowns:
            del self.cooldowns[ip]
        self.failures[ip] = 0
        if elapsed_ms is not None:
            prev = self.latencies.get(ip, float(elapsed_ms))
            self.latencies[ip] = prev * 0.35 + float(elapsed_ms) * 0.65

    def sample_distinct(self, n: int) -> List[str]:
        """Sample n distinct clean IPs, prioritizing the fastest responsive nodes."""
        clean = self.get_clean_ips()
        if len(clean) >= n:
            return clean[:n]
        return (clean * (n // max(1, len(clean)) + 1))[:n]


proxy_pool = DynamicProxyPool(ALL_PROXY_IPS, cooldown_seconds=600)


def get_random_proxy_url() -> Optional[str]:
    """Construct randomized proxy URL from fastest clean residential proxies in pool."""
    clean_ips = proxy_pool.get_clean_ips()
    if not clean_ips:
        return None
    ip = random.choice(clean_ips[:5]) if len(clean_ips) >= 5 else random.choice(clean_ips)
    if PROXY_USER and PROXY_PASS:
        return f"http://{PROXY_USER}:{PROXY_PASS}@{ip}"
    return f"http://{ip}"


try:
    from constants import (
        TITLE_PREFIXES, ROLE_SUFFIXES, COMMON_FIRST_NAMES, LEET_REPLACEMENTS,
        RESERVED_SYSTEM_SLUGS, GENERIC_WORDS, CRAWLER_HEADERS, TWITTER_HEADERS, LI_CRAWLER_HEADERS
    )
except ImportError:
    from backend.constants import (
        TITLE_PREFIXES, ROLE_SUFFIXES, COMMON_FIRST_NAMES, LEET_REPLACEMENTS,
        RESERVED_SYSTEM_SLUGS, GENERIC_WORDS, CRAWLER_HEADERS, TWITTER_HEADERS, LI_CRAWLER_HEADERS
    )


def normalize_handle_leetspeak(text: str) -> List[str]:
    """Generates candidate normalized strings by substituting leetspeak digits with letters."""
    if not text:
        return []
    variants = [text.lower()]
    curr = text.lower()
    for num, char in LEET_REPLACEMENTS:
        if num in curr:
            curr = curr.replace(num, char)
            variants.append(curr)
    return list(dict.fromkeys(variants))


def split_compound_name(local_part: str) -> Tuple[str, str]:
    """
    Splits compound local-part (e.g. tauq33raslam -> Tauqeer Aslam, ch.fahadahmad11 -> Ch Fahad Ahmad, sarah.jenkins.hr -> Sarah Jenkins, nomanghaffar074 -> Noman Ghaffar).
    Returns (first_name, last_name) or (full_inferred_name, "").
    """
    if not local_part:
        return "", ""

    # 1. Check for explicit delimiters (., _, -) e.g. sarah.jenkins.hr, ch.fahadahmad11, john_doe
    if any(sep in local_part for sep in (".", "_", "-")):
        chunks = [re.sub(r"[\d._+-]+", "", c).strip().lower() for c in re.split(r"[._+-]", local_part)]
        chunks = [c for c in chunks if len(c) >= 2]
        if chunks and chunks[-1] in ROLE_SUFFIXES and len(chunks) >= 2:
            chunks = chunks[:-1]

        # Strip title prefix if present in first chunk (e.g. ['ch', 'fahadahmad'])
        title = ""
        if chunks and chunks[0] in TITLE_PREFIXES and len(chunks) >= 2:
            title = chunks[0].capitalize()
            chunks = chunks[1:]

        if len(chunks) >= 2:
            fn = f"{title} {chunks[0].capitalize()}".strip() if title else chunks[0].capitalize()
            return fn, chunks[1].capitalize()
        elif len(chunks) == 1:
            s = chunks[0]
            for fn in sorted(COMMON_FIRST_NAMES, key=len, reverse=True):
                if s.startswith(fn) and len(s) > len(fn):
                    rem = s[len(fn):]
                    if len(rem) >= 2 and rem.isalpha():
                        fn_cap = f"{title} {fn.capitalize()}".strip() if title else fn.capitalize()
                        return fn_cap, rem.capitalize()
            for sn in sorted(COMMON_SURNAMES, key=len, reverse=True):
                if s.endswith(sn) and len(s) > len(sn):
                    prefix = s[:-len(sn)]
                    if len(prefix) >= 3 and prefix.isalpha():
                        fn_cap = f"{title} {prefix.capitalize()}".strip() if title else prefix.capitalize()
                        return fn_cap, sn.capitalize()
            fn_cap = f"{title} {s.capitalize()}".strip() if title else s.capitalize()
            return fn_cap, ""

    # 2. Check if internal digits act as a separator between two name tokens (e.g. saad0asif, john2doe)
    digit_chunks = [c.strip().lower() for c in re.split(r"\d+", local_part) if c.strip()]
    if len(digit_chunks) >= 2:
        c0, c1 = digit_chunks[0], digit_chunks[1]
        if (c0 in COMMON_FIRST_NAMES or c1 in COMMON_SURNAMES) and len(c0) >= 2 and len(c1) >= 2 and c0.isalpha() and c1.isalpha():
            return c0.capitalize(), c1.capitalize()

    # 3. Direct clean stripped check (e.g. saad00 -> Saad, nomanghaffar074 -> Noman Ghaffar, rohaanashraf -> Rohaan Ashraf)
    clean_stripped = re.sub(r"\d+$", "", local_part).lower().strip()
    clean_alpha = re.sub(r"[\d._+-]+", "", clean_stripped)

    if clean_alpha in COMMON_FIRST_NAMES:
        return clean_alpha.capitalize(), ""

    for fn in sorted(COMMON_FIRST_NAMES, key=len, reverse=True):
        if clean_alpha.startswith(fn) and len(clean_alpha) > len(fn):
            rem = clean_alpha[len(fn):]
            if len(rem) >= 2 and rem.isalpha() and rem not in ("oo", "ee", "o", "e", "a", "i", "s", "t"):
                return fn.capitalize(), rem.capitalize()

    for sn in sorted(COMMON_SURNAMES, key=len, reverse=True):
        if clean_alpha.endswith(sn) and len(clean_alpha) > len(sn):
            prefix = clean_alpha[:-len(sn)]
            if len(prefix) >= 3 and prefix.isalpha():
                return prefix.capitalize(), sn.capitalize()

    # 4. Leetspeak substitution ONLY for internal digits (e.g. tauq33raslam -> Tauqeer Aslam, n0manghaffar -> Noman Ghaffar)
    if any(c.isdigit() for c in clean_stripped):
        curr = clean_stripped
        for num, char in LEET_REPLACEMENTS:
            if num in curr:
                curr = curr.replace(num, char)
        curr_clean = re.sub(r"[\d._+-]+", "", curr).strip()

        if curr_clean in COMMON_FIRST_NAMES:
            return curr_clean.capitalize(), ""

        for fn in sorted(COMMON_FIRST_NAMES, key=len, reverse=True):
            if curr_clean.startswith(fn) and len(curr_clean) > len(fn):
                rem = curr_clean[len(fn):]
                if len(rem) >= 2 and rem.isalpha() and rem not in ("oo", "ee", "o", "e", "a", "i", "s", "t"):
                    return fn.capitalize(), rem.capitalize()

        for sn in sorted(COMMON_SURNAMES, key=len, reverse=True):
            if curr_clean.endswith(sn) and len(curr_clean) > len(sn):
                prefix = curr_clean[:-len(sn)]
                if len(prefix) >= 3 and prefix.isalpha():
                    return prefix.capitalize(), sn.capitalize()

    return clean_alpha.capitalize() if clean_alpha else "", ""


def generate_handle_variations(
    email: str,
    name: Optional[str] = None,
    gh_username: Optional[str] = None,
) -> Tuple[List[str], List[str]]:
    """Generate prioritized handle variations from email local-part and name."""
    specific = []
    stems = []
    local = email.split("@")[0].lower().strip() if "@" in email else ""

    if local:
        specific.append(local)
        clean_no_sep = re.sub(r"[._+-]", "", local)
        if clean_no_sep != local:
            specific.append(clean_no_sep)
        clean_no_num = re.sub(r"\d+", "", clean_no_sep)
        if len(clean_no_num) >= 3:
            stems.append(clean_no_num)

        chunks = [re.sub(r"\d+", "", c).strip("._-") for c in re.split(r"[._+-]", local)]
        chunks = [c for c in chunks if len(c) >= 2]

        for c in chunks:
            if len(c) >= 3 and c not in stems:
                stems.append(c)

        if len(chunks) >= 2:
            stems.append("".join(chunks))
            stems.append(f"{chunks[1]}{chunks[0]}")
            stems.append(f"{chunks[0]}.{chunks[1]}")
            stems.append(f"{chunks[0]}_{chunks[1]}")

    if gh_username:
        gh_clean = gh_username.lower().strip()
        if gh_clean not in specific:
            specific.append(gh_clean)
        gh_no_sep = re.sub(r"[._+-]", "", gh_clean)
        if gh_no_sep != gh_clean and gh_no_sep not in specific:
            specific.append(gh_no_sep)

    if not name and local:
        fn, ln = split_compound_name(local)
        if fn and ln:
            name = f"{fn} {ln}"
        elif fn:
            name = fn

    if name:
        parts = [p.lower() for p in re.findall(r"[a-zA-Z]+", name)]
        title = ""
        core_parts = parts
        if parts and parts[0] in TITLE_PREFIXES and len(parts) > 1:
            title = parts[0]
            core_parts = parts[1:]

        if len(core_parts) >= 2:
            first, last = core_parts[0], core_parts[-1]
            concat = "".join(core_parts)
            rev_concat = f"{last}{first}"
            # Core name permutations
            for term in (
                f"{first}.{last}", f"{last}.{first}",
                f"{first}_{last}", f"{last}_{first}",
                f"{first}-{last}", f"{last}-{first}",
                concat, rev_concat,
                f"{first[0]}{last}", f"{last[0]}{first}"
            ):
                if term not in specific and term not in stems:
                    stems.append(term)

            # Permutations with Title prefix
            if title:
                for term in (
                    f"{title}{concat}", f"{title}.{first}.{last}",
                    f"{title}_{concat}", f"{title}.{concat}",
                    f"{title}_{first}_{last}", f"{title}{first}"
                ):
                    if term not in specific and term not in stems:
                        stems.append(term)

            if first in stems:
                stems.remove(first)
            stems.insert(0, first)
        elif len(core_parts) == 1:
            first = core_parts[0]
            if first in stems:
                stems.remove(first)
            stems.insert(0, first)

    generic = {
        "admin", "info", "support", "sales", "contact", "help",
        "billing", "team", "hello", "official", "mail", "user", "test",
        "gmail", "yahoo", "hotmail", "outlook", "profile", "account", "dev",
    }
    filtered_specific = [v for v in dict.fromkeys(specific) if len(v) >= 3 and v not in generic]
    filtered_stems = [v for v in dict.fromkeys(stems) if len(v) >= 3 and v not in generic]
    return filtered_specific, filtered_stems


def expand_social_probe_handles(
    specific_handles: List[str],
    stem_handles: List[str],
    name: Optional[str] = None,
) -> List[str]:
    """Generate targeted handle permutations for direct social probing across platforms."""
    probes = []
    
    # Identify bare surname to strictly prevent probing it alone (AGENTS.md Rule 3.3)
    bare_surname = ""
    if name and len(name.split()) >= 2:
        bare_surname = name.split()[-1].lower().strip()

    for h in (specific_handles + stem_handles):
        clean = h.strip().lower()
        if clean and clean not in probes and len(clean) >= 3 and clean != bare_surname:
            probes.append(clean)

    seeds = []
    if name:
        parts = [p.lower() for p in re.findall(r"[a-zA-Z]+", name)]
        if parts:
            first = parts[0]
            if len(first) >= 3 and first not in seeds and first != bare_surname:
                seeds.append(first)

    for h in stem_handles:
        clean = re.sub(r"\d+", "", h).strip("._-").lower()
        if clean and len(clean) >= 3 and clean not in seeds and len(clean) <= 12 and clean != bare_surname:
            seeds.append(clean)

    for h in specific_handles:
        clean = re.sub(r"\d+", "", h).strip("._-").lower()
        if clean and len(clean) >= 3 and clean not in seeds and clean != bare_surname:
            seeds.append(clean)

    # High-signal handle templates ({clean}_, _{clean}, momina0_, _momina0, ahtisham.v2, ahtisham_v2, dameesha_09)
    variation_templates = [
        "{clean}_",
        "_{clean}",
        "{clean}0_",
        "_{clean}0",
        "{clean}_0",
        "{clean}.v2",
        "{clean}_v2",
        "{clean}_09",
        "{clean}09",
        "{clean}_01",
    ]

    for s in seeds[:3]:
        for tmpl in variation_templates:
            v = tmpl.format(clean=s)
            if v not in probes:
                probes.append(v)

    return probes


# ==========================================
# 4. PARSER & TITLE / NAME CLEANERS
# ==========================================
RESERVED_SYSTEM_SLUGS = {
    "https", "http", "www", "com", "net", "org", "null", "undefined"
}

def parse_social_url(url: str) -> Optional[Dict[str, str]]:
    """Parse a social media URL into platform, canonical profile URL, and handle."""
    if not url:
        return None

    clean = url.split("?")[0].rstrip("/").strip(")>]\'\",.")
    m_nested = list(re.finditer(r"https?:/+", clean, re.IGNORECASE))
    if len(m_nested) > 1:
        clean = clean[m_nested[-1].start():]
    clean = re.sub(r"^(https?):/+([^\s/])", r"\1://\2", clean, flags=re.IGNORECASE)

    # Twitter / X (Profiles & Status/Post URLs)
    tw_match = re.search(r"https?://(?:[a-z0-9-]+\.)?(?:x\.com|twitter\.com)/([a-zA-Z0-9_]{1,25})(?:/status(?:es)?/\d+)?/?$", clean, re.IGNORECASE)
    if tw_match:
        handle = tw_match.group(1)
        if handle.lower() not in RESERVED_SYSTEM_SLUGS and handle.lower() not in ("home", "explore", "search", "notifications", "messages", "settings", "i", "privacy", "tos", "intent", "share", "status", "statuses"):
            return {
                "platform": "twitter",
                "platform_label": "X / Twitter",
                "handle": handle,
                "url": f"https://x.com/{handle}",
            }

    # Instagram
    ig_match = re.search(r"https?://(?:[a-z0-9-]+\.)?instagram\.com/([a-zA-Z0-9_.]{1,30})/?$", clean, re.IGNORECASE)
    if ig_match:
        handle = ig_match.group(1)
        if handle.lower() not in RESERVED_SYSTEM_SLUGS and handle.lower() not in ("p", "reel", "reels", "stories", "explore", "direct", "accounts", "about", "developer", "legal"):
            return {
                "platform": "instagram",
                "platform_label": "Instagram",
                "handle": handle,
                "url": f"https://www.instagram.com/{handle}",
            }

    # Facebook
    fb_people_match = re.search(r"https?://(?:[a-z0-9-]+\.)?facebook\.com/people/([^/?#]+)/(\d+)", clean, re.IGNORECASE)
    if fb_people_match:
        p_name = fb_people_match.group(1).replace("-", " ")
        p_id = fb_people_match.group(2)
        return {
            "platform": "facebook",
            "platform_label": "Facebook",
            "handle": p_name,
            "url": f"https://www.facebook.com/people/{fb_people_match.group(1)}/{p_id}/",
        }

    fb_match = re.search(r"https?://(?:[a-z0-9-]+\.)?facebook\.com/([a-zA-Z0-9_.]{3,50})/?$", clean, re.IGNORECASE)
    if fb_match:
        handle = fb_match.group(1)
        if handle.lower() not in RESERVED_SYSTEM_SLUGS and handle.lower() not in ("sharer", "share", "login", "recover", "help", "policies", "privacy", "pages", "groups", "events", "watch", "photo", "photos", "video", "videos", "reel", "reels", "posts"):
            return {
                "platform": "facebook",
                "platform_label": "Facebook",
                "handle": handle,
                "url": f"https://www.facebook.com/{handle}",
            }

    # LinkedIn
    if "linkedin.com/in/" in clean:
        li_match = re.search(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/([a-zA-Z0-9_/%-]+)", clean, re.IGNORECASE)
        if li_match:
            raw_slug = li_match.group(1).split("?")[0].split("#")[0].rstrip("/").strip()
            # Strip trailing localized language tags or subpaths (e.g. /pa, /ar, /es, /fr, /recent-activity)
            slug = raw_slug.split("/")[0].strip()
            if slug.lower() not in RESERVED_SYSTEM_SLUGS and slug.lower() not in ("dir", "pub", "feed", "jobs", "company", "school", "pulse", "posts", "learning") and len(slug) >= 3:
                return {
                    "platform": "linkedin",
                    "platform_label": "LinkedIn",
                    "handle": slug,
                    "url": f"https://www.linkedin.com/in/{slug}",
                }

    # TikTok
    tt_match = re.search(r"https?://(?:[a-z0-9-]+\.)?tiktok\.com/@([a-zA-Z0-9_.]{2,30})/?$", clean, re.IGNORECASE)
    if tt_match:
        handle = tt_match.group(1)
        if handle.lower() not in RESERVED_SYSTEM_SLUGS and handle.lower() not in ("explore", "direct", "trending", "about", "discover", "login", "live", "tag"):
            return {
                "platform": "tiktok",
                "platform_label": "TikTok",
                "handle": handle,
                "url": f"https://www.tiktok.com/@{handle}",
            }

    # Pinterest
    pin_match = re.search(r"https?://(?:[a-z0-9-]+\.)?pinterest\.com/([a-zA-Z0-9_.]{2,30})/?$", clean, re.IGNORECASE)
    if pin_match:
        handle = pin_match.group(1)
        if handle.lower() not in RESERVED_SYSTEM_SLUGS and handle.lower() not in ("explore", "pin", "ideas", "business", "help", "about", "login", "today", "shop", "news"):
            return {
                "platform": "pinterest",
                "platform_label": "Pinterest",
                "handle": handle,
                "url": f"https://www.pinterest.com/{handle}/",
            }

    # GitHub
    gh_match = re.search(r"https?://(?:[a-z0-9-]+\.)?github\.com/([a-zA-Z0-9_-]{1,39})/?$", clean, re.IGNORECASE)
    if gh_match:
        handle = gh_match.group(1)
        if handle.lower() not in ("features", "business", "explore", "marketplace", "pricing", "topics", "collections", "events"):
            return {
                "platform": "github",
                "platform_label": "GitHub",
                "handle": handle,
                "url": f"https://github.com/{handle}",
            }

    # Spotify (Strictly User Profiles)
    sp_match = re.search(r"https?://(?:open\.)?spotify\.com/(?:intl-[a-z]{2,5}/)?user/([a-zA-Z0-9_.-]{2,60})(?:/.*)?$", clean, re.IGNORECASE)
    if sp_match:
        handle = sp_match.group(1)
        if handle.lower() not in RESERVED_SYSTEM_SLUGS and handle.lower() not in ("download", "search", "genre", "playlist", "track", "album", "artist", "user", "explore", "collection"):
            return {
                "platform": "spotify",
                "platform_label": "Spotify",
                "handle": handle,
                "url": f"https://open.spotify.com/user/{handle}",
            }

    # Stack Overflow
    so_match = re.search(r"https?://(?:www\.)?stackoverflow\.com/users/(\d+)(?:/([a-zA-Z0-9_-]+))?", clean, re.IGNORECASE)
    if so_match:
        uid = so_match.group(1)
        slug = so_match.group(2) or uid
        return {
            "platform": "stackoverflow",
            "platform_label": "Stack Overflow",
            "handle": slug,
            "url": f"https://stackoverflow.com/users/{uid}/{slug}" if slug != uid else f"https://stackoverflow.com/users/{uid}",
        }

    # Medium
    med_match = re.search(r"https?://(?:[a-z0-9-]+\.)?medium\.com/@([a-zA-Z0-9._-]{2,50})/?", clean, re.IGNORECASE)
    if not med_match:
        # Match subdomain style: https://addyosmani.medium.com/...
        med_sub_match = re.search(r"https?://([a-zA-Z0-9._-]{2,50})\.medium\.com(?:/.*)?", clean, re.IGNORECASE)
        if med_sub_match and med_sub_match.group(1).lower() not in ("www", "api", "cdn-images-1", "blog", "status", "help", "policy"):
            med_match = med_sub_match

    if med_match:
        handle = med_match.group(1)
        if handle.lower() not in RESERVED_SYSTEM_SLUGS and handle.lower() not in ("about", "membership", "creators", "feed", "search", "topics", "tag", "explore", "me", "settings", "m", "policy", "www", "blog"):
            return {
                "platform": "medium",
                "platform_label": "Medium",
                "handle": handle,
                "url": f"https://medium.com/@{handle}",
            }

    return None


def format_handle_to_name(handle: str, resolved_name: Optional[str] = None) -> str:
    """Format a social handle into a clean human display name."""
    if not handle:
        return ""
    clean = handle.lstrip("@").strip()
    name_clean = re.sub(r"\d+$", "", clean).strip("._-")
    parts = [p.capitalize() for p in re.split(r"[._-]+", name_clean) if len(p) >= 2]
    if len(parts) >= 2:
        return " ".join(parts)
    elif len(parts) == 1:
        if resolved_name and parts[0].lower() in resolved_name.lower():
            return resolved_name
        return parts[0]
    return clean


def clean_display_name(raw_title: str, handle: str, platform: str, resolved_name: Optional[str] = None) -> str:
    """Extract and unescape authentic display name from title tag, stripping entity garbage and generic boilerplate."""
    if not raw_title:
        return format_handle_to_name(handle, resolved_name)

    t = unicodedata.normalize('NFKD', html.unescape(raw_title)).strip()

    if platform == "linkedin" or "linkedin" in t.lower():
        t = re.sub(r"\s*\|\s*LinkedIn.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*-\s*LinkedIn.*$", "", t, flags=re.IGNORECASE)
        segments = re.split(r"\s*[-–|•]\s*", t)
        if segments and len(segments[0].strip()) >= 2:
            name_part = segments[0].strip()
            name_part = re.sub(r",\s*(?:MBA|PHD|PMP|MD|CPA|ESQ|SHRM-[A-Z]+|BSc|MSc).*$", "", name_part, flags=re.IGNORECASE)
            return name_part.strip()

    # Spotify Profile Titles:
    # "Spotify – Mohid Faraz", "Spotify - ahtisham", "Mohid Faraz on Spotify", "Mohid Faraz | Spotify"
    if platform == "spotify" or "spotify" in t.lower():
        t = re.sub(r"^Spotify\s*[-–—:|•·]\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*[-–—:|•·]\s*Spotify.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+on\s+Spotify.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"^Listen\s+to\s+", "", t, flags=re.IGNORECASE)

    # Stack Overflow Profile Titles:
    # "User Guido van Rossum - Stack Overflow", "Guido van Rossum - Stack Overflow"
    if platform == "stackoverflow" or "stack overflow" in t.lower():
        t = re.sub(r"^User\s+", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*[-–—:|•·]\s*Stack\s*Overflow.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+on\s+Stack\s*Overflow.*$", "", t, flags=re.IGNORECASE)

    # Medium Profile Titles:
    # "Stories by Saad Asif on Medium", "Saad Asif – Medium", "Saad Asif on Medium"
    if platform == "medium" or "medium" in t.lower():
        t = re.sub(r"^Stories\s+by\s+", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*[-–—:|•·]\s*Medium.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+on\s+Medium.*$", "", t, flags=re.IGNORECASE)
        # Check if the title is an article / story title rather than author name
        words = t.split()
        article_indicators = {"why", "how", "what", "when", "guide", "tutorial", "top", "reasons", "best", "the", "an", "a", "into", "using", "with", "for", "vs", "versus"}
        if len(words) > 4 or any(w.lower() in article_indicators for w in words[:3]):
            if resolved_name and len(resolved_name.split()) <= 4:
                return resolved_name
            return format_handle_to_name(handle, resolved_name)

    # Extract playlist creator if present e.g. "backseat - playlist by Mohid Faraz | Spotify"
    if "playlist by" in t.lower():
        m_pl = re.search(r"playlist by\s+([^|•–-]+)", t, re.IGNORECASE)
        if m_pl and len(m_pl.group(1).strip()) >= 2:
            return m_pl.group(1).strip()

    # Strip platform trailers & generic TikTok/Instagram/Pinterest/X/Medium titles
    t = re.sub(r"\s*[-–—|•·]\s*(?:Instagram|X|Twitter|Facebook|TikTok|Pinterest|Spotify|Stack\s*Overflow|Medium|Photos and videos|Profile).*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+on\s+(?:Instagram|Twitter|X|Facebook|TikTok|Pinterest|Spotify|Stack\s*Overflow|Medium)\s*:?.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(?:Photos?|Reels?|Videos?|Posts?)\s+by\s+", "", t, flags=re.IGNORECASE)

    # Strip handle in parentheses e.g. "Babar Dilawar (@dilawar)" -> "Babar Dilawar"
    t = re.sub(r"\s*\(@?[a-zA-Z0-9._-]+\)", "", t)
    if t.startswith("@") or t.lower() == handle.lower() or t.lower() == f"@{handle.lower()}":
        t = ""

    if "|" in t:
        t = t.split("|")[0].strip()
    if " - " in t or " – " in t or " — " in t:
        t = re.split(r"\s*[-–—]\s*", t)[0].strip()

    t = re.sub(r'[\"\'“”#]', '', t).strip(' -–—|•·:/')
    if len(t) > 40:
        t = t[:40].strip()

    tl = t.lower()
    reject_patterns = (
        "link to", "page not found", "welcome back", "log in", "sign up",
        "visit tiktok to discover profiles", "discover profiles", "watch trending",
        "web player", "see what", "profile", "music for everyone", "unsupported browser", "stack overflow"
    )
    if not t or tl in ("spotify", "instagram", "facebook", "tiktok", "pinterest", "linkedin", "twitter", "x", "stackoverflow") or any(rej in tl for rej in reject_patterns) or len(t) < 2:
        return format_handle_to_name(handle, resolved_name)

    return t


def clean_bio_snippet(raw_snippet: str, platform: str, handle: str) -> str:
    """Clean and unescape bio snippets, preserving follower counts while removing boilerplate and directory spillovers."""
    if not raw_snippet:
        return f"{platform.title()} profile for @{handle.lstrip('@')}"
    s = unicodedata.normalize('NFKD', html.unescape(raw_snippet)).strip()
    s = re.sub(r"\s+", " ", s)
    # Only strip true list numbering like '1. ', '2) ', but preserve follower numbers like '12 Followers'
    s = re.sub(r"^\d+[\.\)\]]\s+", "", s).strip()

    if platform == "instagram":
        # Cut off bundled directory search spillover from other accounts
        for agg_marker in ["and discover other accounts you", "See photos and videos from friends on Instagram"]:
            idx = s.find(agg_marker)
            if idx != -1:
                s = s[:idx].strip()

        s = re.sub(r"\s*[-–—]?\s*See Instagram photos and videos from\s+[^@]+(?:\(@[a-zA-Z0-9._-]+\))?.*$", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"\s*[-–—]?\s*See photos and videos from friends on Instagram.*$", "", s, flags=re.IGNORECASE).strip()
        s = s.strip(" .,-–—|•·:/")

    elif platform in ("twitter", "x"):
        s = re.sub(r"\s*See the latest conversations with\s+@?[a-zA-Z0-9._-]+.*$", "", s, flags=re.IGNORECASE).strip()
        s = s.strip(" .,-–—|•·:/")

    elif platform == "facebook":
        # Strip date prefixes e.g. "Jul 20, 2026 ·", "Dec 24, 2023 ·"
        s = re.sub(r"^[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s*·\s*", "", s).strip()
        # Strip follower/like counts if followed by directory boilerplate
        s = re.sub(r"[\d,]+\s+likes\s*·\s*[\d,]+\s+talking\s+about\s+this\.?", "", s, flags=re.IGNORECASE).strip()
        # Strip directory boilerplate
        s = re.sub(r"View the profiles of people named\s+[^.]+\.", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"Join Facebook to connect with\s+[^.]+\.", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"Facebook gives people the power to\s*(?:share\s+and\s+makes?|share\s*\.\.\.|\.\.\.)?", "", s, flags=re.IGNORECASE).strip()
        # Strip internal tracking tokens e.g. tSeordsopn7ca0omgN8vhrhm...
        s = re.sub(r"\b[tT][A-Za-z0-9]{20,}\b.*$", "", s).strip()
        # Cut off secondary post spillovers
        s = re.sub(r"\s*·\s*Shared with Public.*$", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"\s*·\s*Excited to share.*$", "", s, flags=re.IGNORECASE).strip()
        s = s.strip(" .,-–—|•·:/")

    elif platform == "linkedin" or "linkedin" in s.lower():
        patterns = [
            r"^View\s+[^,]+(?:’s|'s)?\s*profile\s*on\s*LinkedIn[,\.\s]*(?:a\s+professional\s+community\s+of\s+[\d\w\s]+members\.?|the\s+world’s\s+largest\s+professional\s+community\.?|the\s+world's\s+largest\s+professional\s+community\.?)?\s*",
            r"a\s+professional\s+community\s+of\s+[\d\w\s]+members\.?",
            r"the\s+world(?:’|')s\s+largest\s+professional\s+community\.?",
            r"View\s+[^,\'’]+(?:’s|'s)?\s*profile\s*on\s*LinkedIn\.?",
            r"\b[A-Za-z0-9\s]+has\s+\d+\s+jobs?\s+listed\s+on\s+their\s+profile\.?",
            r"\bSee\s+the\s+complete\s+profile\s+on\s+LinkedIn\b\.?",
            r"\bJoin\s+LinkedIn\s+to\s+see\s+the\s+complete\s+profile\b\.?",
        ]
        for pat in patterns:
            s = re.sub(pat, "", s, flags=re.IGNORECASE).strip()
        s = s.strip(" .,-–|•·:/")

        # If LinkedIn bundled multiple directory profiles into one meta description, isolate the target person's block
        m_first_block = re.search(r"^(.*?connections\s+on\s+LinkedIn[\.,]*)", s, re.IGNORECASE)
        if m_first_block and len(m_first_block.group(1)) > 30:
            s = m_first_block.group(1).strip()
        elif len(s) > 260:
            s = s[:250].rsplit(" ", 1)[0] + "..."

    if any(bad in s.lower() for bad in ("the site owner hides", "link to facebook", "link to instagram", "welcome back", "log in", "unsupported browser", "join linkedin")):
        return f"{platform.title()} profile for @{handle.lstrip('@')}"

    if not s or len(s) < 3:
        return f"{platform.title()} profile for @{handle.lstrip('@')}"

    return s


# ==========================================
# 5. MULTI-ANCHOR SCORING & DISAMBIGUATION
# ==========================================
def score_candidate(
    platform_info: dict,
    title: str,
    snippet: str,
    all_variations: List[str],
    resolved_name: Optional[str],
    resolved_location: Optional[str],
    gh_username: Optional[str] = None,
    company_name: Optional[str] = None,
) -> Tuple[int, List[str], dict, List[dict]]:
    """Score a candidate from 0 to 95 with Jaro-Winkler string similarity, sub-scores, evidence provenance, and disambiguation rules."""
    handle_score = 0
    name_score = 0
    company_score = 0
    location_score = 0
    reasons = []
    evidence = []

    handle = platform_info["handle"].lower()
    title_l = html.unescape(title or "").lower()
    snippet_l = html.unescape(snippet or "").lower()
    combined_text = f"{title_l} {snippet_l}"
    handle_norm = re.sub(r"[._-]", "", handle)
    plat = platform_info.get("platform", "")

    # 1. Verified GitHub handle match
    if gh_username:
        gh_clean = gh_username.lower().strip()
        gh_norm = re.sub(r"[._-]", "", gh_clean)
        if handle == gh_clean or handle_norm == gh_norm:
            handle_score = max(handle_score, 85)
            reasons.append(f"Direct match with verified GitHub handle (@{gh_username})")
            evidence.append({"type": "handle_match", "source": "github_verified", "value": f"@{gh_username}", "signal_strength": "strong"})
        elif len(gh_norm) >= 4 and (gh_norm in handle_norm or handle_norm in gh_norm):
            handle_score = max(handle_score, 70)
            reasons.append(f"Stem match with verified GitHub handle (@{gh_username})")
            evidence.append({"type": "handle_match", "source": "github_stem", "value": f"@{gh_username}", "signal_strength": "medium"})

    # 2. Handle matching
    for v in all_variations:
        vl = v.lower()
        vl_norm = re.sub(r"[._-]", "", vl)
        if handle == vl or handle_norm == vl_norm:
            if any(c.isdigit() for c in vl) or len(vl) >= 7:
                handle_score = max(handle_score, 75)
                reasons.append(f"Distinctive exact handle match (@{handle})")
                evidence.append({"type": "handle_match", "source": "email_pattern", "value": f"@{handle}", "signal_strength": "strong"})
            else:
                handle_score = max(handle_score, 55)
                reasons.append(f"Exact handle match (@{handle})")
                evidence.append({"type": "handle_match", "source": "email_pattern", "value": f"@{handle}", "signal_strength": "medium"})
            break
        elif len(vl_norm) >= 4 and (vl_norm in handle_norm or handle_norm in vl_norm):
            handle_score = max(handle_score, 45)
            reasons.append(f"Root stem handle match (@{handle})")
            evidence.append({"type": "handle_match", "source": "stem_pattern", "value": f"@{handle}", "signal_strength": "weak"})
            break

    # 3. LinkedIn vanity URL match
    if plat == "linkedin":
        slug_norm = re.sub(r"[-_.]", "", handle)
        if resolved_name:
            name_parts = [p.lower() for p in resolved_name.split() if len(p) >= 2]
            if len(name_parts) >= 2:
                first, last = name_parts[0], name_parts[-1]
                if slug_norm.startswith(f"{first}{last}") or slug_norm.startswith(f"{last}{first}"):
                    handle_score = max(handle_score, 80)
                    reasons.append(f"Direct LinkedIn vanity URL match (in/{handle})")
                    evidence.append({"type": "handle_match", "source": "linkedin_vanity", "value": f"in/{handle}", "signal_strength": "strong"})

    # 4. Name Matching (Exact, Word-Boundary Title, Inverted, and Jaro-Winkler >= 88%)
    target_name = resolved_name
    cand_extracted_name = clean_display_name(title, handle, plat, resolved_name)
    
    if target_name:
        name_parts = [p.lower() for p in target_name.split() if len(p) >= 2]
        if len(name_parts) >= 2:
            first, last = name_parts[0], name_parts[-1]
            rev_name = f"{last} {first}".lower()

            # A. Exact extracted display name match (decisive primary match)
            if cand_extracted_name and (cand_extracted_name.lower() == target_name.lower() or cand_extracted_name.lower() == rev_name):
                name_score = max(name_score, 85)
                reasons.append(f"Exact full name match ({target_name})")
                evidence.append({"type": "name_match", "source": "exact_display_name", "value": target_name, "signal_strength": "strong"})
            elif bool(re.search(r'\b' + re.escape(target_name.lower()) + r'\b', title_l)) or bool(re.search(r'\b' + re.escape(rev_name) + r'\b', title_l)):
                name_score = max(name_score, 50)
                reasons.append(f"Full name match in title ({target_name})")
                evidence.append({"type": "name_match", "source": "profile_title", "value": target_name, "signal_strength": "strong"})
            elif bool(re.search(r'\b' + re.escape(first) + r'\b', title_l)) and bool(re.search(r'\b' + re.escape(last) + r'\b', title_l)):
                name_score = max(name_score, 35)
                reasons.append(f"First and last name in title ({first.title()} {last.title()})")
                evidence.append({"type": "name_match", "source": "profile_title", "value": f"{first.title()} {last.title()}", "signal_strength": "medium"})
            elif bool(re.search(r'\b' + re.escape(target_name.lower()) + r'\b', combined_text)) or bool(re.search(r'\b' + re.escape(rev_name) + r'\b', combined_text)):
                name_score = max(name_score, 30)
                reasons.append(f"Full name match in bio ({target_name})")
                evidence.append({"type": "name_match", "source": "profile_bio", "value": target_name, "signal_strength": "weak"})
            elif cand_extracted_name:
                cand_parts = [p.lower() for p in cand_extracted_name.split() if len(p) >= 2]
                if len(cand_parts) >= 2:
                    c_first, c_last = cand_parts[0], cand_parts[-1]
                    jw_f = jaro_winkler_similarity(c_first, first)
                    jw_l = jaro_winkler_similarity(c_last, last)
                    jw_f_inv = jaro_winkler_similarity(c_first, last)
                    jw_l_inv = jaro_winkler_similarity(c_last, first)

                    if (jw_f >= 0.88 and jw_l >= 0.88) or (jw_f_inv >= 0.88 and jw_l_inv >= 0.88):
                        name_score = max(name_score, 25)
                        best_sim = max((jw_f + jw_l) / 2.0, (jw_f_inv + jw_l_inv) / 2.0)
                        reasons.append(f"Fuzzy name match (Jaro-Winkler {best_sim:.0%}: '{cand_extracted_name}' ~ '{target_name}')")
                        evidence.append({"type": "name_match", "source": "fuzzy_title", "value": cand_extracted_name, "signal_strength": "weak"})
                elif len(cand_parts) == 1:
                    c_single = cand_parts[0]
                    if c_single == first or jaro_winkler_similarity(c_single, first) >= 0.90:
                        name_score = max(name_score, 35)
                        reasons.append(f"First name match in profile ('{c_single.title()}')")
                        evidence.append({"type": "name_match", "source": "profile_name", "value": c_single.title(), "signal_strength": "medium"})
                    elif c_single == last or jaro_winkler_similarity(c_single, last) >= 0.90:
                        name_score = max(name_score, 30)
                        reasons.append(f"Surname match in profile ('{c_single.title()}')")
                        evidence.append({"type": "name_match", "source": "profile_name", "value": c_single.title(), "signal_strength": "weak"})

    # 5. Workplace / Company Corroboration
    if company_name and company_name.lower() in combined_text:
        company_score = 25
        reasons.append(f"Company corroboration ({company_name})")
        evidence.append({"type": "company_match", "source": "corporate_record", "value": company_name, "signal_strength": "strong"})

    # 6. Location Corroboration
    if resolved_location:
        loc_tokens = [tok.strip().lower() for tok in re.split(r"[,/]", resolved_location) if len(tok.strip()) >= 3]
        matched_locs = [l for l in loc_tokens if l in combined_text]
        if matched_locs:
            location_score = 15
            reasons.append(f"Location match ({', '.join([l.title() for l in matched_locs])})")
            evidence.append({"type": "location_match", "source": "location_record", "value": ', '.join([l.title() for l in matched_locs]), "signal_strength": "medium"})

    raw_score = handle_score + name_score + company_score + location_score
    final_score = raw_score

    # 7. Disambiguation Rules: Conflicting Given Name, Contradictory Surname, & Complete Mismatch Penalties
    if target_name and cand_extracted_name:
        name_parts = [p.lower() for p in target_name.split() if len(p) >= 2]
        cand_parts = [p.lower() for p in cand_extracted_name.split() if len(p) >= 2]
        if len(name_parts) >= 2 and len(cand_parts) >= 2:
            first, last = name_parts[0], name_parts[-1]
            c_first, c_last = cand_parts[0], cand_parts[-1]

            exact_full = (cand_extracted_name.lower() == target_name.lower() or cand_extracted_name.lower() == f"{last} {first}")
            if not exact_full:
                surname_match = (c_last == last or (abs(len(c_last) - len(last)) <= 1 and jaro_winkler_similarity(c_last, last) >= 0.90))
                first_match = (c_first == first or (abs(len(c_first) - len(first)) <= 1 and jaro_winkler_similarity(c_first, first) >= 0.90))
                given_conflict = (not first_match and jaro_winkler_similarity(c_first, first) < 0.70 and len(c_first) >= 3 and len(first) >= 3)
                surname_conflict = (not surname_match and len(c_last) >= 3 and len(last) >= 3)

                # Rule A: Conflicting given name (Haseeb Hameed vs Atisam Hameed) -> cap at 15
                if surname_match and given_conflict:
                    final_score = min(final_score, 15)
                    reasons.append(f"Conflicting given name penalty ({c_first.title()} vs {first.title()})")

                # Rule B: Contradictory Surname penalty (Ahtisham Khan vs Ahtisham Dilawar / Shayan Aminmadani vs Shayan Amin) -> cap at 35
                elif first_match and surname_conflict:
                    final_score = min(final_score, 35)
                    reasons.append(f"Contradictory surname penalty ({c_last.title()} vs {last.title()})")

                # Rule C: Complete Name Mismatch (Veronica Torralba Lozano vs Danielle Monaghan)
                else:
                    is_handle_exact = (handle in [v.lower() for v in all_variations])
                    inv_first_match = (c_first == last or jaro_winkler_similarity(c_first, last) >= 0.90)
                    inv_last_match = (c_last == first or jaro_winkler_similarity(c_last, first) >= 0.90)
                    if not (surname_match or first_match or inv_first_match or inv_last_match) and not is_handle_exact:
                        return 0, [f"Unrelated profile: display name ('{cand_extracted_name}') does not match target name ('{target_name}')"], {}, []
        elif len(name_parts) >= 2 and len(cand_parts) == 1:
            first, last = name_parts[0], name_parts[-1]
            c_single = cand_parts[0]
            is_single_match = (c_single == first or c_single == last or jaro_winkler_similarity(c_single, first) >= 0.90 or jaro_winkler_similarity(c_single, last) >= 0.90)
            is_handle_exact = (handle in [v.lower() for v in all_variations])
            if not is_single_match and not is_handle_exact:
                return 0, [f"Unrelated profile: display name ('{cand_extracted_name}') does not match target name ('{target_name}')"], {}, []

    final_score = min(final_score, 95)
    sub_scores = {
        "handle_score": handle_score,
        "name_score": name_score,
        "company_score": company_score,
        "location_score": location_score,
        "final_score": max(0, final_score),
    }
    return max(0, final_score), reasons, sub_scores, evidence


# ==========================================
# 6. DIRECT 5-PLATFORM PROBERS
# ==========================================
CRAWLER_HEADERS = {
    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TWITTER_HEADERS = {
    "User-Agent": "Twitterbot/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def probe_instagram_profile(handle: str, client: Optional[httpx.AsyncClient] = None, proxy_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    clean = re.sub(r'[^a-zA-Z0-9._]', '', handle).lstrip("@").strip()
    if not clean or len(clean) < 3 or clean in ("p", "reel", "reels", "explore", "direct", "accounts", "about", "developer"):
        return None
    url = f"https://www.instagram.com/{clean}/"
    headers = CRAWLER_HEADERS
    
    resp = None
    # 1. Primary: Route through residential proxy (Instagram challenges direct data-center/local IPs)
    p_url = proxy_url or get_random_proxy_url()
    if p_url:
        try:
            async with httpx.AsyncClient(proxy=p_url, timeout=5.0, follow_redirects=True, verify=False) as px_client:
                resp = await px_client.get(url, headers=headers)
        except Exception:
            resp = None

    # 2. Fallback to direct client if proxy was unavailable or timed out
    if not resp or resp.status_code != 200:
        if client:
            try:
                resp = await client.get(url, headers=headers, timeout=3.5, follow_redirects=True)
            except Exception:
                resp = None

    try:
        if resp and resp.status_code == 200:
            text = resp.text
            if any(bad in text for bad in ("Sorry, this page isn't available", "The link you followed may be broken", "Page Not Found")):
                return None
            
            soup = BeautifulSoup(text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            raw_title = og_title.get("content").strip() if (og_title and og_title.get("content")) else (soup.title.string.strip() if soup.title and soup.title.string else "")
            
            # Reject non-existent Instagram profiles (generic "Instagram" title, missing og:title)
            if not raw_title or raw_title.lower() in ("instagram", "login • instagram", "sign up • instagram", "page not found"):
                return None
            
            og_img = soup.find("meta", property="og:image")
            raw_img = og_img.get("content") if og_img else None
            avatar_url = html.unescape(raw_img) if (raw_img and "static.xx.fbcdn" not in raw_img and "fb_icon" not in raw_img) else None

            og_desc = soup.find("meta", property="og:description")
            raw_desc = og_desc.get("content") if og_desc else ""
            
            # If no real description and no authentic avatar, account is not valid
            if not raw_desc and not avatar_url:
                return None

            bio = clean_bio_snippet(raw_desc, "instagram", clean)
            display_name = clean_display_name(raw_title, clean, "instagram")

            print(f"[Prober] [INSTAGRAM] @{clean} -> [OK] Confirmed (Name: '{display_name}', Avatar: {'YES' if avatar_url else 'NO'})", flush=True)
            return {
                "platform": "instagram",
                "platform_label": "Instagram",
                "handle": clean,
                "name": display_name,
                "url": url,
                "avatar_url": avatar_url,
                "snippet": bio,
                "title": raw_title,
                "discovery_method": "probing"
            }
    except Exception:
        pass
    return None


async def probe_tiktok_profile(handle: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    clean = re.sub(r'[^a-zA-Z0-9._]', '', handle).lstrip("@").strip()
    if not clean or len(clean) < 3 or clean in ("explore", "direct", "trending", "about", "discover", "login", "live"):
        return None
    url = f"https://www.tiktok.com/@{clean}"
    try:
        resp = await client.get(url, headers=CRAWLER_HEADERS, timeout=3.0, follow_redirects=True)
        if resp.status_code == 200:
            text = resp.text
            if any(bad in text for bad in ("Couldn't find this account", "UserNotExist", "page_not_found")):
                return None
            soup = BeautifulSoup(text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            raw_title = og_title.get("content").strip() if (og_title and og_title.get("content")) else (soup.title.string.strip() if soup.title and soup.title.string else "")
            
            # Reject generic placeholder pages for nonexistent accounts
            if not raw_title or raw_title.lower() in ("tiktok", "visit tiktok to discover profiles!", "discover profiles on tiktok"):
                return None

            og_img = soup.find("meta", property="og:image")
            raw_img = og_img.get("content") if og_img else None
            avatar_url = html.unescape(raw_img) if (raw_img and "static" not in raw_img) else None

            og_desc = soup.find("meta", property="og:description")
            raw_desc = og_desc.get("content") if og_desc else ""
            
            # Non-existent accounts have the generic slogan without an authentic avatar
            if not avatar_url and (not raw_desc or "Watch, follow, and discover more trending content." in raw_desc):
                return None

            bio = clean_bio_snippet(raw_desc, "tiktok", clean)
            display_name = clean_display_name(raw_title, clean, "tiktok")

            print(f"[Prober] [TIKTOK] @{clean} -> [OK] Confirmed (Name: '{display_name}', Avatar: {'YES' if avatar_url else 'NO'})", flush=True)
            return {
                "platform": "tiktok",
                "platform_label": "TikTok",
                "handle": clean,
                "name": display_name,
                "url": url,
                "avatar_url": avatar_url,
                "snippet": bio,
                "title": raw_title,
                "discovery_method": "probing"
            }
    except Exception:
        pass
    return None


async def probe_pinterest_profile(handle: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    clean = re.sub(r'[^a-zA-Z0-9._]', '', handle).lstrip("@").strip()
    if not clean or len(clean) < 3 or clean in ("explore", "pin", "ideas", "business", "help", "about", "login", "today"):
        return None
    url = f"https://www.pinterest.com/{clean}/"
    try:
        resp = await client.get(url, headers=CRAWLER_HEADERS, timeout=3.0, follow_redirects=True)
        if resp.status_code == 200:
            text = resp.text
            if "Profile not found" in text or "resource not found" in text.lower():
                return None
            soup = BeautifulSoup(text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            raw_title = og_title.get("content").strip() if (og_title and og_title.get("content")) else (soup.title.string.strip() if soup.title and soup.title.string else "")
            
            # Reject non-existent Pinterest placeholder profiles (empty title or generic "Pinterest")
            if not raw_title or raw_title.lower() in ("pinterest", "login • pinterest", "sign up • pinterest", "profile not found", "pinterest profile"):
                return None
            
            og_img = soup.find("meta", property="og:image")
            raw_img = og_img.get("content") if og_img else None
            avatar_url = html.unescape(raw_img) if (raw_img and "default_280" not in raw_img and "default_open_graph" not in raw_img) else None

            og_desc = soup.find("meta", property="og:description")
            raw_desc = og_desc.get("content") if og_desc else ""
            bio = clean_bio_snippet(raw_desc, "pinterest", clean)

            display_name = clean_display_name(raw_title, clean, "pinterest")

            print(f"[Prober] [PINTEREST] @{clean} -> [OK] Confirmed (Name: '{display_name}', Avatar: {'YES' if avatar_url else 'NO'})", flush=True)
            return {
                "platform": "pinterest",
                "platform_label": "Pinterest",
                "handle": clean,
                "name": display_name,
                "url": url,
                "avatar_url": avatar_url,
                "snippet": bio,
                "title": raw_title,
                "discovery_method": "probing"
            }
    except Exception:
        pass
    return None


async def probe_medium_profile(handle: str, client: Optional[httpx.AsyncClient] = None, proxy_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    clean = re.sub(r'[^a-zA-Z0-9._-]', '', handle).lstrip("@").strip()
    if not clean or len(clean) < 2 or clean.lower() in RESERVED_SYSTEM_SLUGS or clean.lower() in ("about", "membership", "creators", "feed", "search", "topics", "tag", "explore", "me", "settings", "policy", "plans"):
        return None
    url = f"https://medium.com/feed/@{clean}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
    }
    resp = None
    p_url = proxy_url or get_random_proxy_url()
    if p_url:
        try:
            async with httpx.AsyncClient(proxy=p_url, timeout=5.0, follow_redirects=True, verify=False) as px_client:
                resp = await px_client.get(url, headers=headers)
        except Exception:
            resp = None

    if not resp or resp.status_code != 200:
        if client:
            try:
                resp = await client.get(url, headers=headers, timeout=3.5, follow_redirects=True)
            except Exception:
                resp = None

    if resp and resp.status_code == 200:
        try:
            root = ET.fromstring(resp.text)
            channel = root.find("channel")
            if channel is None:
                return None
            raw_title = channel.find("title").text if channel.find("title") is not None else ""
            raw_image = channel.find("image/url").text if channel.find("image/url") is not None else None
            
            clean_name = raw_title.replace("Stories by ", "").replace(" on Medium", "").strip() if raw_title else clean
            display_name = clean_display_name(clean_name, clean, "medium")
            
            snippet = f"Medium profile for {display_name}"
            items = channel.findall("item")
            if items:
                first_item = items[0]
                post_title = first_item.find("title").text if first_item.find("title") is not None else ""
                content_encoded = first_item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
                if content_encoded is not None and content_encoded.text:
                    p_soup = BeautifulSoup(content_encoded.text, "html.parser")
                    p_text = p_soup.get_text().strip()
                    snippet = f"Latest story: '{post_title}' — {p_text[:120]}..." if post_title else p_text[:140]
            
            # Only keep avatar if URL looks like a real user photo (Medium CDN user-avatar paths).
            # RSS <image> can also return publication logos — those have no '/fit/c/' or 'resize' pattern.
            raw_avatar = html.unescape(raw_image) if raw_image else None
            avatar_url = None
            if raw_avatar:
                is_user_avatar = (
                    "/fit/c/" in raw_avatar
                    or "resize:fill:" in raw_avatar
                    or "resize%3Afill" in raw_avatar
                    or "/cdn-cgi/image/" in raw_avatar
                )
                if is_user_avatar:
                    avatar_url = re.sub(r'/fit/c/\d+/\d+/', '/v2/resize:fill:200:200/', raw_avatar)
            profile_url = f"https://medium.com/@{clean}"
            
            print(f"[Prober] [MEDIUM] @{clean} -> [OK] Confirmed (Name: '{display_name}', Avatar: {'YES' if avatar_url else 'NO'}, Posts: {len(items)})", flush=True)
            return {
                "platform": "medium",
                "platform_label": "Medium",
                "handle": clean,
                "name": display_name,
                "url": profile_url,
                "avatar_url": avatar_url,
                "snippet": snippet,
                "title": raw_title,
                "discovery_method": "probing"
            }
        except Exception:
            pass
    return None


async def probe_spotify_profile(handle: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    clean = re.sub(r'[^a-zA-Z0-9._-]', '', handle).lstrip("@").strip()
    if not clean or len(clean) < 2 or clean.lower() in RESERVED_SYSTEM_SLUGS or clean.lower() in ("download", "search", "genre", "playlist", "track", "album", "artist", "user", "explore", "collection"):
        return None
    url = f"https://open.spotify.com/user/{clean}"
    
    avatar_url = None
    display_name = None
    bio = f"Spotify profile for @{clean}"
    raw_title = ""
    confirmed = False

    try:
        resp = await client.get(url, headers=LI_CRAWLER_HEADERS, timeout=5.0, follow_redirects=True)
        if resp.status_code == 200:
            text = resp.text
            if "Page not found" in text or "Something went wrong" in text:
                return None
            soup = BeautifulSoup(text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            raw_title = og_title.get("content").strip() if (og_title and og_title.get("content")) else (soup.title.string.strip() if soup.title and soup.title.string else "")
            
            if raw_title and raw_title.lower() not in ("spotify", "spotify - web player", "spotify – web player", "page not found", "sign up", "log in"):
                confirmed = True
                og_img = soup.find("meta", property="og:image")
                raw_img = og_img.get("content") if og_img else None
                if raw_img and raw_img.startswith("http") and not any(x in raw_img.lower() for x in ("default", "icon", "placeholder", "spotify-logo", "logo.png", "generic")):
                    avatar_url = html.unescape(raw_img)
                
                og_desc = soup.find("meta", property="og:description")
                raw_desc = og_desc.get("content") if og_desc else ""
                bio = clean_bio_snippet(raw_desc, "spotify", clean)
                display_name = clean_display_name(raw_title, clean, "spotify")
    except Exception:
        pass

    if not confirmed:
        return None

    if not display_name or display_name.lower() in ("spotify", "web player"):
        display_name = format_handle_to_name(clean)

    print(f"[Prober] [SPOTIFY] @{clean} -> [OK] Confirmed (Name: '{display_name}', Avatar: {'YES' if avatar_url else 'NO'})", flush=True)
    return {
        "platform": "spotify",
        "platform_label": "Spotify",
        "handle": clean,
        "name": display_name,
        "url": url,
        "avatar_url": avatar_url,
        "snippet": bio,
        "title": raw_title,
        "discovery_method": "probing"
    }


async def _fetch_spotify_token_via_sp_dc(sp_dc: str) -> Optional[Dict[str, Any]]:
    """
    Exchanges a long-lived sp_dc session cookie for a short-lived Bearer access token
    by launching a lightweight headless browser with Playwright.
    Uses sync_playwright via asyncio.to_thread with WindowsProactorEventLoopPolicy.
    """
    sp_key = os.getenv("SPOTIFY_SP_KEY", "").strip()

    async with _spotify_refresh_lock:
        # Double check cache inside lock
        now = time.time()
        if _spotify_token_cache["access_token"] and now < _spotify_token_cache["expires_at"] - 300:
            return {
                "access_token": _spotify_token_cache["access_token"],
                "client_token": _spotify_token_cache["client_token"],
                "expires_in": int(_spotify_token_cache["expires_at"] - now),
            }

        def _sync_worker() -> Optional[Dict[str, Any]]:
            if sys.platform == "win32":
                try:
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                except Exception:
                    pass

            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                print("[Spotify Auto-Refresher] Playwright not installed. Run: pip install playwright && playwright install chromium", flush=True)
                return None

            tokens: Dict[str, Any] = {"access_token": "", "client_token": "", "expires_in": 3600}
            try:
                print("[Spotify Auto-Refresher] 🔄 Auto-refreshing Bearer token via headless browser...", flush=True)
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 800},
                    )
                    cookies = [
                        {"name": "sp_dc", "value": sp_dc, "domain": ".spotify.com", "path": "/"},
                    ]
                    if sp_key:
                        cookies.append({"name": "sp_key", "value": sp_key, "domain": ".spotify.com", "path": "/"})

                    context.add_cookies(cookies)
                    page = context.new_page()

                    def on_response(response):
                        try:
                            url = response.url
                            if "token" in url.lower() or "clienttoken" in url.lower():
                                content_type = response.headers.get("content-type", "")
                                if "json" in content_type:
                                    data = response.json()
                                    if "accessToken" in data and not tokens["access_token"]:
                                        tokens["access_token"] = data["accessToken"]
                                        exp_ms = data.get("accessTokenExpirationTimestampMs", 0)
                                        if exp_ms:
                                            tokens["expires_in"] = max(300, int((exp_ms / 1000) - time.time()))
                                    if "client_token" in data or "granted_token" in data:
                                        ct = (data.get("granted_token", {}) or {}).get("token") or data.get("client_token")
                                        if ct and not tokens["client_token"]:
                                            tokens["client_token"] = ct
                        except Exception:
                            pass

                    page.on("response", on_response)

                    try:
                        page.goto("https://open.spotify.com/", wait_until="domcontentloaded", timeout=15000)
                        for _ in range(12):
                            if tokens["access_token"]:
                                break
                            time.sleep(0.3)

                        # In-page fetch fallback if not intercepted
                        if not tokens["access_token"]:
                            res = page.evaluate('''async () => {
                                try {
                                    const r = await fetch('https://open.spotify.com/get_access_token?reason=transport&productType=web_player');
                                    return await r.json();
                                } catch(e) {
                                    return null;
                                }
                            }''')
                            if isinstance(res, dict) and "accessToken" in res:
                                tokens["access_token"] = res["accessToken"]
                                exp_ms = res.get("accessTokenExpirationTimestampMs", 0)
                                if exp_ms:
                                    tokens["expires_in"] = max(300, int((exp_ms / 1000) - time.time()))
                    finally:
                        browser.close()

                if tokens["access_token"]:
                    remaining_mins = tokens["expires_in"] // 60
                    print(f"[Spotify Auto-Refresher] ✅ Bearer token auto-refreshed successfully (~{remaining_mins}m valid)", flush=True)
                    return tokens
                else:
                    print("[Spotify Auto-Refresher] ⚠️ Could not capture accessToken from session", flush=True)
                    return None
            except Exception as e:
                print(f"[Spotify Auto-Refresher] ⚠️ Error during token refresh: {e}", flush=True)
                return None

        return await asyncio.to_thread(_sync_worker)


async def _get_spotify_tokens() -> Tuple[str, str]:
    """
    Returns (access_token, client_token), refreshing from sp_dc if the cached token
    is missing or within 5 minutes of expiry. Falls back to env-hardcoded tokens if
    SPOTIFY_SP_DC is not set.
    """
    global _spotify_token_cache
    now = time.time()
    # Return cached tokens if still valid (with 5-minute buffer)
    if _spotify_token_cache["access_token"] and now < _spotify_token_cache["expires_at"] - 300:
        return _spotify_token_cache["access_token"], _spotify_token_cache["client_token"]

    load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"), override=True)
    sp_dc = os.getenv("SPOTIFY_SP_DC", "").strip()

    if sp_dc:
        # Auto-refresh via sp_dc cookie
        result = await _fetch_spotify_token_via_sp_dc(sp_dc)
        if result:
            _spotify_token_cache["access_token"] = result["access_token"]
            _spotify_token_cache["client_token"] = result.get("client_token", "")
            _spotify_token_cache["expires_at"] = now + result["expires_in"]
            return _spotify_token_cache["access_token"], _spotify_token_cache["client_token"]

    # Fallback: use manually-set env tokens
    auth_token = os.getenv("SPOTIFY_AUTH_TOKEN", "").strip()
    client_token = os.getenv("SPOTIFY_CLIENT_TOKEN", "").strip()
    return auth_token, client_token


async def start_spotify_auto_refresher_daemon():
    """
    Background daemon task launched on FastAPI startup:
    1. Warms up the Bearer access token upon server launch (if SPOTIFY_SP_DC is set).
    2. Proactively refreshes the token 5 minutes before its 1-hour expiration.
    """
    load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"), override=True)
    sp_dc = os.getenv("SPOTIFY_SP_DC", "").strip()
    if not sp_dc:
        return

    print("[Spotify Auto-Refresher] 🚀 Background refresher daemon initialized.", flush=True)
    while True:
        try:
            now = time.time()
            # If missing or within 5 minutes of expiration, refresh
            if not _spotify_token_cache["access_token"] or now >= _spotify_token_cache["expires_at"] - 300:
                await _get_spotify_tokens()

            # Sleep until 5 minutes before expiration (at least 30s)
            remaining_to_refresh = max(30, int((_spotify_token_cache["expires_at"] - 300) - time.time()))
            await asyncio.sleep(remaining_to_refresh)
        except asyncio.CancelledError:
            print("[Spotify Auto-Refresher] 🛑 Daemon stopped cleanly.", flush=True)
            break
        except Exception as e:
            print(f"[Spotify Auto-Refresher] ⚠️ Background daemon error: {e}", flush=True)
            await asyncio.sleep(60)


async def search_spotify_users_pathfinder(
    query: str,
    client: httpx.AsyncClient,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """
    Search Spotify for user profiles by display name using Spotify's internal Pathfinder GraphQL API.
    Automatically refreshes the Bearer token via SPOTIFY_SP_DC (if set) or falls back to
    SPOTIFY_AUTH_TOKEN / SPOTIFY_CLIENT_TOKEN from environment.
    """
    clean_query = query.strip()
    if not clean_query:
        return []

    auth_token, client_token = await _get_spotify_tokens()
    if not auth_token:
        return []

    async def _do_search(at: str, ct: str) -> Optional[httpx.Response]:
        url = "https://api-partner.spotify.com/pathfinder/v2/query"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en",
            "Referer": "https://open.spotify.com/",
            "Origin": "https://open.spotify.com",
            "Authorization": f"Bearer {at}" if not at.startswith("Bearer ") else at,
            "app-platform": "WebPlayer",
            "spotify-app-version": "1.3.4.71.gc1b8a0bfbc9b",
            "Content-Type": "application/json;charset=UTF-8",
        }
        if ct:
            headers["client-token"] = ct
        payload = {
            "operationName": "searchUsers",
            "variables": {
                "searchTerm": clean_query,
                "offset": 0,
                "limit": limit,
                "numberOfTopResults": 20,
                "includeAudiobooks": True,
                "includeAuthors": False,
                "includeEpisodeContentRatingsV2": True,
                "includePreReleases": False,
                "includeAlbumPreReleases": False,
            },
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "8f358dd82e62f61dd4ceaa9f8cd0889e644c9b707f1b724fbfb356a757cb7e5a",
                }
            },
        }
        return await client.post(url, json=payload, headers=headers, timeout=6.0)

    def _parse_results(r: httpx.Response) -> List[Dict[str, Any]]:
        data = r.json()
        users_block = (data.get("data", {}) or {}).get("searchV2", {}).get("users", {}) or {}
        items = users_block.get("items", []) or []
        results = []
        for it in items:
            u_data = it.get("data", {}) or {}
            uri = u_data.get("uri", "")
            uid = uri.replace("spotify:user:", "").strip()
            if not uid:
                continue
            display_name = u_data.get("displayName", "").strip() or uid
            avatar_list = (u_data.get("avatar", {}) or {}).get("sources", [])
            avatar_url = avatar_list[0].get("url") if avatar_list else None
            results.append({
                "platform": "spotify",
                "platform_label": "Spotify",
                "handle": uid,
                "name": display_name,
                "url": f"https://open.spotify.com/user/{uid}",
                "avatar_url": avatar_url,
                "snippet": f"Spotify profile for {display_name}",
                "title": f"{display_name} on Spotify",
                "discovery_method": "spotify_api",
            })
        return results

    try:
        r = await _do_search(auth_token, client_token)
        if r.status_code == 200:
            results = _parse_results(r)
            print(f"[Spotify Pathfinder] Query '{clean_query}' → Found {len(results)} user profiles", flush=True)
            return results
        elif r.status_code == 401:
            # Token expired mid-session — force a refresh and retry once
            print(f"[Spotify Pathfinder] ⚠️ HTTP 401 for '{clean_query}' — forcing token refresh and retrying...", flush=True)
            _spotify_token_cache["expires_at"] = 0.0  # invalidate cache
            new_at, new_ct = await _get_spotify_tokens()
            if new_at and new_at != auth_token:
                r2 = await _do_search(new_at, new_ct)
                if r2.status_code == 200:
                    results = _parse_results(r2)
                    print(f"[Spotify Pathfinder] Retry OK — '{clean_query}' → {len(results)} profiles", flush=True)
                    return results
            print(f"[Spotify Pathfinder] ⚠️ Token refresh failed or SPOTIFY_SP_DC not set. Add SPOTIFY_SP_DC to .env for auto-refresh.", flush=True)
        else:
            print(f"[Spotify Pathfinder] HTTP {r.status_code} for '{clean_query}': {r.text[:200]}", flush=True)
    except Exception as e:
        print(f"[Spotify Pathfinder] Error for '{clean_query}': {e}", flush=True)
    return []


async def search_stackoverflow_users(
    query: str,
    client: httpx.AsyncClient,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Searches Stack Overflow for user profiles using the official Stack Exchange API v2.3.
    Retrieves real developer display names, profile avatars, reputation, location, and website URLs.
    No API key required (300 requests/day per IP; supports optional STACKEXCHANGE_API_KEY for 10,000/day).
    """
    clean_query = query.strip()
    if not clean_query or len(clean_query) < 2:
        return []

    api_key = os.getenv("STACKEXCHANGE_API_KEY", "").strip()
    url = "https://api.stackexchange.com/2.3/users"
    params = {
        "site": "stackoverflow",
        "inname": clean_query,
        "pagesize": min(limit, 20),
        "order": "desc",
        "sort": "reputation",
        "filter": "default",
    }
    if api_key:
        params["key"] = api_key

    headers = {
        "User-Agent": "EmailLookup/1.0 (contact: admin@emaillookup.internal)",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }

    try:
        r = await client.get(url, params=params, headers=headers, timeout=6.0)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", []) or []
            print(f"[Stack Overflow API] Query '{clean_query}' → Found {len(items)} user profiles", flush=True)
            results = []
            for it in items:
                uid = it.get("user_id")
                if not uid:
                    continue
                raw_name = it.get("display_name", "").strip()
                display_name = html.unescape(raw_name) if raw_name else f"user{uid}"
                link = it.get("link", f"https://stackoverflow.com/users/{uid}")
                avatar_url = it.get("profile_image")
                location = it.get("location") or ""
                website_url = it.get("website_url") or ""
                reputation = it.get("reputation", 0)

                slug = link.rstrip("/").split("/")[-1] if "/" in link else str(uid)
                handle_str = slug if (slug and not slug.isdigit() and slug != "users") else str(uid)

                snippet_parts = []
                if reputation:
                    snippet_parts.append(f"Reputation: {reputation:,}")
                if location:
                    snippet_parts.append(f"Location: {location}")
                if website_url:
                    snippet_parts.append(f"Website: {website_url}")
                snippet = " | ".join(snippet_parts) if snippet_parts else f"Stack Overflow profile for {display_name}"

                results.append({
                    "platform": "stackoverflow",
                    "platform_label": "Stack Overflow",
                    "handle": handle_str,
                    "name": display_name,
                    "url": link,
                    "avatar_url": avatar_url,
                    "snippet": snippet,
                    "title": f"{display_name} on Stack Overflow",
                    "location": location,
                    "website_url": website_url,
                    "reputation": reputation,
                    "discovery_method": "stackoverflow_api",
                })
            return results
        else:
            print(f"[Stack Overflow API] HTTP {r.status_code} for query '{clean_query}'", flush=True)
            return []
    except Exception as e:
        print(f"[Stack Overflow API] Query error for '{clean_query}': {e}", flush=True)
        return []


async def probe_twitter_profile(handle: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    clean = re.sub(r'[^a-zA-Z0-9_]', '', handle).lstrip("@").strip()
    if not clean or len(clean) < 3 or clean in ("home", "explore", "search", "notifications", "settings", "i", "tos"):
        return None
    url = f"https://x.com/{clean}"
    
    avatar_url = None
    display_name = None
    bio = f"X / Twitter profile for @{clean}"
    raw_title = ""
    confirmed = False

    try:
        resp = await client.get(url, headers=TWITTER_HEADERS, timeout=6.0, follow_redirects=True)
        if resp.status_code == 200:
            text = resp.text
            if "This account doesn’t exist" in text or "account has been suspended" in text or "page doesn’t exist" in text or "This account doesn't exist" in text:
                return None
            soup = BeautifulSoup(text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            raw_title = og_title.get("content").strip() if (og_title and og_title.get("content")) else (soup.title.string.strip() if soup.title and soup.title.string else "")
            
            if raw_title and not any(bad in raw_title.lower() for bad in ("page not found", "doesn't exist", "doesn’t exist", "suspended", "something went wrong")):
                confirmed = True
                og_img = soup.find("meta", property="og:image")
                raw_img = og_img.get("content") if og_img else None
                if raw_img and "pbs.twimg.com" in raw_img:
                    avatar_url = html.unescape(raw_img)

                og_desc = soup.find("meta", property="og:description")
                raw_desc = og_desc.get("content") if og_desc else ""
                bio = clean_bio_snippet(raw_desc, "twitter", clean)
                display_name = clean_display_name(raw_title, clean, "twitter")
    except Exception:
        pass

    if not confirmed:
        try:
            m_resp = await client.get(f"https://api.microlink.io/?url=https://x.com/{clean}", timeout=4.0)
            if m_resp.status_code == 200:
                m_data = m_resp.json()
                if m_data.get("status") == "success":
                    d_title = m_data.get("data", {}).get("title", "")
                    if d_title and not any(bad in d_title.lower() for bad in ("page not found", "doesn't exist", "doesn’t exist", "suspended")):
                        img_data = m_data.get("data", {}).get("image", {})
                        img_u = img_data.get("url") if isinstance(img_data, dict) else img_data
                        if img_u and "pbs.twimg.com" in str(img_u):
                            avatar_url = str(img_u)
                            confirmed = True
                            display_name = clean_display_name(d_title, clean, "twitter")
        except Exception:
            pass

    if not confirmed:
        return None

    if not display_name or display_name.lower() in ("x", "twitter", "x / twitter"):
        display_name = format_handle_to_name(clean)

    print(f"[Prober] [TWITTER] @{clean} -> [OK] Confirmed (Name: '{display_name}', Avatar: {'YES' if avatar_url else 'NO'})", flush=True)
    return {
        "platform": "twitter",
        "platform_label": "X / Twitter",
        "handle": clean,
        "name": display_name,
        "url": url,
        "avatar_url": avatar_url,
        "snippet": bio,
        "title": raw_title,
        "discovery_method": "probing"
    }


async def probe_facebook_profile(handle: str, client: httpx.AsyncClient, proxy_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    clean = re.sub(r'[^a-zA-Z0-9._]', '', handle).lstrip("@").strip()
    if not clean or len(clean) < 3 or clean in ("sharer", "share", "login", "recover", "help", "policies", "privacy"):
        return None
    url = f"https://www.facebook.com/{clean}"
    
    resp = None
    p_url = proxy_url or get_random_proxy_url()
    if p_url:
        try:
            async with httpx.AsyncClient(proxy=p_url, timeout=5.0, follow_redirects=True, verify=False) as px_client:
                resp = await px_client.get(url, headers=TWITTER_HEADERS)
        except Exception:
            resp = None

    if not resp or resp.status_code != 200:
        try:
            resp = await client.get(url, headers=TWITTER_HEADERS, timeout=3.5, follow_redirects=True)
        except Exception:
            return None

    try:
        if resp and resp.status_code == 200:
            text = resp.text
            if any(bad in text for bad in ("This content isn't available right now", "Page Not Found", "You must log in")):
                return None
            soup = BeautifulSoup(text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            raw_title = og_title.get("content").strip() if (og_title and og_title.get("content")) else ""
            
            # If no og:title or generic "Facebook" title, account is not publicly confirmed
            if not raw_title or raw_title.lower() in ("facebook", "log in to facebook", "log into facebook", "welcome to facebook", "error"):
                return None

            # Extract authentic canonical URL & handle from og:url or final redirected resp.url
            og_url = soup.find("meta", property="og:url")
            canonical_url = og_url.get("content").strip() if (og_url and og_url.get("content")) else str(resp.url)
            m_handle = re.search(r"facebook\.com/([a-zA-Z0-9._-]+)/?$", canonical_url, re.IGNORECASE)
            if m_handle:
                c_cand = m_handle.group(1).rstrip("/")
                if c_cand.lower() not in ("profile.php", "pages", "people", "sharer", "share", "login"):
                    clean = c_cand
                    url = f"https://www.facebook.com/{clean}"
            
            og_img = soup.find("meta", property="og:image")
            raw_img = og_img.get("content") if og_img else None
            avatar_url = html.unescape(raw_img) if (raw_img and "fb_icon" not in raw_img and "static.xx" not in raw_img) else None

            og_desc = soup.find("meta", property="og:description")
            raw_desc = og_desc.get("content") if og_desc else ""
            bio = clean_bio_snippet(raw_desc, "facebook", clean)
            display_name = clean_display_name(raw_title, clean, "facebook")

            print(f"[Prober] [FACEBOOK] @{clean} -> [OK] Confirmed (Name: '{display_name}', Avatar: {'YES' if avatar_url else 'NO'})", flush=True)
            return {
                "platform": "facebook",
                "platform_label": "Facebook",
                "handle": clean,
                "name": display_name,
                "url": url,
                "avatar_url": avatar_url,
                "snippet": bio,
                "title": raw_title,
                "discovery_method": "probing"
            }
    except Exception:
        pass
    return None


async def probe_github_profile(handle: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    clean = re.sub(r'[^a-zA-Z0-9_-]', '', handle).lstrip("@").strip("_-")
    if not clean or len(clean) < 1 or clean.lower() in ("features", "business", "explore", "marketplace", "pricing", "topics", "collections", "events"):
        return None
    url = f"https://github.com/{clean}"
    try:
        resp = await client.get(url, headers=CRAWLER_HEADERS, timeout=3.0, follow_redirects=True)
        if resp.status_code == 200:
            text = resp.text
            if "Page not found" in text or "404 Not Found" in text:
                return None
            soup = BeautifulSoup(text, "html.parser")
            og_title = soup.find("meta", property="og:title")
            raw_title = og_title.get("content").strip() if (og_title and og_title.get("content")) else (soup.title.string.strip() if soup.title and soup.title.string else "")
            
            if not raw_title or raw_title.lower() in ("github", "page not found", "built for developers"):
                return None

            og_img = soup.find("meta", property="og:image")
            raw_img = og_img.get("content") if og_img else None
            avatar_url = html.unescape(raw_img) if (raw_img and "avatars.githubusercontent.com" in raw_img) else None

            og_desc = soup.find("meta", property="og:description")
            raw_desc = og_desc.get("content") if og_desc else ""
            bio = clean_bio_snippet(raw_desc, "github", clean)
            display_name = clean_display_name(raw_title, clean, "github")

            print(f"[Prober] [GITHUB] @{clean} -> [OK] Confirmed (Name: '{display_name}', Avatar: {'YES' if avatar_url else 'NO'})", flush=True)
            return {
                "platform": "github",
                "platform_label": "GitHub",
                "handle": clean,
                "name": display_name,
                "url": url,
                "avatar_url": avatar_url,
                "snippet": bio,
                "title": raw_title,
                "discovery_method": "probing"
            }
    except Exception:
        pass
    return None


LI_CRAWLER_HEADERS = {
    "User-Agent": "Twitterbot/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

async def fetch_linkedin_candidate_avatar(url: str, client: httpx.AsyncClient) -> Tuple[Optional[str], Optional[str]]:
    """Extract authentic LinkedIn profile photo and canonical URL from public OpenGraph tags and HTML via Twitterbot crawler headers."""
    if not url or "linkedin.com/in/" not in url:
        return None, None
    try:
        resp = await client.get(url, headers=LI_CRAWLER_HEADERS, timeout=5.0, follow_redirects=True)
        canonical_url = str(resp.url) if resp else None
        avatar_url = None

        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            og_url = soup.find("meta", property="og:url")
            if og_url and og_url.get("content"):
                canonical_url = og_url.get("content").strip()

            og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
            if og_img and og_img.get("content"):
                img_src = og_img.get("content").strip()
                if "licdn.com" in img_src and "ghost" not in img_src and "default_guest_profile" not in img_src:
                    avatar_url = img_src

            if not avatar_url:
                m = re.search(r'<meta\s+(?:property|name)=["\'](?:og:image|twitter:image)["\']\s+content=["\']([^"\']+)["\']', resp.text)
                if not m:
                    m = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\'](?:og:image|twitter:image)["\']', resp.text)
                if m:
                    img_src = html.unescape(m.group(1)).strip()
                    if "licdn.com" in img_src and "ghost" not in img_src and "default_guest_profile" not in img_src:
                        avatar_url = img_src

        if not avatar_url:
            try:
                p_url = get_random_proxy_url()
                if p_url:
                    async with httpx.AsyncClient(proxy=p_url, timeout=5.0, verify=False) as p_client:
                        p_resp = await p_client.get(url, headers=LI_CRAWLER_HEADERS, follow_redirects=True)
                        if p_resp.status_code == 200:
                            p_soup = BeautifulSoup(p_resp.text, "html.parser")
                            p_img = p_soup.find("meta", property="og:image") or p_soup.find("meta", attrs={"name": "twitter:image"})
                            if p_img and p_img.get("content"):
                                img_src = p_img.get("content").strip()
                                if "licdn.com" in img_src and "ghost" not in img_src and "default_guest_profile" not in img_src:
                                    avatar_url = img_src
            except Exception:
                pass

        return avatar_url, canonical_url
    except Exception:
        pass
    return None, None


async def fetch_facebook_candidate_avatar(url: str, client: httpx.AsyncClient) -> Optional[str]:
    """Extract authentic Facebook profile photo from public OpenGraph tags via crawler headers with proxy fallback."""
    if not url or "facebook.com/" not in url:
        return None

    # 1. Primary: Direct crawler request with Twitterbot headers (Facebook serves rich OpenGraph tags directly)
    try:
        resp = await client.get(url, headers=TWITTER_HEADERS, timeout=4.0, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
            if og_img and og_img.get("content"):
                img_src = og_img.get("content").strip()
                if any(cdn in img_src for cdn in ("fbcdn.net", "fbsbx.com", "facebook.com")) and "static.xx" not in img_src and "fb_icon" not in img_src:
                    return html.unescape(img_src)
    except Exception:
        pass

    # 2. Secondary: Fallback via residential proxy
    p_url = get_random_proxy_url()
    if p_url:
        try:
            async with httpx.AsyncClient(proxy=p_url, timeout=4.0, follow_redirects=True, verify=False) as px_client:
                resp = await px_client.get(url, headers=TWITTER_HEADERS)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
                    if og_img and og_img.get("content"):
                        img_src = og_img.get("content").strip()
                        if any(cdn in img_src for cdn in ("fbcdn.net", "fbsbx.com", "facebook.com")) and "static.xx" not in img_src and "fb_icon" not in img_src:
                            return html.unescape(img_src)
        except Exception:
            pass

    return None



# ==========================================
# 7. DUCKDUCKGO DISTRIBUTED SEARCH ENGINE
# ==========================================
def _query_ddgs_sync(query: str, proxy_url: str, timeout: float = 5.0) -> List[Dict[str, str]]:
    """Execute DuckDuckGo search via residential proxy with backend='auto' and deep pagination (up to 25 items)."""
    if DDGS is None:
        return []
    ddgs = DDGS(proxy=proxy_url, timeout=timeout)
    results = list(ddgs.text(query, max_results=25, backend="auto"))
    items = []
    seen = set()
    for r in results:
        link = r.get("href", "")
        if link and link not in seen:
            if any(dom in link.lower() for dom in ("linkedin.com", "instagram.com", "facebook.com", "tiktok.com", "pinterest.com", "github.com", "x.com", "twitter.com", "spotify.com", "medium.com", "stackoverflow.com")):
                seen.add(link)
                items.append({
                    "link": link,
                    "title": html.unescape(r.get("title", "")),
                    "snippet": html.unescape(r.get("body", "")),
                })
    return items


def run_ddgs_auto_sync(q_str: str) -> List[Dict[str, str]]:
    """Fast failover using ddgs multi-engine browser impersonation with deep pagination (up to 20 items)."""
    if DDGS is None:
        return []
    try:
        ddgs = DDGS(timeout=4.5)
        results = None
        for b in ["google", "auto"]:
            try:
                res = list(ddgs.text(q_str, max_results=20, backend=b))
                if res:
                    results = res
                    break
            except Exception:
                continue
        if not results:
            return []
        items = []
        for r in results:
            if r.get("href"):
                items.append({
                    "link": r.get("href", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                })
        return items
    except Exception:
        return []


async def execute_ddg_html_query(
    query: str,
    primary_proxy_ip: str,
    max_retries: int = 1,
) -> Tuple[List[Dict[str, str]], str, int]:
    """
    Execute DuckDuckGo search query through a residential proxy IP with automatic failover.
    Utilizes DDGS tokenized session to prevent 202 JavaScript challenges.
    """
    available_ips = [primary_proxy_ip]
    fallback_pool = [ip for ip in proxy_pool.get_clean_ips() if ip != primary_proxy_ip]
    if fallback_pool:
        available_ips.extend(random.sample(fallback_pool, min(max_retries, len(fallback_pool))))

    items: List[Dict[str, str]] = []
    seen_links = set()
    used_ip = primary_proxy_ip
    attempts = 0

    for ip in available_ips[:2]:
        attempts += 1
        used_ip = ip
        proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{ip}" if (PROXY_USER and PROXY_PASS) else f"http://{ip}"
        t0 = time.time()
        try:
            items = await asyncio.to_thread(_query_ddgs_sync, query, proxy_url, 6.5)
            elapsed_ms = int((time.time() - t0) * 1000)

            if items:
                proxy_pool.mark_healthy(ip, elapsed_ms)
                print(f"  [DDG] [OK] '{query[:35]}...' -> {len(items)} hits (via {ip} in {elapsed_ms}ms)", flush=True)
                return items, used_ip, attempts
            else:
                proxy_pool.mark_healthy(ip, elapsed_ms)
                print(f"  [DDG] [0 HITS] '{query[:35]}...' -> 0 hits (via {ip} in {elapsed_ms}ms)", flush=True)
                break
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            err_msg = str(e).strip() or type(e).__name__
            if "202" in err_msg or "Ratelimit" in type(e).__name__:
                proxy_pool.mark_challenged(ip)
                print(f"  [DDG] [RATE-LIMIT] IP {ip} rate-limited. Retrying with fallback proxy...", flush=True)
            else:
                proxy_pool.latencies[ip] = max(proxy_pool.latencies.get(ip, 2000.0), float(elapsed_ms) * 1.5)
                print(f"  [DDG] [WARN] IP {ip} ({type(e).__name__}: {err_msg} in {elapsed_ms}ms). Retrying with fallback proxy...", flush=True)

    # Backup failover
    print(f"  [Failover] [BACKUP] Querying multi-engine backup for '{query[:35]}...'...", flush=True)
    fb_items = await asyncio.to_thread(run_ddgs_auto_sync, query)
    if fb_items:
        print(f"  [Failover] [OK] Retrieved {len(fb_items)} hits via backup failover", flush=True)
        for it in fb_items:
            if it["link"] and it["link"] not in seen_links:
                seen_links.add(it["link"])
                items.append(it)
    return items, used_ip, attempts


def extract_domains_and_handles(text: str) -> Tuple[Set[str], Set[str]]:
    """Extract domain links and handle mentions from bio/snippet."""
    if not text:
        return set(), set()
    domains = set(re.findall(r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})', text.lower()))
    common_ignore = {
        'github.com', 'twitter.com', 'x.com', 'linkedin.com', 'instagram.com',
        'facebook.com', 'medium.com', 'tiktok.com', 'pinterest.com', 'spotify.com',
        't.co', 'bit.ly', 'youtu.be', 'youtube.com', 'gravatar.com', 'google.com',
        'apple.com', 'microsoft.com', 'amazon.com', 'wikipedia.org', 'schema.org'
    }
    filtered_domains = {d for d in domains if d not in common_ignore and not d.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'))}
    handles = set(re.findall(r'@([a-zA-Z0-9_.-]{3,30})', text.lower()))
    return filtered_domains, handles


async def corroborate_candidate_profiles(
    candidates: List[Dict[str, Any]],
    anchor_avatar_url: Optional[str] = None,
    anchor_website: Optional[str] = None,
    anchor_profiles: Optional[Dict[str, Any]] = None,
    gh_username: Optional[str] = None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[Dict[str, Any]]:
    """
    Performs fast post-discovery candidate score boosting based on anchor website and verified handle graph.
    Promotes authentic candidates to the top of candidate lists without claiming false visual certainty.
    """
    if not candidates:
        return candidates

    anchor_domains: Set[str] = set()
    anchor_handles: Set[str] = set()
    if gh_username:
        anchor_handles.add(gh_username.lower().lstrip("@"))

    if anchor_website:
        d, _ = extract_domains_and_handles(anchor_website)
        anchor_domains.update(d)

    if anchor_profiles and isinstance(anchor_profiles, dict):
        for p_name, p_data in anchor_profiles.items():
            if isinstance(p_data, dict):
                if p_data.get("username"):
                    anchor_handles.add(str(p_data["username"]).lower().lstrip("@"))
                if p_data.get("blog"):
                    d, _ = extract_domains_and_handles(str(p_data["blog"]))
                    anchor_domains.update(d)
                if p_data.get("bio"):
                    d, h = extract_domains_and_handles(str(p_data["bio"]))
                    anchor_domains.update(d)
                    anchor_handles.update(h)

    for c in candidates:
        c_text = f"{c.get('name', '')} {c.get('snippet', '')} {c.get('url', '')}"
        c_domains, c_handles = extract_domains_and_handles(c_text)
        c_handle_clean = c.get("handle", "").lstrip("@").lower().strip()
        if c_handle_clean:
            c_handles.add(c_handle_clean)

        shared_domains = anchor_domains.intersection(c_domains)
        shared_handles = anchor_handles.intersection(c_handles)

        if shared_domains:
            domain_val = list(shared_domains)[0]
            c["score"] = max(c.get("score", 0), 95)
            if "reasons" in c and not any("website link" in r for r in c["reasons"]):
                c["reasons"].insert(0, f"Reciprocal personal website match ({domain_val})")
        elif shared_handles and len(list(shared_handles)[0]) >= 3:
            handle_val = list(shared_handles)[0]
            c["score"] = max(c.get("score", 0), 95)
            if "reasons" in c and not any("verified handle" in r for r in c["reasons"]):
                c["reasons"].insert(0, f"Cross-platform verified handle match (@{handle_val})")

    return candidates


# ==========================================
# 8. MASTER HYBRID DISCOVERY ENGINE
# ==========================================
async def search_social_candidates(
    email: str,
    resolved_name: Optional[str] = None,
    resolved_location: Optional[str] = None,
    gh_username: Optional[str] = None,
    company_name: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    has_verified_linkedin: bool = False,
    verified_platforms: Optional[Set[str]] = None,
    anchor_avatar: Optional[str] = None,
    anchor_website: Optional[str] = None,
    anchor_profiles: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """
    Master candidate discovery engine combining:
    1. High-speed direct probing with OpenGraph extraction for unverified platforms.
    2. Focused DuckDuckGo search queries for unverified platforms distributed across distinct residential proxy IPs.
    3. Multi-anchor scoring with Jaro-Winkler string similarity and surname disambiguation.
    """
    local_part = email.split("@")[0].lower().strip() if "@" in email else ""
    inferred_first, inferred_last = split_compound_name(local_part)
    inferred_name = f"{inferred_first} {inferred_last}".strip() if (inferred_first and inferred_last) else (inferred_first or "")

    # ── Alias detection ───────────────────────────────────────────────────────
    # If resolved_name is a single token (e.g. "Mikka", "Thor") that does not
    # appear anywhere in the email local-part, it is almost certainly a nickname
    # or alias chosen for a different context (e.g. a gaming handle on GitHub).
    # Using it as the DDG search query floods results with unrelated people who
    # share that nickname. Instead:
    #   • Use the email-derived compound name for the DDG text query.
    #   • Keep resolved_name as a scoring anchor for confirmed handle matches.
    _is_alias_name = (
        resolved_name
        and len(resolved_name.split()) == 1
        and resolved_name.lower() not in local_part.lower()
    )
    if _is_alias_name:
        print(
            f"[DDG Engine] Single-token resolved_name '{resolved_name}' is not present in "
            f"local_part '{local_part}' — treating as alias. "
            f"DDG query will use email-derived name instead.",
            flush=True,
        )

    effective_name = resolved_name or (inferred_name if (inferred_name and len(inferred_name.split()) >= 2) else None)
    # For DDG query purposes, override effective_name with email-derived name when alias detected
    ddg_name = (
        (inferred_name if (inferred_name and len(inferred_name.split()) >= 2) else None)
        if _is_alias_name
        else effective_name
    )

    # Track platforms that are already verified — bypass redundant probing and DDG searches for them
    v_plats = set(verified_platforms) if verified_platforms else set()
    if has_verified_linkedin:
        v_plats.add("linkedin")
    if gh_username:
        v_plats.add("github")

    # Parse clean name tokens — use ddg_name (alias-safe) for query building
    tokens = [p for p in re.findall(r"[a-zA-Z]+", ddg_name or resolved_name or local_part)]
    if tokens and tokens[0].lower() in TITLE_PREFIXES and len(tokens) > 1:
        core_human_name = " ".join(p.capitalize() for p in tokens[1:])
    else:
        core_human_name = ddg_name

    query_target = core_human_name if (core_human_name and len(core_human_name.split()) >= 2) else (ddg_name or resolved_name or local_part)

    # Handle variations use effective_name so alias handles (e.g. "mikka") are still direct-probed
    specific_handles, stem_handles = generate_handle_variations(email, effective_name or resolved_name, gh_username)
    probe_seeds = expand_social_probe_handles(specific_handles, stem_handles, effective_name or resolved_name)[:25]
    all_variations = specific_handles + stem_handles + probe_seeds

    print(f"\n[DDG Engine] ---------------------------------------------------", flush=True)
    print(f"[DDG Engine] Target: {email} | Inferred Name: '{effective_name or resolved_name}' | DDG Query: '{query_target}'", flush=True)
    if v_plats:
        print(f"[DDG Engine] Skipping redundant probes for already verified platforms: {sorted(list(v_plats))}", flush=True)

    # 1. Build Direct Probe Tasks (Skip if platform is already verified)
    combined_seeds = list(dict.fromkeys(specific_handles + probe_seeds))
    ig_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".") for s in combined_seeds if 3 <= len(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".")) <= 30))
    med_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9._-]', '', s).lstrip("@").strip("._-") for s in combined_seeds if 2 <= len(re.sub(r'[^a-zA-Z0-9._-]', '', s).lstrip("@").strip("._-")) <= 40))
    tt_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".") for s in combined_seeds if 2 <= len(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".")) <= 24))
    pin_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".") for s in combined_seeds if 3 <= len(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".")) <= 30))
    tw_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9_]', '_', s).lstrip("@").strip("_") for s in combined_seeds if 4 <= len(re.sub(r'[^a-zA-Z0-9_]', '_', s).lstrip("@").strip("_")) <= 15))
    fb_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9.]', '', s).lstrip("@").strip(".") for s in combined_seeds if 5 <= len(re.sub(r'[^a-zA-Z0-9.]', '', s).lstrip("@").strip(".")) <= 50))
    gh_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9_-]', '', s).lstrip("@").strip("_-") for s in combined_seeds if 1 <= len(re.sub(r'[^a-zA-Z0-9_-]', '', s).lstrip("@").strip("_-")) <= 39))

    limits = httpx.Limits(max_connections=60, max_keepalive_connections=25)
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0), limits=limits, verify=False) as probe_client:
        probe_tasks = []
        if "medium" not in v_plats:
            for s in med_seeds:
                probe_tasks.append(probe_medium_profile(s, probe_client))
        if "instagram" not in v_plats:
            for s in ig_seeds:
                probe_tasks.append(probe_instagram_profile(s, probe_client))
        if "tiktok" not in v_plats:
            for s in tt_seeds:
                probe_tasks.append(probe_tiktok_profile(s, probe_client))
        if "pinterest" not in v_plats:
            for s in pin_seeds:
                probe_tasks.append(probe_pinterest_profile(s, probe_client))
        if "twitter" not in v_plats:
            for s in tw_seeds:
                probe_tasks.append(probe_twitter_profile(s, probe_client))
        if "facebook" not in v_plats:
            for s in fb_seeds:
                probe_tasks.append(probe_facebook_profile(s, probe_client))
        if "github" not in v_plats and not gh_username:
            for s in gh_seeds:
                probe_tasks.append(probe_github_profile(s, probe_client))

        # 2. Build Focused DDG Search Queries (Skip if platform is already verified)
        clean_target = query_target.replace('"', '').strip()
        first_tok = tokens[0] if tokens else ""
        
        # Extract candidate nickname/handle stems from local_part (e.g. roaan.dev -> ['roaan'])
        role_words = {"dev", "tech", "official", "real", "io", "me", "hq", "app", "pro", "code", "design"}
        raw_tokens = [re.sub(r'[\d._+-]+', '', p).strip().lower() for p in re.split(r'[._+-]', local_part) if p]
        handle_stems = [p for p in raw_tokens if p and p not in role_words and len(p) >= 3 and p.lower() not in TITLE_PREFIXES]

        ddg_search_queries = []

        if "medium" not in v_plats:
            ddg_search_queries.append(("medium", f'{clean_target} medium'))
        if "instagram" not in v_plats:
            ddg_search_queries.append(("instagram", f'{clean_target} instagram'))
        if "twitter" not in v_plats:
            ddg_search_queries.append(("twitter", f'{clean_target} twitter'))
        if "facebook" not in v_plats:
            ddg_search_queries.append(("facebook", f'site:facebook.com {clean_target}'))
        if "tiktok" not in v_plats:
            ddg_search_queries.append(("tiktok", f'{clean_target} tiktok'))
        if "pinterest" not in v_plats:
            ddg_search_queries.append(("pinterest", f'{clean_target} pinterest'))
        if "spotify" not in v_plats:
            if len(clean_target.split()) >= 2:
                ddg_search_queries.append(("spotify", f'site:open.spotify.com/user/ "{clean_target}"'))
            elif clean_target:
                ddg_search_queries.append(("spotify", f'site:open.spotify.com/user/ {clean_target}'))
            for stem in handle_stems:
                if stem.lower() != clean_target.lower():
                    ddg_search_queries.append(("spotify", f'site:open.spotify.com/user/ {stem}'))
        if "linkedin" not in v_plats:
            ddg_search_queries.append(("linkedin", f'{clean_target} linkedin'))
            if len(clean_target.split()) >= 2:
                ddg_search_queries.append(("linkedin", f'site:linkedin.com/in/ "{clean_target}"'))
            handle_slug = re.sub(r'[\d._+-]+', '', local_part).lower().strip()
            if handle_slug and len(handle_slug) >= 4 and handle_slug != clean_target.lower().replace(' ', ''):
                ddg_search_queries.append(("linkedin", f'{handle_slug} linkedin'))

        for stem in ([first_tok] if first_tok else []) + handle_stems:
            if stem and len(stem) >= 3 and stem.lower() not in TITLE_PREFIXES and stem.lower() != clean_target.lower():
                if "instagram" not in v_plats:
                    ddg_search_queries.append(("instagram", f'{stem} instagram'))
                if "twitter" not in v_plats:
                    ddg_search_queries.append(("twitter", f'{stem} twitter'))

        # Direct Spotify Pathfinder GraphQL searches
        spotify_search_tasks = []
        if "spotify" not in v_plats:
            seen_sp_q = set()
            if clean_target and clean_target.lower() not in seen_sp_q:
                spotify_search_tasks.append(search_spotify_users_pathfinder(clean_target, probe_client))
                seen_sp_q.add(clean_target.lower())
            for stem in handle_stems:
                if stem.lower() not in seen_sp_q and len(stem) >= 3:
                    spotify_search_tasks.append(search_spotify_users_pathfinder(stem, probe_client))
                    seen_sp_q.add(stem.lower())
            if first_tok and len(first_tok) >= 3 and first_tok.lower() not in TITLE_PREFIXES and first_tok.lower() not in seen_sp_q:
                spotify_search_tasks.append(search_spotify_users_pathfinder(first_tok, probe_client))
                seen_sp_q.add(first_tok.lower())

        # Stack Overflow API Searches
        stackoverflow_search_tasks = []
        if "stackoverflow" not in v_plats:
            seen_so_q = set()
            if clean_target and len(clean_target) >= 3 and clean_target.lower() not in seen_so_q:
                stackoverflow_search_tasks.append(search_stackoverflow_users(clean_target, probe_client))
                seen_so_q.add(clean_target.lower())
            if resolved_name and len(resolved_name) >= 3 and resolved_name.lower() not in seen_so_q:
                stackoverflow_search_tasks.append(search_stackoverflow_users(resolved_name, probe_client))
                seen_so_q.add(resolved_name.lower())
            for stem in handle_stems:
                if stem.lower() not in seen_so_q and len(stem) >= 3:
                    stackoverflow_search_tasks.append(search_stackoverflow_users(stem, probe_client))
                    seen_so_q.add(stem.lower())
            if gh_username and len(gh_username) >= 3 and gh_username.lower() not in seen_so_q:
                stackoverflow_search_tasks.append(search_stackoverflow_users(gh_username, probe_client))
                seen_so_q.add(gh_username.lower())

        # Assign each query its own distinct clean residential IP
        sampled_ips = proxy_pool.sample_distinct(len(ddg_search_queries))
        query_configs = [(plat, q, sampled_ips[i]) for i, (plat, q) in enumerate(ddg_search_queries)]

        print(f"[DDG Engine] Launching direct probes ({len(probe_tasks)}) + {len(query_configs)} DDG queries...", flush=True)

        async def run_single_ddg(plat_tag: str, q_str: str, assigned_ip: str):
            hits, used_ip, attempts = await execute_ddg_html_query(q_str, assigned_ip)
            return plat_tag, hits

        query_tasks = [run_single_ddg(p, q, ip) for p, q, ip in query_configs]

        # 3. Concurrently execute all Probes, Spotify, Stack Overflow, and DDG Queries
        t_start = time.time()
        probe_results_raw, spotify_results_raw, so_results_raw, *query_results_raw = await asyncio.gather(
            asyncio.gather(*probe_tasks, return_exceptions=True),
            asyncio.gather(*spotify_search_tasks, return_exceptions=True),
            asyncio.gather(*stackoverflow_search_tasks, return_exceptions=True),
            *query_tasks
        )
        discovery_elapsed_ms = int((time.time() - t_start) * 1000)
        print(f"[DDG Engine] All Probes & DDG searches completed in {discovery_elapsed_ms}ms", flush=True)

    candidates_map: Dict[str, Dict[str, Any]] = {}

    def make_candidate_dedup_key(p_plat: str, p_handle: str, p_url: str = "") -> str:
        h = p_handle.lstrip("@").strip().lower()
        if p_plat == "linkedin":
            h = h.split("/")[0].strip()
            return f"linkedin:{h}"
        if p_plat == "facebook":
            return f"facebook:{h.replace('.', '')}"
        if p_plat == "stackoverflow" and p_url:
            m = re.search(r"/users/(\d+)", p_url)
            if m:
                return f"stackoverflow:{m.group(1)}"
        return f"{p_plat}:{h.split('/')[0].strip()}"

    # Ingest Direct Stack Overflow User Search Hits
    for so_batch in so_results_raw:
        if not isinstance(so_batch, list):
            continue
        for so_cand in so_batch:
            if not isinstance(so_cand, dict) or not so_cand.get("url"):
                continue
            h_clean = so_cand["handle"].lstrip("@")
            dedup_key = make_candidate_dedup_key("stackoverflow", h_clean, so_cand["url"])
            cand_name = so_cand.get("name") or h_clean
            reputation = so_cand.get("reputation", 0)

            score, reasons, sub_scores, evidence = score_candidate(
                {"platform": "stackoverflow", "platform_label": "Stack Overflow", "handle": h_clean, "url": so_cand["url"], "reputation": reputation},
                so_cand.get("title") or f"{cand_name} on Stack Overflow",
                so_cand.get("snippet", ""),
                all_variations,
                effective_name or resolved_name,
                resolved_location,
                gh_username,
                company_name,
            )

            is_direct_exact = (cand_name.lower() == clean_target.lower())
            if not is_direct_exact and effective_name:
                is_direct_exact = (cand_name.lower() == effective_name.lower())
            is_stem_exact = any(stem.lower() == cand_name.lower() for stem in handle_stems)

            if is_direct_exact or is_stem_exact:
                score = max(score, 85)
                reasons.append(f"Direct Stack Overflow exact display name match ('{cand_name}')")
                sub_scores["name_score"] = max(sub_scores.get("name_score", 0), 45)
                sub_scores["final_score"] = score
            elif score >= 35:
                score = max(score, 50)
                sub_scores["final_score"] = score
            elif score < 15:
                if (first_tok and first_tok.lower() in cand_name.lower()) or any(stem.lower() in cand_name.lower() for stem in handle_stems):
                    score = 45
                    reasons.append(f"Stack Overflow user match ('{cand_name}')")
                    sub_scores = {"handle_score": 0, "name_score": 40, "company_score": 0, "location_score": 0, "final_score": 45}
                else:
                    continue

            # Extra reputation boost for active reputable accounts
            if reputation >= 1000:
                score = min(score + 10, 95)
                sub_scores["final_score"] = score
            elif reputation >= 100:
                score = min(score + 5, 95)
                sub_scores["final_score"] = score

            cand_obj = {
                "platform": "stackoverflow",
                "platform_label": "Stack Overflow",
                "handle": f"@{h_clean}",
                "name": cand_name,
                "url": so_cand["url"],
                "snippet": so_cand.get("snippet", f"Stack Overflow profile for {cand_name}"),
                "score": score,
                "confidence_badge": "",
                "confidence_level": "strong" if score >= 70 else "potential",
                "reasons": reasons,
                "sub_scores": sub_scores,
                "evidence": evidence,
                "avatar_url": so_cand.get("avatar_url"),
                "discovery_method": "stackoverflow_api"
            }
            if dedup_key not in candidates_map:
                candidates_map[dedup_key] = cand_obj
            else:
                existing = candidates_map[dedup_key]
                has_better_avatar = not existing.get("avatar_url") and cand_obj.get("avatar_url")
                if score > existing.get("score", 0) or has_better_avatar:
                    if not cand_obj.get("avatar_url") and existing.get("avatar_url"):
                        cand_obj["avatar_url"] = existing["avatar_url"]
                    candidates_map[dedup_key] = cand_obj

    # Ingest Direct Spotify User Search Hits (with CDN avatars & authentic display names)
    for sp_batch in spotify_results_raw:
        if not isinstance(sp_batch, list):
            continue
        for sp_cand in sp_batch:
            if not isinstance(sp_cand, dict) or not sp_cand.get("url"):
                continue
            h_clean = sp_cand["handle"].lstrip("@")
            dedup_key = make_candidate_dedup_key("spotify", h_clean)
            cand_name = sp_cand.get("name") or h_clean

            score, reasons, sub_scores, evidence = score_candidate(
                {"platform": "spotify", "platform_label": "Spotify", "handle": h_clean, "url": sp_cand["url"]},
                sp_cand.get("title") or f"{cand_name} on Spotify",
                sp_cand.get("snippet", ""),
                all_variations,
                effective_name or resolved_name,
                resolved_location,
                gh_username,
                company_name,
            )

            is_direct_exact = (cand_name.lower() == clean_target.lower())
            if not is_direct_exact and effective_name:
                is_direct_exact = (cand_name.lower() == effective_name.lower())
            is_stem_exact = any(stem.lower() == cand_name.lower() for stem in handle_stems)

            if is_direct_exact or is_stem_exact:
                score = max(score, 80)
                reasons.append(f"Direct Spotify search exact display name match ('{cand_name}')")
                sub_scores["name_score"] = max(sub_scores.get("name_score", 0), 45)
                sub_scores["final_score"] = score
            elif score >= 35:
                score = max(score, 50)
                sub_scores["final_score"] = score
            elif score < 15:
                if (first_tok and first_tok.lower() in cand_name.lower()) or any(stem.lower() in cand_name.lower() for stem in handle_stems):
                    score = 45
                    reasons.append(f"Direct Spotify search user match ('{cand_name}')")
                    sub_scores = {"handle_score": 0, "name_score": 40, "company_score": 0, "location_score": 0, "final_score": 45}
                else:
                    continue

            cand_obj = {
                "platform": "spotify",
                "platform_label": "Spotify",
                "handle": f"@{h_clean}",
                "name": cand_name,
                "url": sp_cand["url"],
                "snippet": sp_cand.get("snippet", f"Spotify profile for {cand_name}"),
                "score": score,
                "confidence_badge": "",
                "confidence_level": "strong" if score >= 70 else "potential",
                "reasons": reasons,
                "sub_scores": sub_scores,
                "evidence": evidence,
                "avatar_url": sp_cand.get("avatar_url"),
                "discovery_method": "spotify_api"
            }
            if dedup_key not in candidates_map:
                candidates_map[dedup_key] = cand_obj
            else:
                existing = candidates_map[dedup_key]
                has_better_avatar = not existing.get("avatar_url") and cand_obj.get("avatar_url")
                if score > existing.get("score", 0) or has_better_avatar:
                    if not cand_obj.get("avatar_url") and existing.get("avatar_url"):
                        cand_obj["avatar_url"] = existing["avatar_url"]
                    candidates_map[dedup_key] = cand_obj

    # Ingest Probe Hits
    for p_cand in probe_results_raw:
        if not isinstance(p_cand, dict) or not p_cand.get("url"):
            continue
        plat = p_cand["platform"]
        h_clean = p_cand["handle"].lstrip("@")
        parsed = {
            "platform": plat,
            "platform_label": p_cand["platform_label"],
            "handle": h_clean,
            "url": p_cand["url"],
        }
        score, reasons, sub_scores, evidence = score_candidate(
            parsed,
            p_cand.get("title", ""),
            p_cand.get("snippet", ""),
            all_variations,
            effective_name or resolved_name,
            resolved_location,
            gh_username,
            company_name,
        )
        if score >= 15:
            dedup_key = make_candidate_dedup_key(plat, h_clean)
            cand_obj = {
                "platform": plat,
                "platform_label": p_cand["platform_label"],
                "handle": f"@{h_clean}",
                "name": p_cand.get("name") or h_clean,
                "url": p_cand["url"],
                "snippet": p_cand.get("snippet", ""),
                "score": score,
                "confidence_badge": "",
                "confidence_level": "strong" if score >= 70 else "potential",
                "reasons": reasons,
                "sub_scores": sub_scores,
                "evidence": evidence,
                "avatar_url": p_cand.get("avatar_url"),
                "discovery_method": "probing"
            }
            if dedup_key not in candidates_map:
                candidates_map[dedup_key] = cand_obj
            else:
                existing = candidates_map[dedup_key]
                has_better_avatar = not existing.get("avatar_url") and p_cand.get("avatar_url")
                has_better_dots = ("." in h_clean and "." not in existing.get("handle", ""))
                if score > existing.get("score", 0) or has_better_avatar or (score == existing.get("score", 0) and has_better_dots):
                    if not cand_obj.get("avatar_url") and existing.get("avatar_url"):
                        cand_obj["avatar_url"] = existing["avatar_url"]
                    candidates_map[dedup_key] = cand_obj

    # Ingest DDG Search Hits
    for q_res in query_results_raw:
        if not isinstance(q_res, tuple) or len(q_res) != 2:
            continue
        plat_tag, items = q_res
        for it in items:
            link = it.get("link", "")
            title = it.get("title", "")
            snippet = it.get("snippet", "")
            parsed = parse_social_url(link)
            if not parsed:
                continue

            plat = parsed["platform"]
            h_clean = parsed["handle"].lstrip("@")
            dedup_key = make_candidate_dedup_key(plat, h_clean)

            score, reasons, sub_scores, evidence = score_candidate(
                parsed,
                title,
                snippet,
                all_variations,
                effective_name or resolved_name,
                resolved_location,
                gh_username,
                company_name,
            )
            if score < 15:
                if plat == "spotify":
                    score = 30
                    reasons = [f"Discovered via Spotify user profile search ({clean_target})"]
                    sub_scores = {"handle_score": 0, "name_score": 30, "company_score": 0, "location_score": 0, "final_score": 30}
                else:
                    continue

            display_name = clean_display_name(title, h_clean, plat, effective_name or resolved_name)
            bio_clean = clean_bio_snippet(snippet, plat, h_clean)

            if dedup_key not in candidates_map:
                candidates_map[dedup_key] = {
                    "platform": plat,
                    "platform_label": parsed["platform_label"],
                    "handle": f"@{h_clean}",
                    "name": display_name or h_clean,
                    "url": parsed["url"],
                    "snippet": bio_clean,
                    "score": score,
                    "confidence_badge": "",
                    "confidence_level": "strong" if score >= 70 else "potential",
                    "reasons": reasons,
                    "sub_scores": sub_scores,
                    "evidence": evidence,
                    "avatar_url": None,
                    # DDG-discovered Spotify candidates need post-probe validation.
                    # Enrichment must confirm the display name matches the target;
                    # if enrichment fails or is skipped this flag keeps them removable.
                    "_sp_ddg": plat == "spotify" and score <= 30,
                }
            else:
                existing = candidates_map[dedup_key]
                existing_avatar = existing.get("avatar_url")
                has_better_dots = ("." in h_clean and "." not in existing.get("handle", ""))
                if score > existing.get("score", 0) or (score == existing.get("score", 0) and has_better_dots):
                    candidates_map[dedup_key] = {
                        "platform": plat,
                        "platform_label": parsed["platform_label"],
                        "handle": f"@{h_clean}",
                        "name": display_name or h_clean,
                        "url": parsed["url"],
                        "snippet": bio_clean,
                        "score": max(score, existing.get("score", 0)),
                        "confidence_badge": "",
                        "confidence_level": "strong" if max(score, existing.get("score", 0)) >= 70 else "potential",
                        "reasons": reasons,
                        "sub_scores": sub_scores,
                        "evidence": evidence,
                        "avatar_url": existing_avatar,
                    }

    # Concurrent Avatar Enrichment (LinkedIn + Instagram + Facebook + Spotify + Medium candidates via crawler headers)
    enrich_tasks = []
    li_count = 0
    med_count = 0
    ig_count = 0
    fb_count = 0
    sp_count = 0
    for c in candidates_map.values():
        if not c.get("avatar_url"):
            if c["platform"] == "linkedin" and "linkedin" not in v_plats and li_count < 15:
                enrich_tasks.append(("linkedin", c))
                li_count += 1
            elif c["platform"] == "medium" and med_count < 15:
                enrich_tasks.append(("medium", c))
                med_count += 1
            elif c["platform"] == "instagram" and "instagram" not in v_plats and ig_count < 15:
                enrich_tasks.append(("instagram", c))
                ig_count += 1
            elif c["platform"] == "facebook" and "facebook" not in v_plats and fb_count < 8:
                enrich_tasks.append(("facebook", c))
                fb_count += 1
            elif c["platform"] == "spotify" and sp_count < 15:
                enrich_tasks.append(("spotify", c))
                sp_count += 1

    if enrich_tasks:
        async def enrich_candidate(plat, c, http_client):
            if plat == "linkedin":
                av, canon_url = await fetch_linkedin_candidate_avatar(c["url"], http_client)
                if av:
                    c["avatar_url"] = av
                if canon_url and "linkedin.com/in/" in canon_url:
                    m_slug = re.search(r"linkedin\.com/in/([a-zA-Z0-9_/%-]+)", canon_url, re.IGNORECASE)
                    if m_slug:
                        raw_slug = m_slug.group(1).split("?")[0].split("#")[0].rstrip("/").strip()
                        canon_slug = raw_slug.split("/")[0].strip()
                        if canon_slug and canon_slug.lower() not in ("dir", "pub", "feed") and len(canon_slug) >= 3:
                            c["handle"] = f"@{canon_slug}"
                            c["url"] = f"https://www.linkedin.com/in/{canon_slug}"
            elif plat == "medium":
                h_slug = c["handle"].lstrip("@").strip()
                med_data = await probe_medium_profile(h_slug, http_client)
                if med_data:
                    if med_data.get("avatar_url"):
                        c["avatar_url"] = med_data["avatar_url"]
                    if med_data.get("name"):
                        c["name"] = med_data["name"]
                    if med_data.get("snippet"):
                        c["snippet"] = med_data["snippet"]
            elif plat == "instagram":
                h_slug = c["handle"].lstrip("@").strip()
                ig_data = await probe_instagram_profile(h_slug, http_client)
                if ig_data:
                    if ig_data.get("avatar_url"):
                        c["avatar_url"] = ig_data["avatar_url"]
                    if ig_data.get("name") and (not c.get("name") or c["name"] == c["handle"].lstrip("@") or len(c.get("name", "")) > 30):
                        c["name"] = ig_data["name"]
                    if ig_data.get("snippet") and not c.get("snippet"):
                        c["snippet"] = ig_data["snippet"]
            elif plat == "facebook":
                av = await fetch_facebook_candidate_avatar(c["url"], http_client)
                if av:
                    c["avatar_url"] = av
            elif plat == "spotify":
                h_slug = c["handle"].lstrip("@").strip()
                sp_data = await probe_spotify_profile(h_slug, http_client)
                if sp_data:
                    if sp_data.get("avatar_url"):
                        c["avatar_url"] = sp_data["avatar_url"]
                    if sp_data.get("name") and (not c.get("name") or c["name"] == c["handle"].lstrip("@") or c["name"] == "on Spotify"):
                        c["name"] = sp_data["name"]
                    if sp_data.get("snippet") and not c.get("snippet"):
                        c["snippet"] = sp_data["snippet"]
                    # Re-score candidate with the authentic probed profile name
                    n_score, n_reasons, n_sub, n_ev = score_candidate(
                        {"platform": "spotify", "platform_label": "Spotify", "handle": h_slug, "url": c["url"]},
                        c["name"],
                        c.get("snippet", ""),
                        all_variations,
                        effective_name or resolved_name,
                        resolved_location,
                        gh_username,
                        company_name,
                    )
                    if n_score >= 15:
                        c["score"] = n_score
                        c["reasons"] = n_reasons
                        c["sub_scores"] = n_sub
                        c["evidence"] = n_ev
                        c["confidence_level"] = "strong" if n_score >= 70 else "potential"
                    elif c.get("score", 0) <= 30:
                        # DDG-discovered candidate; probed name doesn't match target → flag for removal
                        c["_remove"] = True
                else:
                    # Probe returned nothing; DDG-discovered candidates are noise → remove
                    if c.get("score", 0) <= 30:
                        c["_remove"] = True

        async with httpx.AsyncClient(timeout=6.0, verify=False) as av_client:
            await asyncio.gather(*[enrich_candidate(plat, c, av_client) for plat, c in enrich_tasks], return_exceptions=True)

    # Purge Spotify candidates that failed post-probe validation (irrelevant DDG noise).
    # Two removal conditions:
    #  1. _remove=True  → enrichment probed and found name doesn't match target
    #  2. _sp_ddg=True AND score ≤ 30 → enrichment was skipped (limit/exception) so
    #     the DDG-discovered candidate was never name-validated; remove as untrusted
    for dk in list(candidates_map.keys()):
        c = candidates_map[dk]
        if c.get("_remove") or (c.get("_sp_ddg") and c.get("score", 0) <= 30):
            del candidates_map[dk]

    # Post-enrichment cross-candidate deduplication pass:
    # Merge duplicate candidate entries that share the same canonical URL or identical profile avatar photo
    merged_candidates: Dict[str, Dict[str, Any]] = {}
    for c in candidates_map.values():
        plat = c["platform"]
        h_clean = c["handle"].lstrip("@").strip().lower()
        if plat == "linkedin":
            h_clean = h_clean.split("/")[0].strip()
            c["handle"] = f"@{h_clean}"
            c["url"] = f"https://www.linkedin.com/in/{h_clean}"
        p_key = f"{plat}:{h_clean}"
        if plat == "stackoverflow":
            m_uid = re.search(r"/users/(\d+)", c.get("url", ""))
            if m_uid:
                p_key = f"stackoverflow:{m_uid.group(1)}"
        av_key = f"{plat}:av:{c['avatar_url']}" if c.get("avatar_url") else None

        existing_key = None
        if av_key and av_key in merged_candidates:
            existing_key = av_key
        elif p_key in merged_candidates:
            existing_key = p_key

        if existing_key is None:
            merged_candidates[p_key] = c
            if av_key:
                merged_candidates[av_key] = c
        else:
            existing = merged_candidates[existing_key]
            # Merge: Keep the richer snippet, higher score, and authentic avatar
            has_better_avatar = not existing.get("avatar_url") and c.get("avatar_url")
            has_richer_snippet = len(c.get("snippet", "")) > len(existing.get("snippet", "")) and not "profile for @" in c.get("snippet", "")
            if c["score"] > existing["score"] or has_better_avatar or (c["score"] == existing["score"] and has_richer_snippet):
                if not c.get("avatar_url") and existing.get("avatar_url"):
                    c["avatar_url"] = existing.get("avatar_url")
                merged_candidates[p_key] = c
                if av_key:
                    merged_candidates[av_key] = c
                if existing_key != p_key:
                    merged_candidates[existing_key] = c

    unique_candidates = list({id(v): v for v in merged_candidates.values()}.values())
    
    # Run fast post-discovery corroboration (perceptual avatar dHash + reciprocal bio/link-graph)
    unique_candidates = await corroborate_candidate_profiles(
        unique_candidates,
        anchor_avatar_url=anchor_avatar,
        anchor_website=anchor_website,
        anchor_profiles=anchor_profiles,
        gh_username=gh_username,
        http_client=client,
    )

    all_candidates = sorted(unique_candidates, key=lambda x: -x["score"])

    # Group by platform in priority order: LinkedIn -> GitHub -> Stack Overflow -> Medium -> Instagram -> Facebook -> X -> Pinterest -> TikTok -> Spotify
    by_platform = {
        "linkedin": [c for c in all_candidates if c["platform"] == "linkedin"],
        "github": [c for c in all_candidates if c["platform"] == "github"],
        "stackoverflow": [c for c in all_candidates if c["platform"] == "stackoverflow"],
        "medium": [c for c in all_candidates if c["platform"] == "medium"],
        "instagram": [c for c in all_candidates if c["platform"] == "instagram"],
        "facebook": [c for c in all_candidates if c["platform"] == "facebook"],
        "twitter": [c for c in all_candidates if c["platform"] == "twitter"],
        "pinterest": [c for c in all_candidates if c["platform"] == "pinterest"],
        "tiktok": [c for c in all_candidates if c["platform"] == "tiktok"],
        "spotify": [c for c in all_candidates if c["platform"] == "spotify"],
    }

    total_count = sum(len(v) for v in by_platform.values())
    print(f"[Social Discovery] [OK] Discovery Complete! Total Unique Ranked Candidates: {len(all_candidates)}", flush=True)
    if all_candidates:
        top = all_candidates[0]
        print(f"[Social Discovery] Top Match: [{top['platform'].upper()}] {top['handle']} ({top['name']}) -> Score: {top['score']}%", flush=True)
    print(f"[Social Discovery] ---------------------------------------------------\n", flush=True)

    return all_candidates[:40], by_platform
