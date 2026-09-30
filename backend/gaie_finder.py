"""
gaie_finder.py
--------------
Google Account Information Extractor (GAIE) integration for EmailLookup.
Extracts verified Google Display Name, GAIA ID, Profile Photo, and linked Google services
for a target Gmail or Google Workspace address using authenticated Google internal APIs
routed through the residential proxy pool.
"""

import os
import re
import sys
import json
import base64
import asyncio
import httpx
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv

# Ensure UTF-8 console output on Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"), override=True)

try:
    from social_finder import get_random_proxy_url
except ImportError:
    from backend.social_finder import get_random_proxy_url


_GHUNT_INITIALIZED = False
_GHUNT_CREDS = None


def parse_cookie_dict(cookie_str: str) -> dict:
    """Parse raw HTTP cookie string into key-value dictionary."""
    cookies = {}
    if not cookie_str:
        return cookies
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        cookies[k.strip()] = v.strip()
    return cookies


async def _get_or_init_creds(client: httpx.AsyncClient):
    """
    Load or initialize GHunt credentials from .env:
    - GHUNT_CREDS_BASE64 (base64 export from GHunt Companion)
    - GOOGLE_OAUTH_TOKEN (starts with oauth2_4/)
    - GOOGLE_MASTER_TOKEN (starts with aas_et/)
    - GOOGLE_SESSION_COOKIES (raw browser cookies)
    """
    global _GHUNT_INITIALIZED, _GHUNT_CREDS
    if _GHUNT_INITIALIZED and _GHUNT_CREDS:
        return _GHUNT_CREDS

    try:
        from ghunt.objects.apis import GHuntCreds
        from ghunt.helpers.auth import android_master_auth, check_and_gen, gen_cookies_and_osids
    except ImportError:
        return None

    creds = GHuntCreds()
    creds_b64 = os.getenv("GHUNT_CREDS_BASE64", "").strip()
    oauth_token = os.getenv("GOOGLE_OAUTH_TOKEN", "").strip()
    master_token = os.getenv("GOOGLE_MASTER_TOKEN", "").strip()
    raw_cookies = os.getenv("GOOGLE_SESSION_COOKIES", "").strip()

    try:
        if creds_b64:
            raw_data = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
            if "oauth_token" in raw_data:
                oauth_token = raw_data["oauth_token"]
            if "cookies" in raw_data:
                creds.cookies = raw_data["cookies"]
            if "osids" in raw_data:
                creds.osids = raw_data["osids"]
            if "master_token" in raw_data:
                master_token = raw_data["master_token"]

        if oauth_token and not master_token:
            m_token, _, _, _ = await android_master_auth(client, oauth_token)
            master_token = m_token

        if master_token:
            creds.android.master_token = master_token
            await check_and_gen(client, creds)
            _GHUNT_CREDS = creds
            _GHUNT_INITIALIZED = True
            return _GHUNT_CREDS

        if raw_cookies:
            cookie_dict = parse_cookie_dict(raw_cookies)
            creds.cookies = cookie_dict
            _GHUNT_CREDS = creds
            _GHUNT_INITIALIZED = True
            return _GHUNT_CREDS

    except Exception as e:
        print(f"[GAIE] Auth initialization notice: {e}", flush=True)

    return None


async def lookup_google_account(email: str, client: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
    """
    Query Google Account directory and profile metadata for a target email.
    Returns:
    {
        "found": bool,
        "name": Optional[str],
        "gaia_id": Optional[str],
        "avatar_url": Optional[str],
        "is_google_account": bool,
        "email": str,
        "source": "google_account"
    }
    """
    result = {
        "found": False,
        "name": None,
        "gaia_id": None,
        "avatar_url": None,
        "is_google_account": False,
        "email": email,
        "source": "google_account",
    }

    email_clean = email.lower().strip()
    if not email_clean or "@" not in email_clean:
        return result

    proxy = get_random_proxy_url()
    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=8.0, proxy=proxy, verify=False)
        close_client = True

    try:
        creds = await _get_or_init_creds(client)
        if not creds:
            return result

        from ghunt.apis.peoplepa import PeoplePaHttp
        people_pa = PeoplePaHttp(creds)
        found, person = await people_pa.people_lookup(client, email_clean, params_template="max_details")

        if found and person:
            result["found"] = True
            result["is_google_account"] = True
            result["gaia_id"] = person.personId

            # Extract full display name from PROFILE or CONTACT container
            full_name = None
            if "PROFILE" in person.names and person.names["PROFILE"].fullname:
                full_name = person.names["PROFILE"].fullname
            elif "CONTACT" in person.names and person.names["CONTACT"].fullname:
                full_name = person.names["CONTACT"].fullname
            elif person.names:
                for container, name_obj in person.names.items():
                    if name_obj and name_obj.fullname:
                        full_name = name_obj.fullname
                        break

            result["name"] = full_name

            # Extract avatar if not default
            avatar_url = None
            if "PROFILE" in person.profilePhotos:
                photo_obj = person.profilePhotos["PROFILE"]
                if photo_obj and not getattr(photo_obj, "isDefault", False):
                    avatar_url = getattr(photo_obj, "url", None)
            elif person.profilePhotos:
                for container, photo_obj in person.profilePhotos.items():
                    if photo_obj and getattr(photo_obj, "url", None):
                        avatar_url = photo_obj.url
                        break

            result["avatar_url"] = avatar_url

            if full_name:
                print(f"[GAIE] [+] Google Account identified: Name='{full_name}', GAIA ID={person.personId}", flush=True)

    except Exception as e:
        # Non-blocking graceful catch
        pass
    finally:
        if close_client:
            await client.aclose()

    return result
