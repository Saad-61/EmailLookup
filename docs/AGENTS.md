# AI Agent Guidelines & Coding Standards

This file contains rules, standards, and workflow instructions for AI agents working on the `EmailLookup` codebase.

---

## 1. Primary Mandates

1. **Do Not Infer Logic or Schemas**: Always inspect `backend/models.py`, `backend/lookup_engine.py`, and `docs/PROJECT_SPEC.md` before adding or modifying API endpoints or lookup functions.
2. **Preserve Existing Signatures**: If modifying functions in `lookup_engine.py` or `social_finder.py`, update all call sites across `backend/main.py` and `tests/`.
3. **No Hidden Exceptions**: Scrapers and search probes must never swallow exceptions silently. Log error tracebacks and return structured error objects.
4. **No Environment Dependencies**: Code must execute seamlessly on both Windows and Linux environments.

---

## 2. Code Style & Architecture Conventions

### Python Backend Standards
- **Asynchronous I/O**: Use `async`/`await` for network requests (`httpx`) and database operations (`aiosqlite`).
- **Thread Delegation**: Wrap synchronous blocking calls (such as socket SMTP checks or DNS queries) in `asyncio.to_thread()`.
- **Strict Typing**: Use Pydantic models from `backend/models.py` for API requests and responses. Add type hints to all new backend helper functions.
- **Path Handling**: Always use `pathlib.Path` or `os.path.join(os.path.dirname(__file__), ...)` to build paths relative to project subdirectories.

### Database & Caching Rules
- Use `backend/cache.py` for all caching logic.
- Ensure database connections open with `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=30000;`.
- Never modify `data/cache.db` directly without using `aiosqlite` transactions.

---

## 3. Disambiguation & Social Search Guidelines

When modifying `backend/social_finder.py` or `backend/lookup_engine.py`:

1. **Conflicting Given Name Rule**: When matching candidate profiles, if a surname matches (e.g. `Hameed`) but the given name conflicts (e.g. `Atisam` vs `Haseeb`), enforce candidate score capping (`score = min(score, 15)`) to prevent false positives.
2. **Jaro-Winkler Similarity**: Use `jaro_winkler_similarity(s1, s2)` for fuzzy name matching ($\ge 88\%$) to accommodate spelling transliterations (e.g. `Nouman` ~ `Noman`, `Muhammad` ~ `Mohammad`).
3. **Short Handle Stems**: Prioritize single-token short stems (`len <= 10`) for versioned candidate generation (`.v2`, `.v3`, `_09`).
4. **Exclude Bare Surnames**: Do not include bare single-token surnames in general multi-keyword handle searches to prevent search query dilution.
5. **Direct Probing**: Use crawler User-Agents (`facebookexternalhit/1.1`) for direct OpenGraph metadata extraction on Instagram, TikTok, and Pinterest.

---

## 4. Verification & Testing Instructions

After making any changes to `backend/`:

1. **Run Automated Test Suite**:
   ```bash
   python tests/test_lookup.py
   ```
2. **Verify Port Check Route**:
   Confirm `/api/port-check` returns structured status without uncaught exception crashes.
3. **Check Cache Invalidation**:
   Ensure invalidation requests through `/api/cache/invalidate` correctly purge entries from `data/cache.db`.
