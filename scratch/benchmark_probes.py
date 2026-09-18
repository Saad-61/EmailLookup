import asyncio
import time
import httpx
from bs4 import BeautifulSoup

handles = [
    "_momina0", "momina0", "momina0_",
    "dameesha", "dameesha_09", "_dameesha", "dameesha_",
    "ahtisham", "ahtisham.v2", "ahtisham.v3", "_ahtisham",
    "atisam", "atisamhameed", "hameedatisam",
    "sharafat", "sharafat_760", "sharafat760"
]

async def probe(h, client):
    headers = {
        'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    url = f'https://www.instagram.com/{h}/'
    try:
        r = await client.get(url, headers=headers)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            og_title = soup.find('meta', property='og:title')
            title = og_title['content'] if og_title else ''
            return h, 200, title
    except Exception as e:
        return h, 0, str(e)
    return h, r.status_code, ''

async def main():
    t0 = time.time()
    async with httpx.AsyncClient(timeout=3.5, follow_redirects=True) as client:
        results = await asyncio.gather(*[probe(h, client) for h in handles])
    dt = time.time() - t0
    print(f"Probed {len(handles)} handles in {dt:.2f} seconds:")
    for h, status, title in results:
        if status == 200:
            print(f"  ✓ {h:15} -> {status} | {title[:40]}")

asyncio.run(main())
