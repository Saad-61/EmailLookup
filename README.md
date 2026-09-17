# Email Lookup Tool

A reverse email lookup tool that finds publicly available information linked to any email address. Also includes an SMTP email verifier.

## Features

- **Reverse Lookup** — enter any email, get: name, avatar, LinkedIn, GitHub, platform presence (13+ platforms), data breach history
- **Email Verifier** — SMTP handshake verification with catch-all detection, MX provider identification, and AbstractAPI fallback when port 25 is blocked
- Results cached in SQLite (24h for lookups, 6h for verifications)

## Setup

### 1. Clone & install dependencies

```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure API keys

Copy `example.env` to `.env` and fill in your keys:

```bash
copy example.env .env   # Windows
cp example.env .env     # Mac/Linux
```

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `GITHUB_TOKEN` | github.com/settings/tokens (no scopes needed) | Strongly recommended |
| `GRAVATAR_API_KEY` | gravatar.com/developers | Optional (increases rate limit) |
| `ABSTRACT_API_KEY` | app.abstractapi.com/api/email-validation | Needed if port 25 is blocked |
| `HIBP_API_KEY` | haveibeenpwned.com/API/Key | Optional (breach lookups) |

### 3. Check if port 25 is blocked (quick test)

```python
import socket
s = socket.socket(); s.settimeout(5)
print("OPEN" if s.connect_ex(("aspmx.l.google.com", 25)) == 0 else "BLOCKED")
s.close()
```

If it prints `BLOCKED`, add an `ABSTRACT_API_KEY` in `.env` for email verification to work.

### 4. Run the server

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Open **http://127.0.0.1:8000** in your browser.

## Project Structure

```
EmailLookup/
├── backend/
│   ├── main.py              # FastAPI server
│   ├── lookup_engine.py     # Gravatar, GitHub, LinkedIn, breach sources
│   ├── smtp_verifier.py     # SMTP verification + port 25 check
│   ├── platform_checker.py  # 13+ platform presence detection
│   ├── models.py            # Pydantic data models
│   ├── cache.py             # SQLite caching layer
│   └── requirements.txt
├── frontend/
│   ├── index.html           # Two-tab UI
│   ├── style.css            # Light mode styles
│   └── app.js               # API fetch + DOM rendering
├── example.env              # API key template
└── README.md
```

## Data Sources

| Source | What we get | Notes |
|--------|------------|-------|
| Gravatar | Name, avatar, bio, linked URLs | Free, 100 req/hr unauthenticated |
| GitHub API | Username, profile, repos, bio | Free, needs token for 5000 req/hr |
| DuckDuckGo | LinkedIn URL | No API key needed |
| Platform checks | Account existence on 13+ platforms | Holehe-style forgot-password probing |
| Have I Been Pwned | Data breach history | Needs API key |

## Notes

- Platform presence checks use the "forgot password" flow technique — no email is sent to the target
- LinkedIn is found via Google dork through DuckDuckGo (no LinkedIn login required)
- Phone numbers are only shown if publicly listed in a GitHub or Gravatar bio
- Address lookups are not supported (requires paid data brokers)
