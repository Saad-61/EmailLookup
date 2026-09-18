"""
social_finder.py
----------------
Discovers and scores candidate accounts on Twitter/X, Instagram, and Facebook
using platform-targeted search queries, handle permutations, OpenGraph avatar
extraction, and multi-factor corroboration (name, handle, city/country).
"""

import asyncio
import os
import re
from typing import List, Optional, Dict, Any, Tuple
import httpx
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


def generate_handle_variations(
    email: str,
    name: Optional[str] = None,
    gh_username: Optional[str] = None,
) -> Tuple[List[str], List[str]]:
    """
    Generate prioritized handle variations from email local-part,
    name, and verified GitHub username.
    Returns (specific_handles, stem_handles).
    e.g. sharafat_760@hotmail.com -> specific: ['sharafat_760', 'sharafat760'], stem: ['sharafat']
         rdameesha@gmail.com     -> specific: ['rdameesha'], stem: ['dameesha']
         atisamhameed6@gmail.com -> specific: ['atisamhameed6'], stem: ['atisamhameed', 'hameedatisam', 'atisam', 'hameed']
    """
    specific = []
    stems = []
    local = email.split("@")[0].lower().strip() if "@" in email else ""

    if local:
        specific.append(local)
        clean_no_sep = re.sub(r"[._+-]", "", local)
        if clean_no_sep != local:
            specific.append(clean_no_sep)
        clean_no_num = re.sub(r"\d+", "", clean_no_sep)
        if len(clean_no_num) >= 4 and clean_no_num != clean_no_sep:
            stems.append(clean_no_num)

        # Chunks separated by delimiters (e.g. sharafat.contentarcade -> sharafat)
        chunks = [c for c in re.split(r"[._+-]", local) if len(c) >= 3 and not c.isdigit()]
        for c in chunks:
            c_no_num = re.sub(r"\d+", "", c)
            if len(c_no_num) >= 3:
                stems.append(c_no_num)

        if len(chunks) >= 2:
            stems.append("".join(chunks))
            stems.append(f"{chunks[1]}{chunks[0]}")
            stems.append(f"{chunks[0]}.{chunks[1]}")
            stems.append(f"{chunks[0]}_{chunks[1]}")
            stems.append(f"{chunks[1]}.{chunks[0]}")
            stems.append(f"{chunks[1]}_{chunks[0]}")

    if gh_username:
        gh_clean = gh_username.lower().strip()
        if gh_clean not in specific:
            specific.append(gh_clean)
        gh_no_sep = re.sub(r"[._+-]", "", gh_clean)
        if gh_no_sep != gh_clean and gh_no_sep not in specific:
            specific.append(gh_no_sep)

    # If no name provided, attempt to infer from unsegmented local part (e.g. atisamhameed -> Atisam Hameed)
    if not name and local:
        clean_local = re.sub(r"\d+", "", local).strip("._-")
        try:
            try:
                from backend.lookup_engine import split_concatenated_name
            except ImportError:
                from lookup_engine import split_concatenated_name
            inferred = split_concatenated_name(clean_local)
            if inferred:
                name = inferred
        except Exception:
            pass

    if name:
        parts = [p.lower() for p in re.findall(r"[a-zA-Z]+", name)]
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            concat = "".join(parts)
            rev_concat = f"{last}{first}"
            # Both forward and reverse full-name permutations and tokens are highest priority stems
            for term in (concat, rev_concat, first, last, f"{first}_{last}", f"{last}_{first}", f"{first}.{last}", f"{last}.{first}"):
                if term not in specific and term not in stems:
                    stems.append(term)
        elif len(parts) == 1:
            if parts[0] not in specific and parts[0] not in stems:
                stems.append(parts[0])

    # Strip single-letter initial prefix only (e.g. rdameesha -> dameesha, msharafat -> sharafat)
    # Avoid 2-letter stripping which degrades dameesha into ameesha (causes Bollywood actress pollution)
    if local:
        clean_no_num = re.sub(r"\d+", "", re.sub(r"[._+-]", "", local))
        if len(clean_no_num) >= 5:
            prefix_stripped = clean_no_num[1:]
            if len(prefix_stripped) >= 4 and prefix_stripped not in stems:
                stems.append(prefix_stripped)

    generic = {
        "admin", "info", "support", "sales", "contact", "help",
        "billing", "team", "hello", "official", "mail", "user", "test",
        "contentarcade", "gmail", "yahoo", "hotmail", "outlook", "fast",
    }
    filtered_specific = [v for v in dict.fromkeys(specific) if len(v) >= 3 and v not in generic]
    filtered_stems = [v for v in dict.fromkeys(stems) if len(v) >= 3 and v not in generic]
    return filtered_specific, filtered_stems


def expand_social_probe_handles(
    specific_handles: List[str],
    stem_handles: List[str],
) -> List[str]:
    """
    Generate targeted handle permutations for direct social probing (Instagram, Twitter).
    Prioritizes base clean handles (including reverse names) before secondary suffix variants.
    """
    probes = []
    # 1. Base clean handles first (all specific + all top stems)
    for h in (specific_handles + stem_handles):
        clean = h.strip().lower()
        if clean and clean not in probes and len(clean) >= 3:
            probes.append(clean)

    # 2. Pick key seeds: specific handles + single-token/short stems (first name, last name, clean stem)
    seeds = []
    for s in specific_handles:
        clean_s = s.strip().lower()
        if clean_s and clean_s not in seeds:
            seeds.append(clean_s)
    for st in stem_handles:
        clean_st = st.strip().lower()
        if len(clean_st) <= 10 and clean_st not in seeds:
            seeds.append(clean_st)

    for s in seeds[:4]:
        clean = s.strip("._")
        if len(clean) >= 3:
            for v in [f"_{clean}", f"{clean}_", f"{clean}_09", f"{clean}.v2", f"{clean}.v3", f"{clean}_v2", f"{clean}_01"]:
                if v not in probes:
                    probes.append(v)

    return probes


def parse_social_url(url: str) -> Optional[Dict[str, str]]:
    """
    Parse a social media URL into platform, canonical profile URL, and handle.
    Rejects status, post, reel, direct, explore, and policy links.
    """
    if not url:
        return None

    clean = url.split("?")[0].rstrip("/")

    # Twitter / X
    tw_match = re.search(
        r"https?://(?:[a-z0-9-]+\.)?(?:x\.com|twitter\.com)/([a-zA-Z0-9_]{1,25})$",
        clean,
        re.IGNORECASE,
    )
    if tw_match:
        handle = tw_match.group(1)
        if handle.lower() not in (
            "home", "explore", "search", "notifications", "messages",
            "settings", "i", "privacy", "tos", "intent", "all",
        ):
            return {
                "platform": "twitter",
                "platform_label": "X / Twitter",
                "handle": handle,
                "url": f"https://x.com/{handle}",
            }

    # Instagram
    ig_match = re.search(
        r"https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.]{1,30})/?$",
        clean,
        re.IGNORECASE,
    )
    if ig_match:
        handle = ig_match.group(1)
        if handle.lower() not in (
            "p", "reel", "reels", "stories", "explore", "direct",
            "accounts", "about", "developer", "legal",
        ):
            return {
                "platform": "instagram",
                "platform_label": "Instagram",
                "handle": handle,
                "url": f"https://www.instagram.com/{handle}",
            }

    # Facebook People format (e.g. facebook.com/people/Name/100091835441662/)
    fb_people_match = re.search(
        r"https?://(?:[a-z0-9-]+\.)?facebook\.com/people/([^/?#]+)/(\d+)",
        clean,
        re.IGNORECASE,
    )
    if fb_people_match:
        p_name = fb_people_match.group(1).replace("-", " ")
        p_id = fb_people_match.group(2)
        return {
            "platform": "facebook",
            "platform_label": "Facebook",
            "handle": p_name,
            "url": f"https://www.facebook.com/people/{fb_people_match.group(1)}/{p_id}/",
        }

    # Facebook standard username format (e.g. facebook.com/saad.asif.752861/)
    fb_match = re.search(
        r"https?://(?:[a-z0-9-]+\.)?facebook\.com/([a-zA-Z0-9_.]{3,50})/?$",
        clean,
        re.IGNORECASE,
    )
    if fb_match:
        handle = fb_match.group(1)
        if handle.lower() not in (
            "sharer", "share", "login", "recover", "help", "policies",
            "privacy", "pages", "groups", "events", "watch", "photo",
            "photos", "video", "videos", "reel", "reels", "posts", "stories",
        ):
            return {
                "platform": "facebook",
                "platform_label": "Facebook",
                "handle": handle,
                "url": f"https://www.facebook.com/{handle}",
            }

    return None


def extract_name_from_title(title: str, platform: str) -> Optional[str]:
    """Extract display name from organic title."""
    if not title:
        return None
    t = title.strip()
    t = re.sub(r"\s*[-–|•]\s*(Instagram|X|Twitter|Facebook|Photos and videos).*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\(?@[a-zA-Z0-9_.]+\)?.*$", "", t)
    t = re.sub(r"^(Photo|Reel|Video|Post)\s+by\s+", "", t, flags=re.IGNORECASE)
    t = t.strip()
    return t if (t and len(t) >= 2) else None


def score_candidate(
    platform_info: dict,
    title: str,
    snippet: str,
    all_variations: List[str],
    resolved_name: Optional[str],
    resolved_location: Optional[str],
    gh_username: Optional[str] = None,
) -> Tuple[int, List[str]]:
    """
    Score a social candidate from 0 to 95 based on handle, name, and location anchors.
    Returns (score, match_reasons).
    """
    score = 0
    reasons = []
    handle = platform_info["handle"].lower()
    title_l = (title or "").lower()
    snippet_l = (snippet or "").lower()
    combined_text = f"{title_l} {snippet_l}"

    handle_norm = re.sub(r"[._-]", "", handle)

    # 0. Verified GitHub handle corroboration
    if gh_username:
        gh_clean = gh_username.lower().strip()
        gh_norm = re.sub(r"[._-]", "", gh_clean)
        if handle == gh_clean or handle_norm == gh_norm:
            score += 85
            reasons.append(f"Direct match with verified GitHub handle (@{gh_username})")
        elif len(gh_norm) >= 4 and (gh_norm in handle_norm or handle_norm in gh_norm):
            score += 70
            reasons.append(f"Stem match with verified GitHub handle (@{gh_username})")
    # 0b. Reverse full-name handle corroboration (e.g. Hameed Atisam -> @hameedatisam, @hameed.atisam)
    if resolved_name and len(resolved_name.split()) >= 2:
        name_parts = [p.lower() for p in resolved_name.split() if len(p) >= 2]
        first, last = name_parts[0], name_parts[-1]
        rev_concat = f"{last}{first}"
        if handle in (rev_concat, f"{last}.{first}", f"{last}_{first}") or handle_norm == rev_concat:
            score += 80
            reasons.append(f"Reverse full-name handle match (@{handle})")

    for v in all_variations:
        vl = v.lower()
        vl_norm = re.sub(r"[._-]", "", vl)
        if handle == vl or handle_norm == vl_norm:
            if any(c.isdigit() for c in vl) or len(vl) >= 7:
                score += 75
                reasons.append(f"Distinctive exact handle match (@{handle})")
            else:
                score += 55
                reasons.append(f"Exact handle match (@{handle})")
            break
        elif len(vl_norm) >= 4 and (vl_norm in handle_norm or handle_norm in vl_norm):
            has_suffix = bool(re.search(r"(\.v\d+|\.official|_\d+|\d+$)", handle))
            if len(vl_norm) >= 5:
                score += 55 if has_suffix else 50
                reasons.append(f"Root stem match (@{handle})")
            else:
                score += 35
                reasons.append(f"Handle variation match (@{handle})")
            break

    # 2. Name match (Supports normal and inverted order, e.g. "Atisam Hameed" or "Hameed Atisam")
    target_name = resolved_name
    if not target_name:
        for v in all_variations:
            if "." in v or "_" in v:
                v_parts = re.split(r"[._]", v)
                if len(v_parts) == 2 and len(v_parts[0]) >= 3 and len(v_parts[1]) >= 3:
                    if v_parts[0] in title_l and v_parts[1] in title_l:
                        target_name = f"{v_parts[0].title()} {v_parts[1].title()}"
                        break

    if target_name and len(target_name.split()) >= 2:
        name_parts = [p.lower() for p in target_name.split() if len(p) >= 2]
        first, last = name_parts[0], name_parts[-1]
        rev_name = f"{last} {first}".lower()
        if target_name.lower() in title_l or rev_name in title_l:
            score += 40
            reasons.append(f"Full name match in title ({target_name})")
        elif first in title_l and last in title_l:
            score += 35
            reasons.append(f"First and last name in title ({first.title()} {last.title()})")
        elif rev_name in combined_text or target_name.lower() in combined_text:
            score += 30
            reasons.append(f"Full name match in bio ({target_name})")
        elif (first in combined_text and last in combined_text):
            score += 25
            reasons.append(f"Name corroborated in bio ({first.title()} {last.title()})")

    # 3. Location match
    if resolved_location:
        loc_tokens = [tok.strip().lower() for tok in re.split(r"[,/]", resolved_location) if len(tok.strip()) >= 3]
        matched_locs = [l for l in loc_tokens if l in combined_text]
        if matched_locs:
            score += 20
            reasons.append(f"Location match ({', '.join([l.title() for l in matched_locs])})")

    score = min(score, 95)
    return score, reasons


async def fetch_social_avatar(
    url: str,
    platform: str,
    handle: str,
    client: httpx.AsyncClient,
) -> Optional[str]:
    """
    Fetch real user avatar URL from OpenGraph metadata or unavatar.
    Returns direct image URL or None.
    """
    if not url:
        return None

    # Twitter: unavatar is instant and clean
    if platform == "twitter" and handle:
        clean_handle = handle.lstrip("@")
        return f"https://unavatar.io/x/{clean_handle}"

    # Instagram & Facebook: fetch og:image with crawler User-Agent
    try:
        headers = {
            "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = await client.get(url, headers=headers, timeout=2.5, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            og_meta = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
            if og_meta and og_meta.get("content"):
                c_url = og_meta["content"]
                # Reject generic platform branding images
                if not any(k in c_url.lower() for k in ("fb_icon", "logo", "default", "static.xx.fbcdn")):
                    return c_url
    except Exception:
        pass

    return None


async def probe_instagram_profile(
    handle: str,
    client: httpx.AsyncClient,
) -> Optional[Dict[str, Any]]:
    """
    Directly probe an Instagram profile using facebookexternalhit crawler User-Agent.
    Extracts real display name, bio snippet, and authentic profile image directly
    from OpenGraph metadata without consuming search engine quota.
    """
    if not handle or len(handle) < 3:
        return None
    clean_handle = handle.lower().lstrip("@").strip()
    if clean_handle in ("p", "reel", "reels", "explore", "direct", "accounts", "about", "developer", "legal"):
        return None

    try:
        url = f"https://www.instagram.com/{clean_handle}/"
        headers = {
            "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = await client.get(url, headers=headers, timeout=5.5, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            og_title = (soup.find("meta", property="og:title") or {}).get("content", "")
            if not og_title:
                og_title = soup.title.string if soup.title else ""

            # Check if this is a genuine user profile
            if not og_title or f"@{clean_handle}" not in og_title.lower():
                return None

            og_desc = (soup.find("meta", property="og:description") or {}).get("content", "")
            og_image = (soup.find("meta", property="og:image") or {}).get("content", "")
            if og_image and any(k in og_image.lower() for k in ("fb_icon", "logo", "default", "static.xx.fbcdn")):
                og_image = None

            name = extract_name_from_title(og_title, "instagram") or clean_handle
            return {
                "platform": "instagram",
                "platform_label": "Instagram",
                "handle": clean_handle,
                "name": name,
                "url": f"https://www.instagram.com/{clean_handle}",
                "avatar_url": og_image,
                "snippet": og_desc or f"Instagram account @{clean_handle}",
                "title": og_title,
            }
    except Exception:
        pass
    return None


async def search_social_candidates(
    email: str,
    resolved_name: Optional[str],
    resolved_location: Optional[str],
    gh_username: Optional[str],
    client: Optional[httpx.AsyncClient] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """
    Run platform-targeted searches across Instagram, X/Twitter, and Facebook.
    Returns (all_sorted_candidates, candidates_by_platform).
    """
    if client is None or getattr(client, "is_closed", False):
        async with httpx.AsyncClient(timeout=8.0) as local_client:
            return await search_social_candidates(
                email=email,
                resolved_name=resolved_name,
                resolved_location=resolved_location,
                gh_username=gh_username,
                client=local_client,
            )

    raw_serper = os.getenv("SERPER_API_KEY", "")
    if not raw_serper:
        print("[Social Discovery] ⚠️ SERPER_API_KEY not configured. Skipping candidate discovery.", flush=True)
        return [], {"instagram": [], "twitter": [], "facebook": []}

    specific_handles, stem_handles = generate_handle_variations(email, resolved_name, gh_username)
    all_variations = specific_handles + stem_handles
    if not all_variations and not resolved_name:
        return [], {"instagram": [], "twitter": [], "facebook": []}

    print(f"\n[Social Discovery] ───────────────────────────────────────────────────", flush=True)
    print(f"[Social Discovery] Initiating social candidate discovery for: {email}", flush=True)
    print(f"[Social Discovery] Specific handles: {specific_handles} | Stems: {stem_handles}", flush=True)
    if resolved_name:
        print(f"[Social Discovery] Anchor name: '{resolved_name}' | Location: '{resolved_location or 'N/A'}'", flush=True)

    headers = {"X-API-KEY": raw_serper.strip(), "Content-Type": "application/json"}

    # Combine specific handles and stem handles, excluding dots/symbols to keep Google SERP queries clean
    clean_query_handles = []
    for h in (specific_handles[:2] + stem_handles[:6]):
        clean_h = re.sub(r"[._+-]", "", h)
        if clean_h and clean_h not in clean_query_handles and len(clean_h) >= 3:
            clean_query_handles.append(clean_h)

    # 1. Direct Instagram Profile Probes using expanded permutations (e.g. _momina0, dameesha_09, ahtisham.v2, ahtisham.v3, hameedatisam)
    handles_to_probe = expand_social_probe_handles(specific_handles, stem_handles)[:28]
    print(f"[Social Discovery] Direct Instagram probes ({len(handles_to_probe)}): {handles_to_probe[:10]}...", flush=True)
    ig_probe_task = asyncio.gather(*[probe_instagram_profile(h, client) for h in handles_to_probe])

    # 2. Instagram Query (unquoted terms allow prefix / suffix matches like dameesha_09 or ahtisham.v2)
    ig_terms = " OR ".join(clean_query_handles[:6]) if clean_query_handles else ""
    ig_q = f"site:instagram.com ({ig_terms})" if ig_terms else ""
    if resolved_name and len(resolved_name.split()) >= 2:
        ig_q = f'{ig_q} OR (site:instagram.com "{resolved_name}")' if ig_q else f'site:instagram.com "{resolved_name}"'

    # 3. Twitter / X Query
    tw_terms = " OR ".join(clean_query_handles[:6]) if clean_query_handles else ""
    tw_q = f"site:x.com ({tw_terms})" if tw_terms else ""
    if resolved_name and len(resolved_name.split()) >= 2:
        tw_q = f'{tw_q} OR (site:x.com "{resolved_name}")' if tw_q else f'site:x.com "{resolved_name}"'

    # 4. Facebook Query
    fb_terms = []
    if resolved_name and len(resolved_name.split()) >= 2:
        fb_terms.append(f'"{resolved_name}"')
    for h in clean_query_handles[:3]:
        fb_terms.append(f'"{h}"')
    fb_q = f'(site:facebook.com OR site:facebook.com/people) ({" OR ".join(fb_terms)})' if fb_terms else ""

    queries = [("instagram", ig_q), ("twitter", tw_q), ("facebook", fb_q)]

    # Additional targeted queries for dot/version/number patterns (e.g. ahtisham.v2, ahtisham.v3, dameesha_09)
    pattern_handles = [h for h in handles_to_probe if any(pat in h for pat in (".v", "_v", "_0", "_1", "_2"))][:6]
    if pattern_handles:
        pattern_terms = " OR ".join([f'"{h}"' for h in pattern_handles])
        queries.append(("instagram", f"site:instagram.com ({pattern_terms})"))
        queries.append(("twitter", f"site:x.com ({pattern_terms})"))
        queries.append(("facebook", f'(site:facebook.com OR site:facebook.com/people) ({pattern_terms})'))

    active_queries = [(p, q) for p, q in queries if q]

    for p, q in active_queries:
        print(f"[Social Discovery] Sending {p.upper()} query: {q}", flush=True)

    async def run_serper_q(platform_tag: str, q_str: str):
        # Strategy 1: Serper.dev
        if raw_serper:
            try:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    headers=headers,
                    json={"q": q_str, "num": 10},
                    timeout=6.0,
                )
                org = resp.json().get("organic", []) if resp.status_code == 200 else []
                print(f"[Social Discovery] Serper {platform_tag.upper()} -> HTTP {resp.status_code}, {len(org)} organic items", flush=True)
                if org:
                    return platform_tag, org
                elif resp.status_code != 200:
                    print(f"[Social Discovery] [-] {platform_tag} Serper status={resp.status_code}: {resp.text[:120]}", flush=True)
            except Exception as e:
                print(f"[Social Discovery] [-] {platform_tag} Serper error: {e}", flush=True)

        # Strategy 2: Exa.ai semantic search fallback
        raw_exa = os.getenv("EXA_API_KEY", "")
        if raw_exa:
            try:
                domain_map = {
                    "instagram": ["instagram.com"],
                    "twitter": ["x.com", "twitter.com"],
                    "facebook": ["facebook.com"],
                }
                exa_payload = {
                    "query": q_str,
                    "numResults": 8,
                    "includeDomains": domain_map.get(platform_tag, []),
                }
                exa_resp = await client.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": raw_exa.strip(), "content-type": "application/json"},
                    json=exa_payload,
                    timeout=5.0,
                )
                if exa_resp.status_code == 200:
                    exa_items = []
                    for r in exa_resp.json().get("results", []):
                        exa_items.append({
                            "link": r.get("url", ""),
                            "title": r.get("title", ""),
                            "snippet": r.get("text", ""),
                        })
                    if exa_items:
                        print(f"[Social Discovery] ✓ Retrieved {len(exa_items)} {platform_tag.upper()} result(s) via Exa.ai fallback", flush=True)
                        return platform_tag, exa_items
            except Exception as e:
                print(f"[Social Discovery] ✗ {platform_tag} Exa fallback error: {e}", flush=True)

        return platform_tag, []

    serper_task = asyncio.gather(*[run_serper_q(p, q) for p, q in active_queries])
    serper_results, probed_ig_results = await asyncio.gather(serper_task, ig_probe_task)

    candidates_map: Dict[str, Dict[str, Any]] = {}

    # Process direct probed Instagram profiles
    for p_cand in probed_ig_results:
        if not p_cand:
            continue
        h_clean = p_cand["handle"].lstrip("@")
        parsed = {
            "platform": "instagram",
            "platform_label": "Instagram",
            "handle": h_clean,
            "url": p_cand["url"],
        }
        score, reasons = score_candidate(
            parsed, p_cand.get("title", ""), p_cand.get("snippet", ""), all_variations, resolved_name, resolved_location, gh_username
        )
        if score >= 25:
            dedup_key = f"instagram:{h_clean.lower()}"
            candidates_map[dedup_key] = {
                "platform": "instagram",
                "platform_label": "Instagram",
                "handle": f"@{h_clean}",
                "name": p_cand.get("name") or h_clean,
                "url": p_cand["url"],
                "snippet": p_cand.get("snippet", ""),
                "score": score,
                "confidence_badge": "",
                "confidence_level": "strong" if score >= 70 else "potential",
                "reasons": reasons,
                "avatar_url": p_cand.get("avatar_url"),
            }
            print(f"[Social Discovery] [+] Probed Instagram handle confirmed: @{h_clean} (score={score}%, name='{p_cand.get('name')}')", flush=True)

    for platform_tag, items in serper_results:
        found_on_platform = 0
        for item in items:
            link = item.get("link", "")
            title = item.get("title", "")
            snippet = item.get("snippet", "")

            parsed = parse_social_url(link)
            if not parsed:
                continue

            platform = parsed["platform"]
            handle = parsed["handle"]
            dedup_key = f"{platform}:{handle.lower()}"

            score, reasons = score_candidate(
                parsed, title, snippet, all_variations, resolved_name, resolved_location, gh_username
            )

            # Lowered threshold to >= 25 to capture viable candidates across all platforms
            if score < 25:
                continue

            display_name = extract_name_from_title(title, platform) or handle

            cand_obj = {
                "platform": platform,
                "platform_label": parsed["platform_label"],
                "handle": f"@{handle}" if not handle.startswith("@") else handle,
                "name": display_name,
                "url": parsed["url"],
                "snippet": snippet,
                "score": score,
                "confidence_badge": "",
                "confidence_level": "strong" if score >= 70 else "potential",
                "reasons": reasons,
                "avatar_url": None,
            }

            if dedup_key not in candidates_map or candidates_map[dedup_key]["score"] < score:
                candidates_map[dedup_key] = cand_obj
                found_on_platform += 1

        print(f"[Social Discovery] ✓ Discovered {found_on_platform} valid candidate(s) for {platform_tag.upper()}", flush=True)

    # Meta cross-pollination: probe Facebook discovered handles on Instagram if not yet probed
    fb_new_handles = []
    for platform_tag, items in serper_results:
        if platform_tag == "facebook":
            for it in items:
                parsed = parse_social_url(it.get("link", ""))
                if parsed and parsed["platform"] == "facebook":
                    h = parsed["handle"].lstrip("@").strip()
                    if h and h.lower() not in [x.lower() for x in handles_to_probe] and len(h) >= 3 and not any(ch in h for ch in " /?#"):
                        fb_new_handles.append(h)
    if fb_new_handles:
        fb_probe_res = await asyncio.gather(*[probe_instagram_profile(h, client) for h in fb_new_handles[:3]])
        for p_cand in fb_probe_res:
            if not p_cand:
                continue
            h_clean = p_cand["handle"].lstrip("@")
            parsed = {
                "platform": "instagram",
                "platform_label": "Instagram",
                "handle": h_clean,
                "url": p_cand["url"],
            }
            score, reasons = score_candidate(
                parsed, p_cand.get("title", ""), p_cand.get("snippet", ""), all_variations, resolved_name, resolved_location, gh_username
            )
            if score >= 25:
                dedup_key = f"instagram:{h_clean.lower()}"
                if dedup_key not in candidates_map:
                    candidates_map[dedup_key] = {
                        "platform": "instagram",
                        "platform_label": "Instagram",
                        "handle": f"@{h_clean}",
                        "name": p_cand.get("name") or h_clean,
                        "url": p_cand["url"],
                        "snippet": p_cand.get("snippet", ""),
                        "score": score,
                        "confidence_badge": "",
                        "confidence_level": "strong" if score >= 70 else "potential",
                        "reasons": reasons,
                        "avatar_url": p_cand.get("avatar_url"),
                    }
                    print(f"[Social Discovery] [+] Meta cross-pollinated IG handle confirmed: @{h_clean} (score={score}%)", flush=True)

    # Sort all candidates
    all_candidates = sorted(candidates_map.values(), key=lambda x: -x["score"])

    # Concurrently fetch avatars for top candidates (up to 8 candidates across platforms)
    async def resolve_avatar(c: dict):
        if c.get("avatar_url"):
            return
        try:
            av = await fetch_social_avatar(c["url"], c["platform"], c["handle"], client)
            if av:
                c["avatar_url"] = av
        except Exception:
            pass

    top_to_fetch = all_candidates[:12]
    if top_to_fetch:
        await asyncio.gather(*[resolve_avatar(c) for c in top_to_fetch])

    # Group by platform (up to 10 candidates per platform accordion)
    by_platform = {
        "instagram": [c for c in all_candidates if c["platform"] == "instagram"][:10],
        "twitter": [c for c in all_candidates if c["platform"] == "twitter"][:10],
        "facebook": [c for c in all_candidates if c["platform"] == "facebook"][:10],
    }

    total_count = sum(len(v) for v in by_platform.values())
    print(f"[Social Discovery] Total ranked candidates: {total_count} (IG: {len(by_platform['instagram'])}, X: {len(by_platform['twitter'])}, FB: {len(by_platform['facebook'])})", flush=True)
    if all_candidates:
        top = all_candidates[0]
        print(f"[Social Discovery] Top candidate: [{top['platform']}] {top['handle']} - {top['name']} ({top['score']}%)", flush=True)
    print(f"[Social Discovery] ───────────────────────────────────────────────────\n", flush=True)

    return all_candidates[:30], by_platform
