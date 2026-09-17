"""
tests/test_lookup.py
---------------------
Automated test suite to verify lookup engine accuracy against real test emails.

Run with:
    python tests/test_lookup.py
"""

import asyncio
import os
import sys
import json
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from lookup_engine import run_lookup

TEST_CASES = [
    {
        "email": "saadasif78656@gmail.com",
        "description": "User's Gmail address",
        "expected_name_keywords": ["Saad", "Asif"],
        "expected_github": "Saad-61",
    },
    {
        "email": "torvalds@linux-foundation.org",
        "description": "Linus Torvalds (Linux creator)",
        "expected_name_keywords": ["Linus", "Torvalds"],
    },
    {
        "email": "bill@microsoft.com",
        "description": "Corporate email test",
    }
]

async def run_tests():
    print("\n========================================================")
    print("       RUNNING AUTOMATED LOOKUP ENGINE ACCURACY TEST    ")
    print("========================================================\n")

    for tc in TEST_CASES:
        email = tc["email"]
        desc = tc["description"]
        print(f"--> Testing: {email} ({desc})")

        res = await run_lookup(email)

        person = res.get("person", {})
        profiles = res.get("profiles", {})
        breaches = res.get("breaches", [])
        email_quality = res.get("email_quality", {})

        print(f"   * Query Time:     {res.get('query_time_ms')}ms")
        print(f"   * Resolved Name:  {person.get('name') or 'N/A'}")
        print(f"   * Avatar:         {person.get('avatar') or 'N/A'}")
        print(f"   * Bio:            {person.get('bio') or 'N/A'}")
        print(f"   * GitHub Profile: {json.dumps(profiles.get('github', {})) if profiles.get('github') else 'None'}")
        print(f"   * LinkedIn URL:   {profiles.get('linkedin') or 'None'}")
        print(f"   * Quality Score:  {email_quality.get('quality_score', 'N/A')}")
        print(f"   * Risk Levels:    Address: {email_quality.get('address_risk')}, Domain: {email_quality.get('domain_risk')}")
        print(f"   * Breaches:       {len(breaches)} breach(es) found")
        if breaches:
            print(f"     Domains: {[b['name'] for b in breaches]}")

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

        print("-" * 56 + "\n")

if __name__ == "__main__":
    asyncio.run(run_tests())
