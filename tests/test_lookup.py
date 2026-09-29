"""
tests/test_lookup.py
---------------------
Automated test suite to verify lookup engine accuracy against real test emails and unit helpers.

Run with:
    python tests/test_lookup.py
"""

import asyncio
import os
import sys
import json
import httpx
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from lookup_engine import run_lookup, lookup_gravatar, clean_social_url
from social_finder import parse_social_url

def run_unit_tests():
    print("\n========================================================")
    print("       RUNNING UNIT TESTS (URL PARSER & GRAVATAR)       ")
    print("========================================================\n")

    # 1. Test Twitter status/post URL parsing to profile handle
    tw_status_url = "https://x.com/ShayyanAmin/status/178901234567"
    parsed_tw = parse_social_url(tw_status_url)
    assert parsed_tw is not None, "Twitter status URL should be parsed!"
    assert parsed_tw["handle"] == "ShayyanAmin", f"Expected handle 'ShayyanAmin', got '{parsed_tw['handle']}'"
    assert parsed_tw["url"] == "https://x.com/ShayyanAmin", f"Expected profile URL 'https://x.com/ShayyanAmin', got '{parsed_tw['url']}'"
    print("   [OK] Twitter Status URL Parser: Passed (Status post -> User profile handle @ShayyanAmin)")

    # 2. Test Spotify URL cleaning
    sp_url = "spotify:user:saadlife61"
    cleaned_sp = clean_social_url(sp_url, platform="spotify")
    assert cleaned_sp == "https://open.spotify.com/user/saadlife61", f"Got '{cleaned_sp}'"
    print("   [OK] Spotify URI Sanitizer: Passed (spotify:user:saadlife61 -> open.spotify.com/user/saadlife61)")

    print("-" * 56 + "\n")


TEST_CASES = [
    {
        "email": "saadasif78656@gmail.com",
        "description": "User's Gmail address",
        "expected_name_keywords": ["Saad", "Asif"],
        "expected_github": "Saad-61",
        "expected_profiles": ["github", "linkedin", "twitter", "spotify"],
    },
    {
        "email": "torvalds@linux-foundation.org",
        "description": "Linus Torvalds (Linux creator)",
        "expected_name_keywords": ["Linus", "Torvalds"],
        "expected_profiles": ["github", "linkedin"],
    },
    {
        "email": "bill@microsoft.com",
        "description": "Corporate email test",
        "expected_name_keywords": ["Bill", "Gates"],
    }
]

async def run_integration_tests():
    print("\n========================================================")
    print("       RUNNING AUTOMATED LOOKUP ENGINE E2E ACCURACY TEST ")
    print("========================================================\n")

    # Gravatar unit test for saadasif78656@gmail.com
    async with httpx.AsyncClient(timeout=8) as client:
        grav = await lookup_gravatar("saadasif78656@gmail.com", client)
        assert grav.get("facebook_url") is None, "Facebook should NOT be extracted from Gravatar!"
        print(f"   [OK] Gravatar Isolation: Verified Facebook is excluded. Gravatar extracted keys: {list(grav.keys())}")
        print("-" * 56 + "\n")

    for tc in TEST_CASES:
        email = tc["email"]
        desc = tc["description"]
        print(f"--> Testing: {email} ({desc})")

        res = await run_lookup(email)

        person = res.get("person", {})
        profiles = res.get("profiles", {})
        social_candidates = res.get("social_candidates", [])
        cands_by_plat = res.get("social_candidates_by_platform", {})

        print(f"   * Query Time:     {res.get('query_time_ms')}ms")
        print(f"   * Resolved Name:  {person.get('name') or 'N/A'}")
        print(f"   * Avatar:         {person.get('avatar') or 'N/A'}")
        print(f"   * Bio:            {person.get('bio') or 'N/A'}")
        print(f"   * Verified Profiles: {list(profiles.keys())}")
        print(f"   * GitHub Profile: {json.dumps(profiles.get('github', {})) if profiles.get('github') else 'None'}")
        print(f"   * LinkedIn Profile: {json.dumps(profiles.get('linkedin', {})) if profiles.get('linkedin') else 'None'}")
        print(f"   * Twitter Profile: {json.dumps(profiles.get('twitter', {})) if profiles.get('twitter') else 'None'}")
        print(f"   * Spotify Profile: {json.dumps(profiles.get('spotify', {})) if profiles.get('spotify') else 'None'}")
        print(f"   * Social Cands:   {len(social_candidates)} discovered ({ {k: len(v) for k, v in cands_by_plat.items()} })")

        # Assertions / Warnings
        name = person.get("name") or ""
        if "expected_name_keywords" in tc:
            match = any(kw.lower() in name.lower() for kw in tc["expected_name_keywords"])
            if match:
                print(f"   [OK] Name accuracy: MATCH ({name})")
            else:
                print(f"   [WARN] Name accuracy: MISMATCH (Got '{name}', expected keywords {tc['expected_name_keywords']})")

        if "expected_github" in tc:
            gh_username = (profiles.get("github", {}) or {}).get("username", "")
            if tc["expected_github"].lower() in gh_username.lower():
                print(f"   [OK] GitHub username: MATCH (@{gh_username})")
            else:
                print(f"   [WARN] GitHub username: MISMATCH (Got '@{gh_username}', expected '@{tc['expected_github']}')")

        if "expected_profiles" in tc:
            for p_key in tc["expected_profiles"]:
                if p_key in profiles:
                    print(f"   [OK] Verified Profile '{p_key}': FOUND ({profiles[p_key].get('url') if isinstance(profiles[p_key], dict) else profiles[p_key]})")
                else:
                    print(f"   [WARN] Verified Profile '{p_key}': MISSING")

        print("-" * 56 + "\n")

if __name__ == "__main__":
    run_unit_tests()
    asyncio.run(run_integration_tests())
