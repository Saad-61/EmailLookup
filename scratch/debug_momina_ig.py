import os
import httpx
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("SERPER_API_KEY")
q = 'site:instagram.com (mominawaqar18 OR momina0 OR waqarmomina OR mominawaqar) OR (site:instagram.com "Momina Waqar")'

r = httpx.post(
    "https://google.serper.dev/search",
    headers={"X-API-KEY": key.strip(), "Content-Type": "application/json"},
    json={"q": q, "num": 10}
)
for idx, x in enumerate(r.json().get("organic", []), 1):
    link = x.get("link", "")
    title = x.get("title", "").encode("ascii", errors="replace").decode()
    print(f"[{idx}] {link} | {title}")
