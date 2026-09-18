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

load_dotenv()


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
         ahtishamdilawar@gmail.com -> specific: ['ahtishamdilawar'], stem: ['ahtisham', 'dilawar', 'ahtisham.dilawar']
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

        # Strip 1 or 2 letter prefix (e.g. rdameesha -> dameesha, msharafat -> sharafat)
        if len(clean_no_num) >= 7:
            for prefix_len in (1, 2):
                prefix_stripped = clean_no_num[prefix_len:]
                if len(prefix_stripped) >= 4 and prefix_stripped not in stems:
                    stems.append(prefix_stripped)

        # Chunks separated by delimiters (e.g. sharafat.contentarcade -> sharafat)
        chunks = [c for c in re.split(r"[._+-]", local) if len(c) >= 3 and not c.isdigit()]
        for c in chunks:
            c_no_num = re.sub(r"\d+", "", c)
            if len(c_no_num) >= 3:
                stems.append(c_no_num)

        if len(chunks) >= 2:
            stems.append("".join(chunks))
            stems.append(f"{chunks[0]}.{chunks[1]}")
            stems.append(f"{chunks[0]}_{chunks[1]}")

    if gh_username:
        gh_clean = gh_username.lower().strip()
        if gh_clean not in specific:
            specific.append(gh_clean)
        gh_no_sep = re.sub(r"[._+-]", "", gh_clean)
        if gh_no_sep != gh_clean and gh_no_sep not in specific:
            specific.append(gh_no_sep)

    if name:
        parts = [p.lower() for p in re.findall(r"[a-zA-Z]+", name)]
        if len(parts) >= 2:
            concat = "".join(parts)
            if concat not in specific and concat not in stems:
                stems.append(concat)
            stems.append(f"{parts[0]}.{parts[-1]}")
            stems.append(f"{parts[0]}_{parts[-1]}")
            stems.append(parts[0])
            stems.append(parts[-1])

    generic = {
        "admin", "info", "support", "sales", "contact", "help",
        "billing", "team", "hello", "official", "mail", "user", "test",
        "contentarcade", "gmail", "yahoo", "hotmail", "outlook", "fast",
    }
    filtered_specific = [v for v in dict.fromkeys(specific) if len(v) >= 3 and v not in generic]
    filtered_stems = [v for v in dict.fromkeys(stems) if len(v) >= 3 and v not in generic]
    return filtered_specific, filtered_stems


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

    # 1. Handle match
    handle_norm = re.sub(r"[._-]", "", handle)
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
            score += 35
            reasons.append(f"Handle variation match (@{handle})")
            break

    # 2. Name match
    if resolved_name and len(resolved_name.split()) >= 2:
        name_parts = [p.lower() for p in resolved_name.split() if len(p) >= 2]
        first, last = name_parts[0], name_parts[-1]
        if resolved_name.lower() in title_l:
            score += 35
            reasons.append(f"Full name match ({resolved_name})")
        elif first in title_l and last in title_l:
            score += 30
            reasons.append(f"Name match ({first.title()} {last.title()})")
        elif first in combined_text and last in combined_text:
            score += 20
            reasons.append(f"Name corroborated in bio")

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

    # 1. Instagram Query
    ig_handles = (specific_handles[:3] if specific_handles else stem_handles[:2])
    ig_terms = " OR ".join([f'"{h}"' for h in ig_handles]) if ig_handles else ""
    ig_q = f"site:instagram.com ({ig_terms})" if ig_terms else ""
    if resolved_name and len(resolved_name.split()) >= 2:
        ig_q = f'{ig_q} OR (site:instagram.com "{resolved_name}")' if ig_q else f'site:instagram.com "{resolved_name}"'

    # 2. Twitter / X Query
    tw_handles = (specific_handles[:3] if specific_handles else stem_handles[:2])
    tw_terms = " OR ".join([f'"{h}"' for h in tw_handles]) if tw_handles else ""
    tw_q = f"site:x.com ({tw_terms})" if tw_terms else ""
    if resolved_name and len(resolved_name.split()) >= 2:
        tw_q = f'{tw_q} OR (site:x.com "{resolved_name}")' if tw_q else f'site:x.com "{resolved_name}"'

    # 3. Facebook Query
    fb_terms = []
    if resolved_name and len(resolved_name.split()) >= 2:
        fb_terms.append(f'"{resolved_name}"')
    if specific_handles:
        fb_terms.append(f'"{specific_handles[0]}"')
    elif stem_handles:
        fb_terms.append(f'"{stem_handles[0]}"')
    fb_q = f'(site:facebook.com OR site:facebook.com/people) ({" OR ".join(fb_terms)})' if fb_terms else ""

    queries = [("instagram", ig_q), ("twitter", tw_q), ("facebook", fb_q)]
    active_queries = [(p, q) for p, q in queries if q]

    for p, q in active_queries:
        print(f"[Social Discovery] Sending {p.upper()} query to Serper: {q}", flush=True)

    async def run_serper_q(platform_tag: str, q_str: str):
        try:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers=headers,
                json={"q": q_str, "num": 10},
                timeout=4.5,
            )
            if resp.status_code == 200:
                return platform_tag, resp.json().get("organic", [])
        except Exception as e:
            print(f"[Social Discovery] ✗ {platform_tag} query error: {e}", flush=True)
        return platform_tag, []

    serper_results = await asyncio.gather(*[run_serper_q(p, q) for p, q in active_queries])

    candidates_map: Dict[str, Dict[str, Any]] = {}

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
                parsed, title, snippet, all_variations, resolved_name, resolved_location
            )

            # Keep candidates meeting minimum threshold (>= 45 points)
            if score < 45:
                continue

            display_name = extract_name_from_title(title, platform) or handle

            conf_badge = f"★ {score}% Match"
            conf_level = "strong" if score >= 70 else "potential"

            cand_obj = {
                "platform": platform,
                "platform_label": parsed["platform_label"],
                "handle": f"@{handle}" if not handle.startswith("@") else handle,
                "name": display_name,
                "url": parsed["url"],
                "snippet": snippet,
                "score": score,
                "confidence_badge": conf_badge,
                "confidence_level": conf_level,
                "reasons": reasons,
                "avatar_url": None,
            }

            if dedup_key not in candidates_map or candidates_map[dedup_key]["score"] < score:
                candidates_map[dedup_key] = cand_obj
                found_on_platform += 1

        print(f"[Social Discovery] ✓ Discovered {found_on_platform} valid candidate(s) for {platform_tag.upper()}", flush=True)

    # Sort all candidates
    all_candidates = sorted(candidates_map.values(), key=lambda x: -x["score"])

    # Concurrently fetch avatars for top candidates (up to 2 per platform)
    async def resolve_avatar(c: dict):
        try:
            av = await fetch_social_avatar(c["url"], c["platform"], c["handle"], client)
            if av:
                c["avatar_url"] = av
        except Exception:
            pass

    top_to_fetch = all_candidates[:6]
    if top_to_fetch:
        await asyncio.gather(*[resolve_avatar(c) for c in top_to_fetch])

    # Group by platform
    by_platform = {
        "instagram": [c for c in all_candidates if c["platform"] == "instagram"][:4],
        "twitter": [c for c in all_candidates if c["platform"] == "twitter"][:4],
        "facebook": [c for c in all_candidates if c["platform"] == "facebook"][:4],
    }

    total_count = sum(len(v) for v in by_platform.values())
    print(f"[Social Discovery] Total ranked candidates: {total_count} (IG: {len(by_platform['instagram'])}, X: {len(by_platform['twitter'])}, FB: {len(by_platform['facebook'])})", flush=True)
    if all_candidates:
        top = all_candidates[0]
        print(f"[Social Discovery] Top candidate: [{top['platform']}] {top['handle']} - {top['name']} ({top['score']}%)", flush=True)
    print(f"[Social Discovery] ───────────────────────────────────────────────────\n", flush=True)

    return all_candidates[:12], by_platform
