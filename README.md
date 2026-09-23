# Email Lookup & Verification Tool

A reverse email lookup and SMTP verifier application built with FastAPI, SQLite, and vanilla JS/CSS.

---

## Key Features

- **Reverse Email Lookup**:
  - Discovers full name, avatar, bio, location, and website.
  - Extracts GitHub profiles, repositories, and commit history.
  - Detects account existence across 30+ platforms (Holehe method).
  - Searches and ranks candidate social media profiles (LinkedIn, Instagram, Twitter/X, etc.).
  - Applies given name conflict penalties to prevent false positive matches.
- **SMTP Email Verifier**:
  - Outbound Port 25 availability check.
  - Real-time SMTP handshake verification (`HELO` / `MAIL FROM` / `RCPT TO`).
  - MX provider identification & Catch-all server detection.
- **High Performance Caching**:
  - SQLite persistent cache with WAL mode enabled (`data/cache.db`).
  - Cached lookup results (24h default) with force-refresh and cache invalidation endpoint support.

---

## Technical Stack

- **Backend**: Python 3.11+, FastAPI, `httpx`, `aiosqlite`, `dnspython`, `beautifulsoup4`.
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
```

### 2. Configure Environment

Copy `example.env` to `.env`:

```bash
# On Windows:
copy example.env .env
# On Linux/macOS:
cp example.env .env
```

*(Optional configuration such as `HOST`, `PORT`, and SMTP sender details can be customized in `.env` if needed).*

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
- See **[PROJECT_SPEC.md](PROJECT_SPEC.md)** for master architecture and pipeline details.
- See **[DEVELOPMENT.md](DEVELOPMENT.md)** for developer setup and testing commands.
- See **[AGENTS.md](AGENTS.md)** for AI agent guidelines and code standards.

---

## Testing

Run the automated test suite to check reverse lookup accuracy:

```bash
python tests/test_lookup.py
```
