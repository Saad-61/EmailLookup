"""
standalone_ddg_test.py
----------------------
Standalone test script and interactive server evaluating DuckDuckGo with Residential Proxy Rotation
as a direct replacement for SearXNG.

Usage:
  1. CLI manual test:
       python standalone_ddg_test.py sarah.jenkins.hr@gmail.com
       python standalone_ddg_test.py saadasif78656@gmail.com

  2. Frontend Web Server (Serves the UI on port 8001):
       python standalone_ddg_test.py --server
       python standalone_ddg_test.py --server --port 8001
"""

import asyncio
import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import re
import html
import time
import random
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "backend"))

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

if DDGS is not None:
    print("  [Engine] ✓ ddgs search library initialized successfully", flush=True)
else:
    print("  [Engine] ⚠️ WARNING: ddgs library not found in this Python environment!", flush=True)

load_dotenv(BASE_DIR / ".env", override=True)

# Import existing core modules without modifying them
from social_finder import (
    score_candidate,
    parse_social_url,
    clean_display_name,
    clean_bio_snippet,
    generate_handle_variations,
    expand_social_probe_handles,
    probe_instagram_profile,
    probe_tiktok_profile,
    probe_pinterest_profile,
    probe_twitter_profile,
    probe_facebook_profile,
    probe_github_profile,
    fetch_linkedin_candidate_avatar,
    fetch_facebook_candidate_avatar,
    jaro_winkler_similarity,
    TITLE_PREFIXES,
    ROLE_SUFFIXES,
)
from lookup_engine import run_lookup

# ── 1. DYNAMIC PROXY POOL & AUTO-COOLDOWN MANAGER ─────────────────────────
PROXY_USER = os.getenv("PROXY_USERNAME")
PROXY_PASS = os.getenv("PROXY_PASSWORD")
RAW_IPS = os.getenv("PROXY_IPS", "")
ALL_PROXY_IPS = [ip.strip() for ip in RAW_IPS.split(",") if ip.strip()]
PROXY_IPS = ALL_PROXY_IPS

class DynamicProxyPool:
    """
    Manages residential proxy IPs with automatic rate-limit cooldown and latency-based ranking.
    - Tracks temporary 202 blocks with an expiration timestamp (e.g. 10 minutes).
    - Automatically measures roundtrip response time on every query to route requests to the fastest nodes.
    - When cooldown expires, the proxy automatically re-joins the active pool.
    """
    def __init__(self, ip_list: List[str], cooldown_seconds: int = 600):
        self.all_ips = list(ip_list)
        self.cooldown_seconds = cooldown_seconds
        self.cooldowns: Dict[str, float] = {}
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
        """Temporarily flag an IP that encountered a 202 challenge or block."""
        cd = duration or self.cooldown_seconds
        self.cooldowns[ip] = time.time() + cd
        self.latencies[ip] = 9999.0
        remaining = len(self.get_clean_ips())
        print(f"  [ProxyPool] ⏳ IP {ip} flagged with {cd}s cooldown ({remaining} clean IPs remaining in pool)", flush=True)

    def mark_healthy(self, ip: str, elapsed_ms: Optional[int] = None):
        """Confirm an IP is clean and update its moving-average latency score."""
        if ip in self.cooldowns:
            del self.cooldowns[ip]
        if elapsed_ms is not None:
            prev = self.latencies.get(ip, float(elapsed_ms))
            self.latencies[ip] = prev * 0.35 + float(elapsed_ms) * 0.65

    def sample_distinct(self, n: int) -> List[str]:
        """Sample n distinct clean IPs, prioritizing the fastest responsive nodes."""
        clean = self.get_clean_ips()
        if len(clean) >= n:
            return clean[:n]
        return (clean * (n // max(1, len(clean)) + 1))[:n]

# Initialize pool with all configured proxies
proxy_pool = DynamicProxyPool(ALL_PROXY_IPS, cooldown_seconds=600)
print(f"  [ProxyPool] ✓ Initialized dynamic latency-ranked pool with {len(ALL_PROXY_IPS)} active residential proxies", flush=True)


# ── 2. REALISTIC BROWSER HEADERS (CHROME 124 ON WINDOWS) ────────────────────
CHROME_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://html.duckduckgo.com/",
}


def unwrap_ddg_url(raw_href: str) -> str:
    """Unwrap DuckDuckGo redirect link (e.g. //duckduckgo.com/l/?uddg=https%3A%2F%2F...) to real target URL."""
    if not raw_href:
        return ""
    if "uddg=" in raw_href:
        try:
            parsed = urllib.parse.urlparse(raw_href)
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs and qs["uddg"]:
                return urllib.parse.unquote(qs["uddg"][0])
        except Exception:
            pass
    clean = raw_href.replace("//duckduckgo.com", "https://duckduckgo.com")
    return clean


def _query_ddgs_sync(query: str, proxy_url: str, timeout: float = 4.5) -> List[Dict[str, str]]:
    """Execute DuckDuckGo search via residential proxy using official tokenized API session."""
    if DDGS is None:
        return []
    ddgs = DDGS(proxy=proxy_url, timeout=timeout)
    results = list(ddgs.text(query, max_results=10))
    items = []
    seen = set()
    for r in results:
        link = r.get("href", "")
        if link and link not in seen:
            if any(dom in link.lower() for dom in ("linkedin.com", "instagram.com", "facebook.com", "tiktok.com", "pinterest.com", "github.com", "x.com", "twitter.com")):
                seen.add(link)
                items.append({
                    "link": link,
                    "title": html.unescape(r.get("title", "")),
                    "snippet": html.unescape(r.get("body", "")),
                })
    return items


def run_ddgs_auto_sync(q_str: str) -> List[Dict[str, str]]:
    """Fast failover using ddgs multi-engine browser impersonation."""
    if DDGS is None:
        return []
    try:
        ddgs = DDGS(timeout=4)
        results = None
        for b in ["google", "auto"]:
            try:
                res = list(ddgs.text(q_str, max_results=8, backend=b))
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
        proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{ip}"
        t0 = time.time()
        try:
            items = await asyncio.to_thread(_query_ddgs_sync, query, proxy_url, 4.5)
            elapsed_ms = int((time.time() - t0) * 1000)

            if items:
                proxy_pool.mark_healthy(ip, elapsed_ms)
                print(f"  [DDG] ✓ '{query[:35]}...' -> {len(items)} hits (via {ip} in {elapsed_ms}ms)", flush=True)
                return items, used_ip, attempts
            else:
                proxy_pool.mark_healthy(ip, elapsed_ms)
                print(f"  [DDG] ℹ️ '{query[:35]}...' -> 0 hits (via {ip} in {elapsed_ms}ms)", flush=True)
                break
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            err_msg = str(e).strip() or type(e).__name__
            # Only challenge if DDG explicitly rate-limited or blocked
            if "202" in err_msg or "Ratelimit" in type(e).__name__:
                proxy_pool.mark_challenged(ip)
                print(f"  [DDG] ⏳ IP {ip} rate-limited. Retrying with fallback proxy...", flush=True)
            else:
                proxy_pool.latencies[ip] = max(proxy_pool.latencies.get(ip, 2000.0), float(elapsed_ms) * 1.5)
                print(f"  [DDG] ⚠️ IP {ip} ({type(e).__name__}: {err_msg} in {elapsed_ms}ms). Retrying with fallback proxy...", flush=True)

    # If DDG returned empty or failed on proxy, trigger fast multi-backend failover
    print(f"  [Failover] 🔄 Querying multi-engine backup for '{query[:35]}...'...", flush=True)
    fb_items = await asyncio.to_thread(run_ddgs_auto_sync, query)
    if fb_items:
        print(f"  [Failover] ✓ Retrieved {len(fb_items)} hits via backup failover", flush=True)
        for it in fb_items:
            if it["link"] and it["link"] not in seen_links:
                seen_links.add(it["link"])
                items.append(it)
    else:
        print(f"  [Failover] ℹ️ 0 hits retrieved via backup failover for '{query[:35]}...'", flush=True)
    return items, used_ip, attempts





# ── 3. HYBRID SOCIAL DISCOVERY USING DDG PROXY POOL ──────────────────────────
async def search_social_candidates_ddg(
    email: str,
    resolved_name: Optional[str] = None,
    resolved_location: Optional[str] = None,
    gh_username: Optional[str] = None,
    company_name: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    has_verified_linkedin: bool = False,
    **kwargs,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """
    Executes social discovery by combining:
    1. 125 direct high-speed OpenGraph crawler probes (Instagram, TikTok, Pinterest, Facebook, GitHub, Twitter).
    2. 5 focused DuckDuckGo queries distributed across 5 distinct residential proxy IPs.
    3. Multi-anchor scoring with Jaro-Winkler string similarity and surname disambiguation.
    """
    local_part = email.split("@")[0].lower().strip() if "@" in email else ""

    # Parse clean name tokens
    tokens = [p for p in re.findall(r"[a-zA-Z]+", resolved_name or local_part)]
    if tokens and tokens[0].lower() in TITLE_PREFIXES and len(tokens) > 1:
        core_human_name = " ".join(p.capitalize() for p in tokens[1:])
    else:
        core_human_name = resolved_name

    query_target = core_human_name if (core_human_name and len(core_human_name.split()) >= 2) else (resolved_name or local_part)

    specific_handles, stem_handles = generate_handle_variations(email, resolved_name, gh_username)
    probe_seeds = expand_social_probe_handles(specific_handles, stem_handles, resolved_name)[:25]
    all_variations = specific_handles + stem_handles + probe_seeds

    print(f"\n[DDG Engine] ───────────────────────────────────────────────────", flush=True)
    print(f"[DDG Engine] Target: {email} | Inferred Name: '{resolved_name}' | Query: '{query_target}'", flush=True)
    print(f"[DDG Engine] 📡 Launching 125 direct probes + 5 DDG queries via residential proxy pool...", flush=True)

    # 1. Build Direct Probe Tasks (Direct socket checks with crawler headers, no search engine)
    ig_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".") for s in probe_seeds if 3 <= len(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".")) <= 30))
    tt_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".") for s in probe_seeds if 2 <= len(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".")) <= 24))
    pin_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".") for s in probe_seeds if 3 <= len(re.sub(r'[^a-zA-Z0-9._]', '', s).lstrip("@").strip(".")) <= 30))
    tw_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9_]', '_', s).lstrip("@").strip("_") for s in probe_seeds if 4 <= len(re.sub(r'[^a-zA-Z0-9_]', '_', s).lstrip("@").strip("_")) <= 15))
    fb_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9.]', '', s).lstrip("@").strip(".") for s in probe_seeds if 5 <= len(re.sub(r'[^a-zA-Z0-9.]', '', s).lstrip("@").strip(".")) <= 50))
    gh_seeds = list(dict.fromkeys(re.sub(r'[^a-zA-Z0-9_-]', '', s).lstrip("@").strip("_-") for s in probe_seeds if 1 <= len(re.sub(r'[^a-zA-Z0-9_-]', '', s).lstrip("@").strip("_-")) <= 39))

    limits = httpx.Limits(max_connections=60, max_keepalive_connections=25)
    async with httpx.AsyncClient(timeout=4.0, limits=limits, verify=False) as probe_client:
        probe_tasks = []
        for s in ig_seeds: probe_tasks.append(probe_instagram_profile(s, probe_client))
        for s in tt_seeds: probe_tasks.append(probe_tiktok_profile(s, probe_client))
        for s in pin_seeds: probe_tasks.append(probe_pinterest_profile(s, probe_client))
        for s in tw_seeds: probe_tasks.append(probe_twitter_profile(s, probe_client))
        for s in fb_seeds: probe_tasks.append(probe_facebook_profile(s, probe_client))
        if not gh_username:
            for s in gh_seeds: probe_tasks.append(probe_github_profile(s, probe_client))

        # 2. Build Focused DDG Search Queries (skip LinkedIn if already verified)
        clean_target = query_target.replace('"', '').strip()
        ddg_search_queries = [
            ("instagram", f'site:instagram.com {clean_target}'),
            ("facebook", f'site:facebook.com {clean_target}'),
            ("tiktok", f'{clean_target} tiktok'),
            ("pinterest", f'{clean_target} pinterest'),
        ]
        if not has_verified_linkedin:
            ddg_search_queries.append(("linkedin", f'site:linkedin.com/in {clean_target}'))

        # Assign each query its own distinct clean residential IP
        sampled_ips = proxy_pool.sample_distinct(len(ddg_search_queries))
        query_configs = [(plat, q, sampled_ips[i]) for i, (plat, q) in enumerate(ddg_search_queries)]

        print(f"[DDG Engine] 📡 Launching 125 direct probes + {len(query_configs)} DDG queries via residential proxy pool...", flush=True)

        async def run_single_ddg(plat_tag: str, q_str: str, assigned_ip: str):
            hits, used_ip, attempts = await execute_ddg_html_query(q_str, assigned_ip)
            return plat_tag, hits

        query_tasks = [run_single_ddg(p, q, ip) for p, q, ip in query_configs]

        # 3. Concurrently execute all Probes and DDG Queries
        t_start = time.time()
        probe_results_raw, *query_results_raw = await asyncio.gather(
            asyncio.gather(*probe_tasks, return_exceptions=True),
            *query_tasks
        )
        discovery_elapsed_ms = int((time.time() - t_start) * 1000)
        print(f"[DDG Engine] ⏱ All Probes & DDG searches completed in {discovery_elapsed_ms}ms", flush=True)

    # 4. Ingest and Score Candidates
    candidates_map: Dict[str, Dict[str, Any]] = {}

    def make_cand_key(p_plat: str, p_handle: str) -> str:
        h = p_handle.lstrip("@").strip().lower()
        if p_plat == "facebook":
            return f"facebook:{h.replace('.', '')}"
        return f"{p_plat}:{h}"

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
            resolved_name,
            resolved_location,
            gh_username,
            company_name,
        )
        if score >= 15:
            k = make_cand_key(plat, h_clean)
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
            if k not in candidates_map or score > candidates_map[k]["score"]:
                candidates_map[k] = cand_obj

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
            k = make_cand_key(plat, h_clean)

            score, reasons, sub_scores, evidence = score_candidate(
                parsed,
                title,
                snippet,
                all_variations,
                resolved_name,
                resolved_location,
                gh_username,
                company_name,
            )
            if score < 15:
                continue

            display_name = clean_display_name(title, h_clean, plat, resolved_name)
            bio_clean = clean_bio_snippet(snippet, plat, h_clean)

            cand_obj = {
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
                "discovery_method": "ddg_search"
            }
            if k not in candidates_map or score > candidates_map[k]["score"]:
                candidates_map[k] = cand_obj

    # 5. Concurrent Avatar Extraction & Deduplication (Parallelized for LinkedIn & Facebook)
    linkedin_cands = [c for c in candidates_map.values() if not c.get("avatar_url") and c["platform"] == "linkedin"]
    facebook_cands = [c for c in candidates_map.values() if not c.get("avatar_url") and c["platform"] == "facebook"]

    if linkedin_cands or facebook_cands:
        async with httpx.AsyncClient(timeout=3.0, verify=False) as av_client:
            tasks = []
            async def fetch_single_li(c_obj):
                try:
                    av, canon_url = await fetch_linkedin_candidate_avatar(c_obj["url"], av_client)
                    if av: c_obj["avatar_url"] = av
                    if canon_url and "linkedin.com/in/" in canon_url:
                        m_slug = re.search(r"linkedin\.com/in/([a-zA-Z0-9_/%-]+)", canon_url, re.IGNORECASE)
                        if m_slug:
                            canon_slug = m_slug.group(1).split("?")[0].rstrip("/")
                            if canon_slug and canon_slug.lower() not in ("dir", "pub", "feed"):
                                c_obj["handle"] = f"@{canon_slug}"
                                c_obj["url"] = f"https://www.linkedin.com/in/{canon_slug}"
                except Exception:
                    pass

            async def fetch_single_fb(c_obj):
                try:
                    av = await fetch_facebook_candidate_avatar(c_obj["url"], av_client)
                    if av: c_obj["avatar_url"] = av
                except Exception:
                    pass

            for c in linkedin_cands[:8]:
                tasks.append(fetch_single_li(c))
            for c in facebook_cands[:6]:
                tasks.append(fetch_single_fb(c))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    # Post-enrichment deduplication pass by platform and handle
    merged: Dict[str, Dict[str, Any]] = {}
    for c in candidates_map.values():
        h = c["handle"].lstrip("@").lower().strip()
        p = c["platform"]
        # Normalize Facebook dot-variations in handle
        p_key = f"facebook:{h.replace('.', '')}" if p == "facebook" else f"{p}:{h}"

        if p_key not in merged or c["score"] > merged[p_key]["score"]:
            merged[p_key] = c
        elif c.get("avatar_url") and not merged[p_key].get("avatar_url"):
            merged[p_key]["avatar_url"] = c["avatar_url"]

    all_cands = sorted(merged.values(), key=lambda x: -x["score"])
    by_platform = {
        "linkedin": [c for c in all_cands if c["platform"] == "linkedin"],
        "instagram": [c for c in all_cands if c["platform"] == "instagram"],
        "twitter": [c for c in all_cands if c["platform"] == "twitter"],
        "facebook": [c for c in all_cands if c["platform"] == "facebook"],
        "tiktok": [c for c in all_cands if c["platform"] == "tiktok"],
        "pinterest": [c for c in all_cands if c["platform"] == "pinterest"],
        "github": [c for c in all_cands if c["platform"] == "github"],
    }
    print(f"[DDG Engine] ✓ Discovery complete! Total unique ranked candidates: {len(all_cands)}", flush=True)
    return all_cands[:40], by_platform


# ── 4. FULL REVERSE LOOKUP USING DDG ENGINE ─────────────────────────────────
async def execute_full_lookup_ddg(email: str) -> Dict[str, Any]:
    """Execute complete reverse email lookup replacing SearXNG with the DDG Engine in a single pass."""
    import lookup_engine
    t_start = time.time()
    orig_social = lookup_engine.search_social_candidates
    lookup_engine.search_social_candidates = search_social_candidates_ddg
    try:
        result = await run_lookup(email)
        result["query_time_ms"] = int((time.time() - t_start) * 1000)
        return result
    finally:
        lookup_engine.search_social_candidates = orig_social


# ── 5. STANDALONE FASTAPI TEST SERVER (PORT 8001) ───────────────────────────
def start_standalone_frontend_server(port: int = 8001):
    """Start standalone test server mounting the existing frontend UI on port 8001."""
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from pydantic import BaseModel

    class StandaloneLookupRequest(BaseModel):
        email: str
        force_refresh: Optional[bool] = False

    app = FastAPI(title="EmailLookup - DDG Proxy Test Server", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    frontend_dir = str(BASE_DIR / "frontend")
    if os.path.isdir(frontend_dir):
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    @app.get("/favicon.ico")
    async def serve_fav():
        return FileResponse(os.path.join(frontend_dir, "favicon.svg"), media_type="image/svg+xml")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "engine": "DuckDuckGo Proxy Pool", "proxies_loaded": len(proxy_pool.get_clean_ips())}

    @app.get("/api/port-check")
    async def port_check():
        return {"port25_available": False, "message": "DDG Test Server Mode"}

    @app.post("/api/cache/invalidate")
    async def invalidate_cache(req: StandaloneLookupRequest):
        return {"success": True, "email": req.email, "message": "DDG Test Server: Live lookup forced."}

    @app.post("/api/lookup")
    async def lookup_endpoint(req: StandaloneLookupRequest):
        email = req.email.strip().lower()
        if not email or "@" not in email:
            raise HTTPException(status_code=422, detail="Invalid email address.")
        try:
            res = await execute_full_lookup_ddg(email)
            return res
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

    print(f"\n" + "=" * 70)
    print(f"🚀 DuckDuckGo Proxy Test Server is running at: http://localhost:{port}")
    print(f"   Frontend UI:  http://localhost:{port}/")
    print(f"   Proxy Pool:   {len(proxy_pool.get_clean_ips())} Active Clean Residential Proxies Loaded")
    print(f"   SearXNG:      BYPASSED (100% DuckDuckGo + Direct Probes)")
    print(f"=" * 70 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


# ── 6. CLI ENTRY POINT ──────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1 and ("--server" in sys.argv or "-s" in sys.argv):
        port_num = 8001
        for i, arg in enumerate(sys.argv):
            if arg in ("--port", "-p") and i + 1 < len(sys.argv):
                port_num = int(sys.argv[i + 1])
        start_standalone_frontend_server(port=port_num)
    else:
        test_email = sys.argv[1] if len(sys.argv) > 1 else "sarah.jenkins.hr@gmail.com"
        print(f"\n[CLI Mode] Testing DuckDuckGo Proxy Engine on email: {test_email}")
        result = asyncio.run(execute_full_lookup_ddg(test_email))

        print("\n" + "=" * 60)
        print("LOOKUP RESULTS SUMMARY (via DuckDuckGo Proxy Engine)")
        print("=" * 60)
        print(f"Target Email:   {result.get('email')}")
        print(f"Resolved Name:  {result.get('person', {}).get('name')}")
        print(f"Total Time:     {result.get('query_time_ms')}ms")
        print(f"Candidates:     {len(result.get('social_candidates', []))}")
        print(f"By Platform:    { {k: len(v) for k, v in result.get('social_candidates_by_platform', {}).items()} }")

        top_candidates = result.get("social_candidates", [])[:5]
        if top_candidates:
            print("\nTop Discovered Profiles:")
            for c in top_candidates:
                print(f"  [{c['platform'].upper():9}] {c['handle']:25} | Score: {c['score']}% | {c['name']}")
        print("=" * 60 + "\n")
