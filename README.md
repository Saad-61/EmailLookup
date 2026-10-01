# Email Lookup & Verification Tool

A high-performance reverse email lookup and SMTP verifier application built with FastAPI, SQLite, Playwright, and vanilla JS/CSS.

---

## Key Features

- **Reverse Email Lookup**:
  - Discovers full name, avatar, bio, location, and website.
  - Extracts GitHub profiles, repositories, and commit history.
  - Detects account existence across 30+ platforms (Holehe method).
  - Searches and ranks candidate social media profiles (LinkedIn, Instagram, Twitter/X, TikTok, Pinterest, Facebook, Spotify, GitHub, Stack Overflow).
  - Multi-anchor scoring algorithm with Jaro-Winkler similarity and surname disambiguation.
- **Direct Stack Overflow API Integration**:
  - Real-time user discovery via Stack Exchange REST API v2.3 (`inname` search).
  - Preserves distinct user accounts by unique User ID (`/users/{uid}`).
  - Extracts reputation scores, tags, profile links, and website corroboration.
  - Works with 0 authentication out-of-the-box (300 req/day) with optional `STACKEXCHANGE_API_KEY` for 10,000 req/day.
- **Automated Spotify Pathfinder GraphQL User Search**:
  - Automatically solves Spotify's dynamic TOTP challenge via background headless Playwright browser.
  - Auto-refreshes Bearer access tokens 5 minutes before expiration with in-memory caching (0ms lookup latency).
  - Fully hands-free using long-lived `SPOTIFY_SP_DC` session cookie (no manual token copy-pasting).
- **Residential Proxy Rotation & Failover**:
  - Dynamic proxy pool with latency ranking and rate-limit cooldown tracking.
  - Concurrently queries DuckDuckGo across 20+ residential proxy IPs with automatic failover.
- **SMTP Email Verifier**:
  - Outbound Port 25 availability check.
  - Real-time SMTP handshake verification (`HELO` / `MAIL FROM` / `RCPT TO`).
  - MX provider identification & Catch-all server detection.
- **High Performance Persistent Caching**:
  - SQLite persistent cache with WAL mode enabled (`data/cache.db`).
  - Cached lookup results (24h default) with force-refresh and cache invalidation endpoint support.

---

## Technical Stack

- **Backend**: Python 3.11+, FastAPI, `httpx`, `aiosqlite`, `dnspython`, `beautifulsoup4`, `playwright`.
- **Frontend**: Vanilla HTML5, CSS3, JavaScript (Fetch API).
- **Database**: SQLite3 (`data/cache.db`).

---

## Quickstart Setup

### 1. Clone & Install Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install required packages
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

### 2. Configure Environment

Copy `example.env` to `.env`:

```bash
# On Windows:
copy example.env .env
# On Linux/macOS:
cp example.env .env
```

#### Environment Variables Overview:
| Variable | Status | Default / Behavior |
| :--- | :--- | :--- |
| `GITHUB_TOKEN` | Optional | Works unauthenticated (60 req/hr); token increases limit to 5,000 req/hr. |
| `STACKEXCHANGE_API_KEY` | Optional | Works unauthenticated (300 req/day); key increases limit to 10,000 req/day. |
| `SPOTIFY_SP_DC` | Optional | If set, launches Playwright worker to auto-refresh Spotify GraphQL tokens; if blank, skipped gracefully. |
| `PROXY_IPS`, `PROXY_USERNAME`, `PROXY_PASSWORD` | Optional | If blank, searches run from local host; if set, enables proxy rotation with failover. |
| `SMTP_SENDER_EMAIL`, `SMTP_HELO_HOST` | Optional | Fallbacks provided for Port 25 SMTP handshake checks. |

### 3. Run the Application

Start the server using `uvicorn`:

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open your browser and navigate to:
[http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## Core Pipeline Architecture

For in-depth details on how the pipelines, scoring algorithms, and database cache operate:
- See **[docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md)** for master architecture and pipeline details.
- See **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** for developer setup and testing commands.
- See **[docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)** for implementation details.
- See **[AGENTS.md](AGENTS.md)** for AI agent guidelines and code standards.

---

## Testing

Run the automated test suite to check reverse lookup accuracy:

```bash
python tests/test_lookup.py
```
