import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import asyncio
import httpx
from backend.social_finder import search_social_candidates

async def main():
    async with httpx.AsyncClient(timeout=8.0) as client:
        cands, by_plat = await search_social_candidates(
            'atisamhameed6@gmail.com',
            'Atisam Hameed',
            'Faisalabad, Pakistan',
            None,
            client
        )
    print('=== Instagram Candidates ===')
    for c in by_plat['instagram']:
        print('  -', c['handle'], 'Name:', c['name'], 'Score:', c['score'], 'Reasons:', c['reasons'])

if __name__ == '__main__':
    asyncio.run(main())
