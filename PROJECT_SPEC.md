# Email Lookup Tool — Project Specification & Architecture Blueprint

This document is the **master technical specification** for the `EmailLookup` application. It provides a complete reference for the architecture, data schemas, pipeline mechanics, candidate scoring algorithms, and database storage.

---

## 1. System Overview

`EmailLookup` is a web-based intelligence and email validation application. It has two main capabilities:

1. **Reverse Email Lookup**: Discovers publicly available details associated with any email address (Full Name, Avatar, GitHub profile, LinkedIn profile, Bio, Platform presence across 30+ services, data breaches, and social candidates).
2. **SMTP Email Verifier**: Validates deliverability via direct SMTP handshakes, catch-all server detection, MX provider identification, and port checking.

---

## 2. Codebase Structure & Pipeline Overview

The core processing logic is located in the following backend files:

| Component / File | Primary Purpose | Pipeline Role |
| :--- | :--- | :--- |
| **`backend/lookup_engine.py`** | **Master Reverse Lookup Pipeline** | Orchestrates concurrent data harvesting from Gravatar, GitHub, search engines, and platform checkers; merges and disambiguates person profiles. |
| **`backend/social_finder.py`** | **Social Candidate Finder & Scoring** | Executes targeted queries for social media handles (Instagram, LinkedIn, Twitter/X, etc.), scores candidates against name/email stems, and filters out false positives. |
| **`backend/smtp_verifier.py`** | **SMTP Verification Handshake** | Performs MX DNS queries, opens socket connections to mail servers, sends `HELO`/`MAIL FROM`/`RCPT TO` commands, and detects catch-all configurations. |
| **`backend/platform_checker.py`** | **Account Existence Detector** | Performs silent account existence checks across 30+ platforms (Holehe method). |
| **`backend/cache.py`** | **SQLite Persistent Cache** | Handles high-performance asynchronous storage (`aiosqlite`) with WAL mode for lookups and verifications. |
| **`backend/models.py`** | **Data Models & Contracts** | Defines Pydantic data schemas for requests and responses. |
| **`backend/main.py`** | **FastAPI Web Service** | Exposes REST API endpoints and serves the static frontend UI. |

---

## 3. Detailed Data Pipeline Mechanics

### A. Reverse Lookup Pipeline (`backend/lookup_engine.py`)

When a request arrives at `POST /api/lookup`:

```
                 ┌──────────────────────────────────────┐
                 │         User Input (Email)           │
                 └──────────────────┬───────────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │  Cache Check (24h)  │
                         └──────────┬──────────┘
                                    │ (Miss or force_refresh)
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
┌─────────────┐             ┌──────────────┐             ┌──────────────┐
│  Gravatar   │             │ GitHub Search│             │ Platform     │
│ SHA256 API  │             │ & Commits    │             │ Checks (30+) │
└──────┬──────┘             └──────┬───────┘             └──────┬───────┘
       │                           │                            │
       └───────────────────────────┼────────────────────────────┘
                                   │
                                   ▼
                   ┌──────────────────────────────┐
                   │    Social Candidate Finder   │
                   │ (`backend/social_finder.py`) │
                   └───────────────┬──────────────┘
                                   │
                                   ▼
                   ┌──────────────────────────────┐
                   │  Merging & Disambiguation    │
                   │  - Full-Name Corroboration   │
                   │  - Surname/Given Name Caps   │
                   └───────────────┬──────────────┘
                                   │
                                   ▼
                   ┌──────────────────────────────┐
                   │    Structured Output JSON    │
                   └──────────────────────────────┘
```

1. **Email Syntax & Typo Detection**: Validates email format using regex and corrects common TLD or domain typos (e.g. `gmai.com` -> `gmail.com`).
2. **Gravatar Lookup**: Hashes the email using SHA-256 to query Gravatar profile data (Name, Avatar URL, Bio, linked accounts).
3. **GitHub Harvest**: Searches GitHub by email and commit author history to extract username, avatar, repositories, follower counts, and location.
4. **Social Candidate Discovery (`social_finder.py`)**:
   - Generates name & email stem variants (e.g., `saadasif`, `saad.asif`, `.v2`, `_09`).
   - Strips bare single-token surnames to prevent search noise.
   - Searches public platform indexes and parses profile candidates.
5. **Score & Penalty Filtering**:
   - Scores candidates based on stem matches, full-name overlap, and location consistency.
   - **Conflicting Given Name Penalty**: If a candidate shares a surname (e.g. `Rauf`) but has a completely different given name (e.g., `Haris` vs `Dameesha`), its score is capped at 15% with a reason note (`Conflicting given name`), suppressing false positives.
   - **LinkedIn Full-Name Upgrade**: Upgrades candidate display names when verified via LinkedIn profile corroboration.

---

### B. Verification Pipeline (`backend/smtp_verifier.py`)

When a request arrives at `POST /api/verify`:

1. **Syntax Check**: Validates RFC email syntax.
2. **MX Record Resolution**: Queries DNS for the target domain's MX records to identify mail providers (Google Workspaces, Outlook, ProtonMail, custom).
3. **Outbound Port 25 Check**: Tests socket connectivity to the target MX server on Port 25.
4. **SMTP Handshake**:
   - Connects to MX server.
   - Issues `HELO`/`EHLO` command using configured hostname.
   - Sends `MAIL FROM: <sender>` and `RCPT TO: <target_email>`.
   - Analyzes response codes: `250` = Valid, `550`/`551`/`553` = Invalid address.
5. **Catch-All Detection**: Tests a random fake email address on the domain (e.g., `random_xyz987654@domain.com`). If the server accepts it with `250`, the domain is flagged as `Catch-All`.

---

## 4. Database Schema (`data/cache.db`)

Managed by SQLite via `aiosqlite` in `backend/cache.py` with `WAL` journal mode enabled.

```sql
CREATE TABLE IF NOT EXISTS lookup_cache (
    email TEXT PRIMARY KEY,
    result TEXT NOT NULL,       -- Full JSON serialized LookupResponse
    cached_at INTEGER NOT NULL  -- Unix timestamp in seconds
);

CREATE TABLE IF NOT EXISTS verify_cache (
    email TEXT PRIMARY KEY,
    result TEXT NOT NULL,       -- Full JSON serialized VerifyResponse
    cached_at INTEGER NOT NULL  -- Unix timestamp in seconds
);
```

---

## 5. API Data Models & Response Contracts

Defined in `backend/models.py`:

- **`LookupResponse`**:
  - `email`: `str`
  - `person`: `PersonInfo` (name, avatar, bio, location, website)
  - `profiles`: `dict` (github, linkedin, etc.)
  - `platforms`: `List[PlatformResult]` (30+ check results)
  - `social_candidates`: `List[dict]` (ranked candidate profiles)
  - `social_candidates_by_platform`: `dict`
  - `cached`: `bool`
- **`VerifyResponse`**:
  - `email`: `str`
  - `valid`: `Optional[bool]`
  - `catchall`: `Optional[bool]`
  - `mx_provider`: `Optional[str]`
  - `confidence`: `Optional[int]`
  - `port25_available`: `bool`

---

## 6. Development & Operations Guidelines

- All backend routes are hosted via FastAPI in `backend/main.py`.
- Static files for the user interface are served directly from `frontend/`.
- Automated test coverage is located in `tests/test_lookup.py`.
