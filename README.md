# Email Lookup & Verification Tool

A high-performance reverse email lookup and SMTP verifier application built with FastAPI, SQLite, Playwright, and vanilla JS/CSS.

---

## Key Features

- **Reverse Email Lookup**:
  - Discovers full name, avatar, bio, location, and website.
  - Extracts GitHub profiles, repositories, and commit history.
  - Detects account existence across 30+ platforms (Holehe method).
  - Searches and ranks candidate social media profiles (LinkedIn, Instagram, Twitter/X, TikTok, Pinterest, Facebook, Spotify, GitHub).
  - Multi-anchor scoring algorithm with Jaro-Winkler similarity and surname disambiguation.
- **Google Account Information Extractor (GAIE)**:
  - Discovers verified full names, GAIA IDs, and profile avatars for `@gmail.com` and Google Workspace accounts.
  - Queries Google's internal People APIs concurrently in Phase 1 with 0ms added latency.
  - Routes single requests through residential proxy pool to eliminate rate-limiting.
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

- **Backend**: Python 3.11+, FastAPI, `httpx`, `aiosqlite`, `dnspython`, `beautifulsoup4`, `playwright`, `ghunt`.
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

Fill in your configuration in `.env`:
- `SPOTIFY_SP_DC`: Your Spotify `sp_dc` cookie from browser DevTools (Application > Cookies > open.spotify.com).
- `PROXY_USERNAME`, `PROXY_PASSWORD`, `PROXY_IPS`: Your residential proxy pool.
- `GITHUB_TOKEN`: (Optional) Increases GitHub API rate limit.

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
