import asyncio
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import httpx
from backend.social_finder import search_social_candidates

async def test_email(email, name=None, location=None, gh_username=None):
    print(f"\n==========================================")
    print(f"TESTING: {email} (name={name}, gh={gh_username})")
    async with httpx.AsyncClient(timeout=8.0) as client:
        cands, by_plat = await search_social_candidates(
            email=email,
            resolved_name=name,
            resolved_location=location,
            gh_username=gh_username,
            client=client,
        )
    print(f"Results for {email}:")
    print(f"  Instagram ({len(by_plat['instagram'])}):")
    for c in by_plat['instagram']:
        print(f"    - {c['handle']} ({c['name']}) | Score={c['score']} | {c['url']}")
    print(f"  Facebook ({len(by_plat['facebook'])}):")
    for c in by_plat['facebook']:
        print(f"    - {c['handle']} ({c['name']}) | Score={c['score']} | {c['url']}")
    print(f"  Twitter ({len(by_plat['twitter'])}):")
    for c in by_plat['twitter']:
        print(f"    - {c['handle']} ({c['name']}) | Score={c['score']} | {c['url']}")

async def main():
    await test_email("rdameesha@gmail.com")
    await test_email("mominawaqar18@gmail.com", "Momina Waqar", "Faisalabad, Pakistan", "momina0")
    await test_email("ahtishamdilawar@gmail.com", "Ahtisham Dilawar")

if __name__ == "__main__":
    asyncio.run(main())
