# Developer Operations & Execution Guide

This document outlines environment setup, local execution, diagnostic commands, and test suite procedures for developers and AI agents working on `EmailLookup`.

---

## 1. Environment Setup

### System Requirements
- Python 3.11 or higher
- Git
- SearXNG Docker instance (running locally on port 8888 or remote)

### Installation Steps

```bash
# 1. Create Python virtual environment
python -m venv .venv

# 2. Activate virtual environment
# Windows (PowerShell / CMD):
.\.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# 3. Install backend dependencies
pip install -r requirements.txt
```

---

## 2. Local Execution

Run the FastAPI application locally with auto-reload enabled:

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

- **Frontend Interface**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive OpenAPI Specs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 3. SearXNG & Proxy Configuration

SearXNG provides fast multi-engine meta-search over rotated datacenter/residential proxies without getting blocked.

### Starting SearXNG
```bash
docker run -d -p 8888:8080 -v ${PWD}/searxng:/etc/searxng searxng/searxng:latest
```

### Environment Variables
Configure your `.env` with:
```ini
SEARXNG_URL=http://localhost:8888/search
PROXY_USERNAME=your_username
PROXY_PASSWORD=your_password
PROXY_IPS=ip1:port,ip2:port
GOOGLE_API_KEY=your_key_here
GOOGLE_CSE_ID=your_cse_id_here
```

---

## 4. Port 25 Diagnostic Verification

The SMTP verifier relies on outbound TCP connectivity to Port 25. Many consumer ISPs block Port 25 by default.

### Quick Port 25 Test Script

Run this inline command in Python to test if outbound Port 25 is accessible:

```python
import socket
s = socket.socket()
s.settimeout(5)
res = s.connect_ex(("aspmx.l.google.com", 25))
print("OPEN (Full SMTP Verification available)" if res == 0 else "BLOCKED by ISP")
s.close()
```

You can also call the API endpoint:
```bash
curl http://127.0.0.1:8000/api/port-check
```

---

## 5. Cache Management & API Endpoints

### Cache Database Location
The SQLite cache database is auto-created at `data/cache.db` with WAL mode enabled.

### Invalidate Cache Entry
To force a fresh live lookup and bypass cached data for a specific email address, issue a POST request to `/api/cache/invalidate`:

```bash
curl -X POST "http://127.0.0.1:8000/api/cache/invalidate" \
     -H "Content-Type: application/json" \
     -d '{"email": "user@example.com"}'
```

---

## 6. Running Automated Tests

Run the test suite to verify lookup engine accuracy and candidate resolution:

```bash
python tests/test_lookup.py
```
