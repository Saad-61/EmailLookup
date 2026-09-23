# Project Specification & Architecture Blueprint

This document is the **master technical specification** for the `EmailLookup` application. It provides a complete reference for the architecture, data schemas, pipeline mechanics, candidate scoring algorithms, direct probing engines, and database storage.

---

## 1. System Overview

`EmailLookup` is a web-based intelligence and email validation application. It has two main capabilities:

1. **Reverse Email Lookup**: Discovers publicly available details associated with any email address (Full Name, Avatar, GitHub profile, LinkedIn profile, Bio, Platform presence across 30+ services, data breaches, and verified social candidates across LinkedIn, Instagram, X/Twitter, Facebook, TikTok, and Pinterest).
2. **SMTP Email Verifier**: Validates deliverability via direct SMTP handshakes, catch-all server detection, MX provider identification, and port checking.

---

## 2. Codebase Structure & Pipeline Overview

| Component / File | Primary Purpose | Pipeline Role |
| :--- | :--- | :--- |
| **`backend/lookup_engine.py`** | **Master Reverse Lookup Pipeline** | Orchestrates concurrent data harvesting from Gravatar, GitHub, search engines, and platform checkers; merges and disambiguates person profiles. |
| **`backend/social_finder.py`** | **Social Candidate Finder & Probing** | Probes OpenGraph tags directly for Instagram, TikTok, and Pinterest; executes targeted queries via SearXNG / Google CSE, scores candidates with Jaro-Winkler similarity, and eliminates false positives. |
| **`backend/smtp_verifier.py`** | **SMTP Verification Handshake** | Performs MX DNS queries, opens socket connections to mail servers, sends `HELO`/`MAIL FROM`/`RCPT TO` commands, and detects catch-all configurations. |
| **`backend/platform_checker.py`** | **Account Existence Detector** | Performs silent account existence checks across 30+ platforms (Holehe method). |
| **`backend/cache.py`** | **SQLite Persistent Cache** | Handles high-performance asynchronous storage (`aiosqlite`) with WAL mode for lookups and verifications. |
| **`backend/models.py`** | **Data Models & Contracts** | Defines Pydantic data schemas for requests and responses. |
| **`backend/main.py`** | **FastAPI Web Service** | Exposes REST API endpoints and serves the static frontend UI. |

---

## 3. Detailed Data Pipeline Mechanics

### A. Reverse Lookup Pipeline (`backend/lookup_engine.py`)

1. **Base Layer (Fast APIs <1s)**:
   - Queries Gravatar SHA-256 profile hash for avatar, bio, and linked accounts.
   - Queries GitHub user & commit author history for technical identities.
   - Validates domain MX records and corporate workplace DB.

2. **Direct OpenGraph Probers (`social_finder.py`)**:
   - Emulates social crawler headers (`facebookexternalhit/1.1`) over rotating proxy pool.
   - Directly probes **Instagram** (35 handles), **TikTok** (20 handles), and **Pinterest** (20 handles) in <2s with 0 CAPTCHAs.

3. **High-Precision Metasearch (`social_finder.py`)**:
   - Dispatches single clean search strings per platform (LinkedIn, Instagram, X, Facebook) targeting SearXNG/Yandex and Google CSE.

4. **Jaro-Winkler Scoring & Disambiguation**:
   - Matches candidate names using Jaro-Winkler string similarity ($\ge 88\%$) to handle transliterations (e.g. `Nouman` vs `Noman`, `Muhammad` vs `Mohammad`).
   - Caps conflicting given names (e.g. `Atisam` vs `Haseeb`) at 15% to suppress false positives.
