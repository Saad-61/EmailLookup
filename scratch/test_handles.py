import os
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import httpx
from dotenv import load_dotenv

load_dotenv('.env')

key = os.getenv('SERPER_API_KEY')
headers = {'X-API-KEY': key, 'Content-Type': 'application/json'}
for q in ['site:instagram.com ahtisham.v2', 'site:instagram.com ahtisham.v3', 'site:facebook.com ahtishamdilawar']:
    r = httpx.post('https://google.serper.dev/search', headers=headers, json={'q': q, 'num': 5})
    items = r.json().get('organic', [])
    print(f"Query '{q}': {len(items)} items")
    for item in items:
        print('  -', item.get('link'), '|', item.get('title'))
