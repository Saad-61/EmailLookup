"""
social_finder.py
----------------
Discovers and scores candidate accounts on Twitter/X, Instagram, and Facebook
using platform-targeted search queries, handle permutations, OpenGraph avatar
extraction, and multi-factor corroboration (name, handle, city/country).
"""

import asyncio
import os
import random
import re
import urllib.parse
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


def jaro_similarity(s1: str, s2: str) -> float:
    """Compute the standard Jaro similarity between two strings."""
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
    Accounts for common transliterations and minor spelling variations
    (e.g., Nouman vs Noman, Mohammad vs Muhammad, Dameesha vs Damesha).
    """
    s1_clean = (s1 or "").strip().lower()
    s2_clean = (s2 or "").strip().lower()
    if not s1_clean or not s2_clean:
        return 1.0 if s1_clean == s2_clean else 0.0
    if s1_clean == s2_clean:
        return 1.0

    j_sim = jaro_similarity(s1_clean, s2_clean)

    # Prefix match up to 4 characters
    prefix_len = 0
    for c1, c2 in zip(s1_clean[:4], s2_clean[:4]):
        if c1 == c2:
            prefix_len += 1
        else:
            break

    return min(1.0, j_sim + (prefix_len * prefix_weight * (1.0 - j_sim)))


def get_proxy_ips() -> List[str]:
    """Load proxy IP list dynamically from PROXY_IPS in .env."""
    raw = os.getenv("PROXY_IPS", "").strip()
    if raw:
        return [ip.strip() for ip in raw.split(",") if ip.strip()]
    return []


def get_random_proxy_url() -> Optional[str]:
    """Construct randomized proxy URL from PROXY_USERNAME, PROXY_PASSWORD, and PROXY_IPS."""
    ips = get_proxy_ips()
    if not ips:
        return None
    ip = random.choice(ips)
    user = os.getenv("PROXY_USERNAME", "").strip()
    pwd = os.getenv("PROXY_PASSWORD", "").strip()
    if user and pwd:
        return f"http://{user}:{pwd}@{ip}"
    return f"http://{ip}"




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
         atisamhameed6@gmail.com -> specific: ['atisamhameed6'], stem: ['atisamhameed', 'atisam', 'hameedatisam', 'hameed']
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
        if len(clean_no_num) >= 3:
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
            # Put forward and reverse permutations and tokens into stems
            for term in (f"{first}.{last}", f"{last}.{first}", f"{first}_{last}", f"{last}_{first}", rev_concat, concat, last):
                if term not in specific and term not in stems:
                    stems.append(term)
            # First name is top priority stem
            if first in stems:
                stems.remove(first)
            stems.insert(0, first)
        elif len(parts) == 1:
            first = parts[0]
            if first in stems:
                stems.remove(first)
            stems.insert(0, first)
    else:
        # Fallback: if single-letter initial prefix might exist (e.g. rdameesha -> dameesha), append as secondary stem
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
        "guy", "man", "boy", "girl", "profile", "account", "user", "dev",
    }
    filtered_specific = [v for v in dict.fromkeys(specific) if len(v) >= 3 and v not in generic]
    filtered_stems = [v for v in dict.fromkeys(stems) if len(v) >= 3 and v not in generic]
    return filtered_specific, filtered_stems


def expand_social_probe_handles(
    specific_handles: List[str],
    stem_handles: List[str],
    name: Optional[str] = None,
) -> List[str]:
    """
    Generate targeted handle permutations for direct social probing (Instagram, Twitter).
    Prioritizes clean number-stripped seeds (especially first name and clean stem)
    to generate valid handle variations such as _momina0, momina0_, dameesha_09, ahtisham.v2, etc.
    """
    probes = []
    # 1. Base clean handles first (all specific + all top stems)
    for h in (specific_handles + stem_handles):
        clean = h.strip().lower()
        if clean and clean not in probes and len(clean) >= 3:
            probes.append(clean)

    # 2. Pick clean base seeds WITHOUT numbers for suffix/prefix variations
    seeds = []
    if name:
        parts = [p.lower() for p in re.findall(r"[a-zA-Z]+", name)]
        if parts:
            first = parts[0]
            if len(first) >= 3 and first not in seeds:
                seeds.append(first)

    # Add single-word / stripped stems (e.g. rdameesha -> dameesha)
    for h in stem_handles:
        clean = re.sub(r"\d+", "", h).strip("._-").lower()
        if clean and len(clean) >= 3 and clean not in seeds and len(clean) <= 12:
            seeds.append(clean)

    for h in specific_handles:
        clean = re.sub(r"\d+", "", h).strip("._-").lower()
        if clean and len(clean) >= 3 and clean not in seeds:
            seeds.append(clean)

    variation_templates = [
        "{clean}.v2",
        "{clean}.v3",
        "{clean}_v2",
        "{clean}_v3",
        "{clean}_0",
        "_{clean}0",
        "{clean}0_",
        "{clean}0",
        "{clean}_09",
        "{clean}09",
        "mr.{clean}",
        "mr_{clean}",
        "{clean}_01",
        "{clean}_02",
        "_{clean}",
        "{clean}_",
        "_{clean}_",
        "{clean}_00",
    ]

    for s in seeds[:3]:
        for tmpl in variation_templates:
            v = tmpl.format(clean=s)
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

    # Instagram (supports subdomains including www, m, www-fallback, etc.)
    ig_match = re.search(
        r"https?://(?:[a-z0-9-]+\.)?instagram\.com/([a-zA-Z0-9_.]{1,30})/?$",
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

    # LinkedIn (e.g. linkedin.com/in/sarah-jenkins or linkedin.com/in/sarahjenkins/)
    if "linkedin.com/in/" in clean:
        li_match = re.search(
            r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/([a-zA-Z0-9_/%-]+)",
            clean,
            re.IGNORECASE,
        )
        if li_match:
            slug = li_match.group(1).split("?")[0].rstrip("/")
            if slug.lower() not in ("dir", "pub", "feed", "jobs", "company", "school", "pulse", "posts", "learning"):
                return {
                    "platform": "linkedin",
                    "platform_label": "LinkedIn",
                    "handle": slug,
                    "url": f"https://www.linkedin.com/in/{slug}",
                }

    # TikTok (e.g. tiktok.com/@username)
    tt_match = re.search(
        r"https?://(?:[a-z0-9-]+\.)?tiktok\.com/@([a-zA-Z0-9_.]{2,30})/?$",
        clean,
        re.IGNORECASE,
    )
    if tt_match:
        handle = tt_match.group(1)
        if handle.lower() not in ("explore", "direct", "trending", "about", "discover", "login", "live", "tag"):
            return {
                "platform": "tiktok",
                "platform_label": "TikTok",
                "handle": handle,
                "url": f"https://www.tiktok.com/@{handle}",
            }

    # Pinterest (e.g. pinterest.com/username/)
    pin_match = re.search(
        r"https?://(?:[a-z0-9-]+\.)?pinterest\.com/([a-zA-Z0-9_.]{2,30})/?$",
        clean,
        re.IGNORECASE,
    )
    if pin_match:
        handle = pin_match.group(1)
        if handle.lower() not in ("explore", "pin", "ideas", "business", "help", "about", "login", "today", "shop", "news"):
            return {
                "platform": "pinterest",
                "platform_label": "Pinterest",
                "handle": handle,
                "url": f"https://www.pinterest.com/{handle}/",
            }

    return None


def extract_name_from_title(title: str, platform: str) -> Optional[str]:
    """Extract display name from organic title cleanly without caption blobs or hashtags."""
    if not title:
        return None
    t = title.strip()

    # If 'Photo by Name' or 'Video by Name' or 'Instagram photo by Name' exists in full title, extract Name directly!
    by_match = re.search(r"(?:Photos?|Reels?|Videos?|Posts?)\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", t, flags=re.IGNORECASE)
    if by_match:
        cand_name = by_match.group(1).strip()
        if len(cand_name) >= 3 and cand_name.lower() not in ("instagram", "facebook", "twitter", "x"):
            return cand_name

    # If LinkedIn title: e.g. "Sarah Jenkins - Senior Recruiter - Stripe | LinkedIn"
    if platform == "linkedin" or "linkedin" in title.lower():
        t = re.sub(r"\s*\|\s*LinkedIn.*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*-\s*LinkedIn.*$", "", t, flags=re.IGNORECASE)
        segments = re.split(r"\s*[-–|•]\s*", t)
        if segments and len(segments[0].strip()) >= 2:
            name_part = segments[0].strip()
            name_part = re.sub(r",\s*(?:MBA|PHD|PMP|MD|CPA|ESQ|SHRM-[A-Z]+|BSc|MSc).*$", "", name_part, flags=re.IGNORECASE)
            return name_part.strip()

    # Check across segments for a clean name if first segment is a post caption (e.g. "Getting ready for • Instagram photo by Guy Kawasaki")
    segments = re.split(r"\s*[-–|•·]\s*", t)
    for seg in segments:
        seg_s = seg.strip()
        # Look for 'by Name' in segment
        b_m = re.search(r"\bby\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", seg_s, flags=re.IGNORECASE)
        if b_m:
            return b_m.group(1).strip()

    # Strip 'on Instagram: ...' or 'on Facebook: ...' or 'on X: ...'
    t = re.sub(r"\s+on\s+(?:Instagram|Twitter|X|Facebook)\s*:.*$", "", t, flags=re.IGNORECASE)
    # Strip after hyphen/bar/bullet platform names (e.g. " - Instagram photos and videos")
    t = re.sub(r"\s*[-–|•·]\s*(Instagram|X|Twitter|Facebook|Photos and videos|Profile|TikTok).*$", "", t, flags=re.IGNORECASE)
    # Strip dates (e.g. "· February 28, 2026")
    t = re.sub(r"\s*·\s*(?:January|February|March|April|May|June|July|August|September|October|November|December|\d{1,2},?\s*\d{4}|\d{4}).*$", "", t, flags=re.IGNORECASE)
    # Strip international headers like "Instagram 用户 Momina Sheikh : ..."
    t = re.sub(r"^Instagram\s+[^:]+:\s*", "", t, flags=re.IGNORECASE)
    # Strip @handle suffix e.g. 'John Doe (@johndoe)'
    t = re.sub(r"\s*\(?@[a-zA-Z0-9_.]+\)?.*$", "", t)
    # Strip 'Photo by' / 'Reel by' / 'Video by'
    t = re.sub(r"^(?:Photos?|Reels?|Videos?|Posts?)\s+by\s+", "", t, flags=re.IGNORECASE)
    # Cut off at first slash or pipe
    if "/" in t:
        parts = t.split("/")
        if len(parts[0].strip()) >= 2:
            t = parts[0].strip()
    if "|" in t:
        parts = t.split("|")
        if len(parts[0].strip()) >= 2:
            t = parts[0].strip()
    # Strip quotes and hashtags
    t = re.sub(r'[\"\'“”]', '', t)
    t = re.sub(r'#\w+', '', t)
    t = t.strip(' -–|•·:/')
    if len(t) > 35:
        t = t[:35].strip()

    # Reject generic placeholders
    tl = t.lower()
    if any(rej in tl for rej in (
        "link to facebook", "link to instagram", "link to twitter", "link to linkedin",
        "facebook", "instagram", "twitter", "linkedin", "x.com", "threads.net",
        "log in", "sign up", "page not found", "the site owner hides", "welcome back"
    )):
        return None

    return t if (t and len(t) >= 2) else None


def format_handle_to_name(handle: str, resolved_name: Optional[str] = None) -> str:
    """Format a social handle into a human-readable display name when title is missing/generic."""
    if not handle:
        return ""
    clean = handle.lstrip("@").strip()
    # Strip trailing numbers
    name_clean = re.sub(r"\d+$", "", clean).strip("._-")
    # Split by dot or underscore
    parts = [p.capitalize() for p in re.split(r"[._-]+", name_clean) if len(p) >= 2]
    if len(parts) >= 2:
        return " ".join(parts)
    elif len(parts) == 1:
        if resolved_name and parts[0].lower() in resolved_name.lower():
            return resolved_name
        return parts[0]
    return clean


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

    # 0c. LinkedIn vanity slug & handle corroboration
    if platform_info.get("platform") == "linkedin":
        slug_norm = re.sub(r"[-_.]", "", handle)
        if resolved_name and len(resolved_name.split()) >= 2:
            name_parts = [p.lower() for p in resolved_name.split() if len(p) >= 2]
            first, last = name_parts[0], name_parts[-1]
            concat = f"{first}{last}"
            rev_concat = f"{last}{first}"
            if slug_norm.startswith(concat) or slug_norm.startswith(rev_concat):
                score += 80
                reasons.append(f"Direct LinkedIn vanity URL match (in/{handle})")
        for v in all_variations:
            vl_norm = re.sub(r"[-_.]", "", v.lower())
            if slug_norm == vl_norm or (len(vl_norm) >= 5 and vl_norm in slug_norm):
                score += 70
                reasons.append(f"Handle match with LinkedIn URL (in/{handle})")
                break

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

    # 2. Name match (Supports exact, inverted, and Jaro-Winkler fuzzy transliteration)
    target_name = resolved_name
    if not target_name:
        for v in all_variations:
            if "." in v or "_" in v:
                v_parts = re.split(r"[._]", v)
                if len(v_parts) == 2 and len(v_parts[0]) >= 3 and len(v_parts[1]) >= 3:
                    if v_parts[0] in title_l and v_parts[1] in title_l:
                        target_name = f"{v_parts[0].title()} {v_parts[1].title()}"
                        break

    cand_extracted_name = extract_name_from_title(title, platform_info.get("platform", ""))
    name_matched = False

    if target_name and len(target_name.split()) >= 2:
        name_parts = [p.lower() for p in target_name.split() if len(p) >= 2]
        first, last = name_parts[0], name_parts[-1]
        rev_name = f"{last} {first}".lower()

        if target_name.lower() in title_l or rev_name in title_l:
            score += 40
            reasons.append(f"Full name match in title ({target_name})")
            name_matched = True
        elif first in title_l and last in title_l:
            score += 35
            reasons.append(f"First and last name in title ({first.title()} {last.title()})")
            name_matched = True
        elif rev_name in combined_text or target_name.lower() in combined_text:
            score += 30
            reasons.append(f"Full name match in bio ({target_name})")
            name_matched = True
        elif (first in combined_text and last in combined_text):
            score += 25
            reasons.append(f"Name corroborated in bio ({first.title()} {last.title()})")
            name_matched = True
        elif cand_extracted_name and len(cand_extracted_name.split()) >= 2:
            cand_parts = [p.lower() for p in cand_extracted_name.split() if len(p) >= 2]
            c_first, c_last = cand_parts[0], cand_parts[-1]
            jw_f = jaro_winkler_similarity(c_first, first)
            jw_l = jaro_winkler_similarity(c_last, last)
            # Check inverted as well (e.g. Last First)
            jw_f_inv = jaro_winkler_similarity(c_first, last)
            jw_l_inv = jaro_winkler_similarity(c_last, first)

            if (jw_f >= 0.88 and jw_l >= 0.88) or (jw_f_inv >= 0.88 and jw_l_inv >= 0.88):
                score += 25
                best_sim = max((jw_f + jw_l) / 2.0, (jw_f_inv + jw_l_inv) / 2.0)
                reasons.append(f"Fuzzy name match (Jaro-Winkler {best_sim:.0%}: '{cand_extracted_name}' ~ '{target_name}')")
                name_matched = True

    # 3. Location match
    if resolved_location:
        loc_tokens = [tok.strip().lower() for tok in re.split(r"[,/]", resolved_location) if len(tok.strip()) >= 3]
        matched_locs = [l for l in loc_tokens if l in combined_text]
        if matched_locs:
            score += 20
            reasons.append(f"Location match ({', '.join([l.title() for l in matched_locs])})")

    # 4. Conflicting Given Name Penalty (Rule 3.1)
    # If surname matches but given name is completely contradictory (e.g. Haseeb Hameed vs Atisam Hameed), cap score at 15
    if target_name and len(target_name.split()) >= 2 and cand_extracted_name and len(cand_extracted_name.split()) >= 2:
        name_parts = [p.lower() for p in target_name.split() if len(p) >= 2]
        cand_parts = [p.lower() for p in cand_extracted_name.split() if len(p) >= 2]
        first, last = name_parts[0], name_parts[-1]
        c_first, c_last = cand_parts[0], cand_parts[-1]
        surname_match = (c_last == last or jaro_winkler_similarity(c_last, last) >= 0.90)
        given_conflict = (c_first != first and jaro_winkler_similarity(c_first, first) < 0.65 and len(c_first) >= 3 and len(first) >= 3)
        if surname_match and given_conflict:
            score = min(score, 15)
            reasons.append(f"Conflicting given name penalty ({c_first.title()} vs {first.title()})")

    score = min(score, 95)
    return score, reasons



async def fetch_social_avatar(
    url: str,
    platform: str,
    handle: str,
    client: httpx.AsyncClient,
) -> Optional[str]:
    """
    Fetch authentic user avatar URL across all supported platforms
    using fast CDN endpoints and OpenGraph crawler metadata.
    """
    if not handle and not url:
        return None

    clean_handle = (handle or "").lstrip("@").strip()

    # 1. Twitter / X: Unavatar CDN
    if platform == "twitter" and clean_handle:
        return f"https://unavatar.io/x/{clean_handle}"

    # 2. Facebook: Graph API (Numerical ID or vanity) + OpenGraph fallback
    if platform == "facebook":
        if url:
            m_id = re.search(r"/(\d{8,25})", url)
            if m_id:
                return f"https://graph.facebook.com/{m_id.group(1)}/picture?type=large"
        if clean_handle and not any(c in clean_handle for c in " /?#"):
            return f"https://graph.facebook.com/{clean_handle}/picture?type=large"
        if url:
            try:
                headers = {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"}
                resp = await client.get(url, headers=headers, timeout=2.5, follow_redirects=True)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    og_meta = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
                    if og_meta and og_meta.get("content"):
                        img_url = og_meta["content"]
                        if not any(k in img_url.lower() for k in ("fb_icon", "logo", "default", "static.xx.fbcdn", "rsrc.php")):
                            return img_url
            except Exception:
                pass

    # 3. Instagram: Meta OpenGraph via rotated proxy
    if platform == "instagram" and (url or clean_handle):
        target_url = url or f"https://www.instagram.com/{clean_handle}/"
        try:
            headers = {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"}
            proxy = get_random_proxy_url()
            if proxy:
                async with httpx.AsyncClient(proxy=proxy, timeout=3.5, follow_redirects=True) as proxied:
                    resp = await proxied.get(target_url, headers=headers)
            else:
                resp = await client.get(target_url, headers=headers, timeout=3.5, follow_redirects=True)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                og_meta = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
                if og_meta and og_meta.get("content"):
                    img_url = og_meta["content"]
                    if not any(k in img_url.lower() for k in ("fb_icon", "logo", "default", "static.xx.fbcdn", "rsrc.php")):
                        return img_url
        except Exception:
            pass

    # 4. TikTok: OpenGraph CDN profile image
    if platform == "tiktok" and (url or clean_handle):
        target_url = url or f"https://www.tiktok.com/@{clean_handle}"
        try:
            headers = {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)", "Accept-Language": "en-US,en;q=0.9"}
            resp = await client.get(target_url, headers=headers, timeout=3.0, follow_redirects=True)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                og_meta = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
                if og_meta and og_meta.get("content"):
                    img_url = og_meta["content"]
                    if "static" not in img_url and not any(k in img_url.lower() for k in ("default", "logo", "placeholder")):
                        return img_url
        except Exception:
            pass

    # 5. Pinterest: High-Res OpenGraph Avatar
    if platform == "pinterest" and (url or clean_handle):
        target_url = url or f"https://www.pinterest.com/{clean_handle}/"
        try:
            headers = {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)", "Accept-Language": "en-US,en;q=0.9"}
            resp = await client.get(target_url, headers=headers, timeout=3.0, follow_redirects=True)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                og_meta = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
                if og_meta and og_meta.get("content"):
                    img_url = og_meta["content"]
                    if not any(k in img_url.lower() for k in ("default_280", "default_open_graph", "logo", "placeholder")):
                        return img_url
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
        proxy = get_random_proxy_url()
        if proxy:
            async with httpx.AsyncClient(proxy=proxy, timeout=5.5, follow_redirects=True) as proxied_client:
                resp = await proxied_client.get(url, headers=headers)
        else:
            resp = await client.get(url, headers=headers, timeout=5.5, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            og_title = (soup.find("meta", property="og:title") or {}).get("content", "")
            if not og_title:
                og_title = soup.title.string if soup.title else ""

            # Check if this is a genuine user profile
            if not og_title:
                return None
            og_title_l = og_title.lower()
            if any(reject in og_title_l for reject in ("page not found", "login • instagram", "welcome back", "instagram user:", "unsupported browser")):
                return None
            if og_title_l in ("instagram", "instagram photos and videos"):
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


async def probe_tiktok_profile(
    handle: str,
    client: httpx.AsyncClient,
) -> Optional[Dict[str, Any]]:
    """
    Directly probe a TikTok profile using crawler User-Agent.
    Extracts display name, followers/likes bio snippet, and CDN avatar image.
    """
    if not handle or len(handle) < 3:
        return None
    clean = handle.lower().lstrip("@").strip()
    if clean in ("explore", "direct", "trending", "about", "discover", "login", "live", "tag"):
        return None

    try:
        url = f"https://www.tiktok.com/@{clean}"
        headers = {
            "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = await client.get(url, headers=headers, timeout=5.5, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            og_title = (soup.find("meta", property="og:title") or {}).get("content", "")
            if not og_title:
                og_title = soup.title.string if soup.title else ""
            
            og_title_l = og_title.lower() if og_title else ""
            if "on tiktok" in og_title_l and "discover profiles" not in og_title_l and "watch trending" not in og_title_l:
                og_desc = (soup.find("meta", property="og:description") or {}).get("content", "")
                og_img = (soup.find("meta", property="og:image") or {}).get("content", "")
                # Extract display name: "Saad Asif on TikTok" -> "Saad Asif"
                m = re.match(r"^(.*?)\s+on\s+TikTok", og_title, re.IGNORECASE)
                display_name = m.group(1).strip() if m else clean
                return {
                    "platform": "tiktok",
                    "platform_label": "TikTok",
                    "handle": clean,
                    "name": display_name,
                    "url": url,
                    "snippet": og_desc or f"TikTok account @{clean}",
                    "avatar_url": og_img if og_img and "static" not in og_img else None,
                    "title": og_title,
                }
    except Exception:
        pass
    return None


async def probe_pinterest_profile(
    handle: str,
    client: httpx.AsyncClient,
) -> Optional[Dict[str, Any]]:
    """
    Directly probe a Pinterest profile using crawler User-Agent.
    Extracts display name, bio snippet, and CDN avatar image.
    """
    if not handle or len(handle) < 3:
        return None
    clean = handle.lower().lstrip("@").strip()
    if clean in ("explore", "pin", "ideas", "business", "help", "about", "login", "today", "shop", "news"):
        return None

    try:
        url = f"https://www.pinterest.com/{clean}/"
        headers = {
            "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = await client.get(url, headers=headers, timeout=5.5, follow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            og_title = (soup.find("meta", property="og:title") or {}).get("content", "")
            if not og_title:
                og_title = soup.title.string if soup.title else ""
            
            og_title_l = og_title.lower() if og_title else ""
            if "- profile | pinterest" in og_title_l or "on pinterest" in og_title_l:
                og_desc = (soup.find("meta", property="og:description") or {}).get("content", "")
                og_img = (soup.find("meta", property="og:image") or {}).get("content", "")
                # Extract display name: "Dameesha (rdameesha) - Profile | Pinterest" -> "Dameesha"
                m = re.match(r"^(.*?)\s*\([a-zA-Z0-9_.]+\)\s*-\s*Profile", og_title, re.IGNORECASE)
                display_name = m.group(1).strip() if m else clean
                return {
                    "platform": "pinterest",
                    "platform_label": "Pinterest",
                    "handle": clean,
                    "name": display_name,
                    "url": url,
                    "snippet": og_desc or f"Pinterest profile for {display_name}",
                    "avatar_url": og_img if og_img and "default_280" not in og_img and "default_open_graph" not in og_img else None,
                    "title": og_title,
                }
    except Exception:
        pass
    return None


_google_cse_disabled_reason: Optional[str] = None


async def query_google_cse(q_str: str, client: httpx.AsyncClient) -> List[Dict[str, str]]:
    """
    Query Google Programmable Search JSON API (100 free queries/day).
    Gracefully returns [] if unconfigured or on any quota/authentication error.
    """
    global _google_cse_disabled_reason
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    cse_id = os.getenv("GOOGLE_CSE_ID", "").strip()
    if not api_key or not cse_id:
        return []
    if _google_cse_disabled_reason:
        return []

    try:
        url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cse_id}&q={urllib.parse.quote(q_str)}"
        resp = await client.get(url, timeout=4.5)
        if resp.status_code == 200:
            data = resp.json()
            items = []
            for item in data.get("items", []):
                l = item.get("link", "")
                if l and (parse_social_url(l) or any(dom in l.lower() for dom in ("instagram.com", "facebook.com", "x.com", "twitter.com", "linkedin.com", "tiktok.com", "pinterest.com"))):
                    items.append({
                        "link": l,
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                    })
            if items:
                print(f"[Google CSE] ✓ 200 OK -> {len(items)} items for: {q_str}", flush=True)
                return items
            else:
                print(f"[Google CSE] ✓ 200 OK (0 relevant social items) -> Falling back to SearXNG", flush=True)
        elif resp.status_code == 403:
            _google_cse_disabled_reason = "HTTP 403 Permission Denied (Custom Search API not enabled in Google Cloud Console for this key)"
            print(f"[Google CSE] ✗ {_google_cse_disabled_reason} -> Seamlessly falling back to SearXNG/Yandex", flush=True)
        elif resp.status_code == 429:
            _google_cse_disabled_reason = "HTTP 429 Rate Limit (100 free daily queries exhausted)"
            print(f"[Google CSE] ✗ {_google_cse_disabled_reason} -> Seamlessly falling back to SearXNG/Yandex", flush=True)
        else:
            print(f"[Google CSE] ✗ HTTP {resp.status_code} error -> Falling back to SearXNG", flush=True)
    except Exception as e:
        print(f"[Google CSE] ✗ Query exception: {e} -> Falling back to SearXNG", flush=True)
    return []


async def search_social_candidates(
    email: str,
    resolved_name: Optional[str] = None,
    resolved_location: Optional[str] = None,
    gh_username: Optional[str] = None,
    company_name: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    has_verified_linkedin: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """
    Candidate discovery engine using rotated proxy DuckDuckGo search + platform-targeted queries.
    Returns (all_sorted_candidates, candidates_by_platform).
    """
    if client is None or getattr(client, "is_closed", False):
        async with httpx.AsyncClient(timeout=8.0) as local_client:
            return await search_social_candidates(
                email=email,
                resolved_name=resolved_name,
                resolved_location=resolved_location,
                gh_username=gh_username,
                company_name=company_name,
                client=local_client,
                has_verified_linkedin=has_verified_linkedin,
            )

    specific_handles, stem_handles = generate_handle_variations(email, resolved_name, gh_username)
    handles_to_probe = expand_social_probe_handles(specific_handles, stem_handles, resolved_name)[:35]
    all_variations = specific_handles + stem_handles + handles_to_probe[:25]
    if not all_variations and not resolved_name:
        return [], {"linkedin": [], "instagram": [], "twitter": [], "facebook": []}

    # Select 1 primary proxy (or direct host IP) for this email lookup
    lookup_pool = ["DIRECT (Host IP)"] + get_proxy_ips()
    lookup_proxy_ip = random.choice(lookup_pool)
    print(f"\n[Social Discovery] ───────────────────────────────────────────────────", flush=True)
    print(f"[Social Discovery] Initiating social candidate discovery for: {email}", flush=True)
    print(f"[Social Discovery] Active proxy/route for lookup: {lookup_proxy_ip}", flush=True)
    print(f"[Social Discovery] Specific handles: {specific_handles} | Stems: {stem_handles}", flush=True)
    if resolved_name:
        print(f"[Social Discovery] Anchor name: '{resolved_name}' | Location: '{resolved_location or 'N/A'}'", flush=True)
    if company_name:
        print(f"[Social Discovery] Company Anchor: '{company_name}'", flush=True)

    # Extract clean handles for search queries, stripping numbers/separators to keep queries effective
    clean_query_handles = []
    for h in (stem_handles[:4] + specific_handles[:2]):
        clean_h = re.sub(r"[._+-]", "", h)
        clean_no_num = re.sub(r"\d+", "", clean_h)
        if clean_no_num and clean_no_num not in clean_query_handles and len(clean_no_num) >= 3:
            clean_query_handles.append(clean_no_num)
        if clean_h and clean_h not in clean_query_handles and len(clean_h) >= 3:
            clean_query_handles.append(clean_h)

    # 1. Direct Social Profile Probes (Instagram, TikTok, Pinterest in parallel)
    print(f"[Social Discovery] Direct probes ({len(handles_to_probe)}): Instagram (35), TikTok (20), Pinterest (20)...", flush=True)
    ig_probe_task = asyncio.gather(*[probe_instagram_profile(h, client) for h in handles_to_probe])
    tt_probe_task = asyncio.gather(*[probe_tiktok_profile(h, client) for h in handles_to_probe[:20]])
    pin_probe_task = asyncio.gather(*[probe_pinterest_profile(h, client) for h in handles_to_probe[:20]])

    # 2. Extract high-signal pattern handle terms (e.g. dameesha_09, momina0_, ahtisham.v2, ahtisham.v3, mr.sharafat760)
    core_stem = stem_handles[0] if stem_handles else ""
    if resolved_name and len(resolved_name.split()) >= 1:
        core_stem = resolved_name.split()[0].lower()
    
    pattern_handles = []
    priority_pattern_families = ["_09", "0_", "_0", ".v2", ".v3", "09", "_v2", "_v3", "mr."]
    for pat in priority_pattern_families:
        for h in handles_to_probe:
            if pat in h and core_stem and core_stem in h and h not in pattern_handles:
                pattern_handles.append(h)
                break
    for pat in priority_pattern_families:
        for h in handles_to_probe:
            if pat in h and h not in pattern_handles:
                pattern_handles.append(h)
                break
    pattern_handles = pattern_handles[:4]

    # 3. High-Signal Targeted Platform Queries (Clean search strings for SearXNG)
    search_jobs = []

    # LinkedIn Queries (if not already verified in base sources)
    if not has_verified_linkedin:
        if resolved_name and len(resolved_name.split()) >= 2:
            if company_name and 1 <= len(company_name.split()) <= 2:
                search_jobs.append(("linkedin", f'site:linkedin.com/in "{resolved_name}" {company_name.strip()}'))
            else:
                search_jobs.append(("linkedin", f'site:linkedin.com/in "{resolved_name}"'))
        for h in specific_handles[:2]:
            if h and len(h) >= 3:
                search_jobs.append(("linkedin", f'site:linkedin.com/in {h}'))
        if core_stem and len(core_stem) >= 4 and core_stem not in specific_handles:
            search_jobs.append(("linkedin", f'site:linkedin.com/in {core_stem}'))

    # Instagram Queries
    if resolved_name and len(resolved_name.split()) >= 2:
        search_jobs.append(("instagram", f'site:instagram.com "{resolved_name}"'))
    for h in specific_handles[:2]:
        if h and len(h) >= 3:
            search_jobs.append(("instagram", f'site:instagram.com {h}'))
    if core_stem and len(core_stem) >= 4 and core_stem not in specific_handles:
        search_jobs.append(("instagram", f'site:instagram.com {core_stem}'))

    # Twitter / X Queries
    if resolved_name and len(resolved_name.split()) >= 2:
        search_jobs.append(("twitter", f'site:twitter.com "{resolved_name}"'))
    for h in specific_handles[:2]:
        if h and len(h) >= 3:
            search_jobs.append(("twitter", f'site:twitter.com {h}'))
    if core_stem and len(core_stem) >= 4 and core_stem not in specific_handles:
        search_jobs.append(("twitter", f'site:twitter.com {core_stem}'))

    # Facebook Queries
    if resolved_name and len(resolved_name.split()) >= 2:
        search_jobs.append(("facebook", f'site:facebook.com "{resolved_name}"'))
    for h in specific_handles[:2]:
        if h and len(h) >= 3:
            search_jobs.append(("facebook", f'site:facebook.com {h}'))
    if core_stem and len(core_stem) >= 4 and core_stem not in specific_handles:
        search_jobs.append(("facebook", f'site:facebook.com {core_stem}'))

    for p, q in search_jobs:
        print(f"[Social Discovery] Sending {p.upper()} query: {q}", flush=True)

    async def run_search_q(platform_tag: str, q_str: str):
        # 1. Direct Google Custom Search JSON API if configured
        cse_items = await query_google_cse(q_str, client)
        if cse_items:
            return platform_tag, cse_items

        # 2. Seamless fallback to SearXNG / Yandex
        searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8888/search")
        try:
            req = client.get(
                searxng_url,
                params={"q": q_str, "format": "json", "pageno": 1, "engines": "yandex"},
                timeout=7.0
            )
            resp = await req
            items = []
            seen_links = set()
            if resp.status_code == 200:
                raw_results = resp.json().get("results", [])
                for r in raw_results:
                    l = r.get("url", "")
                    if l and l not in seen_links:
                        if parse_social_url(l) or any(dom in l.lower() for dom in ("instagram.com", "facebook.com", "x.com", "twitter.com", "linkedin.com", "tiktok.com", "pinterest.com")):
                            seen_links.add(l)
                            items.append({
                                "link": l,
                                "title": r.get("title", ""),
                                "snippet": r.get("content", ""),
                            })
            if items:
                print(f"[Social Discovery] ✓ SearXNG ({platform_tag.upper()}) -> {len(items)} items for: {q_str}", flush=True)
                return platform_tag, items
            else:
                return platform_tag, []
        except Exception as e:
            print(f"[Social Discovery] [-] SearXNG error ({platform_tag.upper()}): {e}", flush=True)
            return platform_tag, []

    search_task = asyncio.gather(*[run_search_q(p, q) for p, q in search_jobs])
    search_results, probed_ig_results, probed_tt_results, probed_pin_results = await asyncio.gather(
        search_task, ig_probe_task, tt_probe_task, pin_probe_task
    )

    candidates_map: Dict[str, Dict[str, Any]] = {}

    # Helper to ingest probed candidate
    def ingest_probed(p_cand: Optional[Dict[str, Any]], plat: str, plat_label: str):
        if not p_cand:
            return
        h_clean = p_cand["handle"].lstrip("@")
        parsed = {
            "platform": plat,
            "platform_label": plat_label,
            "handle": h_clean,
            "url": p_cand["url"],
        }
        score, reasons = score_candidate(
            parsed, p_cand.get("title", ""), p_cand.get("snippet", ""), all_variations, resolved_name, resolved_location, gh_username
        )
        if score >= 25:
            dedup_key = f"{plat}:{h_clean.lower()}"
            candidates_map[dedup_key] = {
                "platform": plat,
                "platform_label": plat_label,
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
            print(f"[Social Discovery] [+] Probed {plat_label} handle confirmed: @{h_clean} (score={score}%, name='{p_cand.get('name')}')", flush=True)

    # Process direct probed profiles
    for p_cand in probed_ig_results:
        ingest_probed(p_cand, "instagram", "Instagram")
    for p_cand in probed_tt_results:
        ingest_probed(p_cand, "tiktok", "TikTok")
    for p_cand in probed_pin_results:
        ingest_probed(p_cand, "pinterest", "Pinterest")

    for platform_tag, items in search_results:
        found_on_platform = 0
        for item in items:
            link = item.get("link", "")
            title = item.get("title", "")
            snippet = item.get("snippet", "")

            parsed = parse_social_url(link)
            if not parsed:
                # If link is a post/reel/status, attempt to extract authentic profile handle from title or snippet
                combined_meta = f"{title} {snippet}"
                if platform_tag == "instagram" and "instagram.com" in link:
                    for v in all_variations:
                        vl = v.lower().strip("@")
                        if len(vl) >= 4 and re.search(r"(?:@|\b)" + re.escape(vl) + r"\b", combined_meta, re.IGNORECASE):
                            parsed = {
                                "platform": "instagram",
                                "platform_label": "Instagram",
                                "handle": vl,
                                "url": f"https://www.instagram.com/{vl}",
                            }
                            break
                    if not parsed:
                        ig_at_matches = re.findall(r"@([a-zA-Z0-9_.]{3,30})", combined_meta)
                        for h_cand in ig_at_matches:
                            clean_h = h_cand.strip("._")
                            if clean_h.lower() not in ("instagram", "reel", "reels", "p", "explore", "threads", "meta", "stories"):
                                parsed = {
                                    "platform": "instagram",
                                    "platform_label": "Instagram",
                                    "handle": h_cand,
                                    "url": f"https://www.instagram.com/{h_cand}",
                                }
                                break
                    if not parsed:
                        by_match = re.search(r"(?:Photos?|Reels?|Videos?|Posts?)\s+by\s+([a-zA-Z0-9_.]{3,30})", combined_meta, re.IGNORECASE)
                        if by_match:
                            h_by = by_match.group(1).strip("._")
                            if h_by.lower() not in ("instagram", "reel", "reels", "p", "explore"):
                                parsed = {
                                    "platform": "instagram",
                                    "platform_label": "Instagram",
                                    "handle": h_by,
                                    "url": f"https://www.instagram.com/{h_by}",
                                }
            if not parsed:
                continue

            platform = parsed["platform"]
            handle = parsed["handle"]
            dedup_key = f"{platform}:{handle.lower()}"

            score, reasons = score_candidate(
                parsed, title, snippet, all_variations, resolved_name, resolved_location, gh_username
            )

            # Accept all candidates with score >= 5 so no valid candidates are hidden
            if score < 5:
                continue

            raw_name = extract_name_from_title(title, platform)
            display_name = raw_name if raw_name else format_handle_to_name(handle, resolved_name)
            if not display_name:
                display_name = handle

            clean_snippet = (snippet or "").strip()
            if any(bad in clean_snippet.lower() for bad in ("the site owner hides", "link to facebook", "link to instagram", "welcome back", "log in")):
                clean_snippet = f"{parsed['platform_label']} profile for @{handle.lstrip('@')}"

            cand_obj = {
                "platform": platform,
                "platform_label": parsed["platform_label"],
                "handle": f"@{handle}" if not handle.startswith("@") else handle,
                "name": display_name,
                "url": parsed["url"],
                "snippet": clean_snippet or f"{parsed['platform_label']} account @{handle.lstrip('@')}",
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
    for platform_tag, items in search_results:
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

    # Concurrently fetch avatars for top candidates (up to 12 candidates across platforms)
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
        "linkedin": [c for c in all_candidates if c["platform"] == "linkedin"][:10],
        "instagram": [c for c in all_candidates if c["platform"] == "instagram"][:10],
        "twitter": [c for c in all_candidates if c["platform"] == "twitter"][:10],
        "facebook": [c for c in all_candidates if c["platform"] == "facebook"][:10],
        "tiktok": [c for c in all_candidates if c["platform"] == "tiktok"][:10],
        "pinterest": [c for c in all_candidates if c["platform"] == "pinterest"][:10],
    }

    total_count = sum(len(v) for v in by_platform.values())
    print(f"[Social Discovery] Total ranked candidates: {total_count} (LI: {len(by_platform['linkedin'])}, IG: {len(by_platform['instagram'])}, X: {len(by_platform['twitter'])}, FB: {len(by_platform['facebook'])}, TT: {len(by_platform['tiktok'])}, PIN: {len(by_platform['pinterest'])})", flush=True)
    if all_candidates:
        top = all_candidates[0]
        print(f"[Social Discovery] Top candidate: [{top['platform']}] {top['handle']} - {top['name']} ({top['score']}%)", flush=True)
    print(f"[Social Discovery] ───────────────────────────────────────────────────\n", flush=True)

    return all_candidates[:40], by_platform
