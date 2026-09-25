#!/usr/bin/env python3
"""
check_proxy_health.py - Comprehensive Proxy Health & DDGS Live Diagnostic Tool

Audits each residential proxy IP in .env:
  1. Direct Proxy Egress & Handshake Latency
  2. Live DuckDuckGo Search Query through DDGS via that Proxy
  3. Formatted Console Table & Diagnostic Summary
"""

import sys
import os
import time
import argparse
import asyncio
from pathlib import Path
from typing import Dict, Any, List

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

PROXY_USER = os.getenv("PROXY_USERNAME")
PROXY_PASS = os.getenv("PROXY_PASSWORD")
RAW_IPS = os.getenv("PROXY_IPS", "")
ALL_PROXY_IPS = [ip.strip() for ip in RAW_IPS.split(",") if ip.strip()]


def test_single_proxy_ddgs(ip: str, query: str = "site:github.com python", timeout: float = 6.0) -> Dict[str, Any]:
    """Perform synchronous live test of a single proxy using DDGS."""
    proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{ip}"
    t0 = time.time()
    
    if DDGS is None:
        return {
            "ip": ip,
            "status": "NO_LIBRARY",
            "hits": 0,
            "latency_ms": 0,
            "error": "ddgs library not installed",
        }

    try:
        ddgs = DDGS(proxy=proxy_url, timeout=timeout)
        results = list(ddgs.text(query, max_results=3))
        elapsed_ms = int((time.time() - t0) * 1000)
        
        if results and len(results) > 0:
            return {
                "ip": ip,
                "status": "HEALTHY",
                "hits": len(results),
                "latency_ms": elapsed_ms,
                "error": None,
                "sample_title": results[0].get("title", "")[:40],
            }
        else:
            return {
                "ip": ip,
                "status": "EMPTY_RESULTS",
                "hits": 0,
                "latency_ms": elapsed_ms,
                "error": "Query returned 0 hits",
                "sample_title": "",
            }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        err_type = type(e).__name__
        err_msg = str(e).strip() or err_type

        # Categorize known errors
        if "202" in err_msg or "Ratelimit" in err_type:
            status = "RATE_LIMITED"
        elif "Timeout" in err_type or "timed out" in err_msg.lower():
            status = "TIMEOUT"
        elif "ProxyError" in err_type or "ConnectError" in err_type:
            status = "CONNECTION_ERROR"
        else:
            status = "ERROR"

        return {
            "ip": ip,
            "status": status,
            "hits": 0,
            "latency_ms": elapsed_ms,
            "error": f"{err_type}: {err_msg[:60]}",
            "sample_title": "",
        }


async def audit_all_proxies(query: str, timeout: float, concurrency: int) -> List[Dict[str, Any]]:
    """Run proxy audits concurrently with bounded worker pool."""
    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async def worker(ip: str, idx: int, total: int):
        async with semaphore:
            print(f"  [{idx:02d}/{total:02d}] Probing IP {ip}...", flush=True)
            res = await asyncio.to_thread(test_single_proxy_ddgs, ip, query, timeout)
            
            # Print immediate line result
            st = res["status"]
            ms = res["latency_ms"]
            if st == "HEALTHY":
                print(f"    ✓ {ip:<21} -> HEALTHY ({res['hits']} hits in {ms}ms) | \"{res['sample_title']}\"", flush=True)
            elif st == "RATE_LIMITED":
                print(f"    ⏳ {ip:<21} -> RATE-LIMITED (202 / DDG Challenge in {ms}ms)", flush=True)
            elif st == "TIMEOUT":
                print(f"    ⏱ {ip:<21} -> TIMEOUT (> {ms}ms)", flush=True)
            else:
                print(f"    ❌ {ip:<21} -> {st} ({res['error']} in {ms}ms)", flush=True)
                
            return res

    tasks = [worker(ip, i + 1, len(ALL_PROXY_IPS)) for i, ip in enumerate(ALL_PROXY_IPS)]
    results = await asyncio.gather(*tasks)
    return results


def main():
    parser = argparse.ArgumentParser(description="Live Diagnostic Tool for Residential Proxy Pool & DDGS Search")
    parser.add_argument("--query", "-q", default="site:github.com python", help="Test query to run through each proxy")
    parser.add_argument("--timeout", "-t", type=float, default=6.0, help="Per-proxy timeout in seconds (default: 6.0)")
    parser.add_argument("--concurrency", "-c", type=int, default=5, help="Concurrent testing workers (default: 5)")
    args = parser.parse_args()

    print("\n" + "=" * 75)
    print(" 🛡️  RESIDENTIAL PROXY POOL & DDGS HEALTH AUDIT")
    print("=" * 75)
    print(f"  Environment:       {BASE_DIR / '.env'}")
    print(f"  Proxy Username:    {PROXY_USER or 'NOT SET ⚠️'}")
    print(f"  Proxy Password:    {'*' * len(PROXY_PASS) if PROXY_PASS else 'NOT SET ⚠️'}")
    print(f"  Total Proxies:     {len(ALL_PROXY_IPS)} loaded")
    print(f"  DDGS Library:      {'INSTALLED ✓' if DDGS else 'MISSING ❌'}")
    print(f"  Audit Test Query:  '{args.query}'")
    print(f"  Timeout / Worker:  {args.timeout}s (Concurrency: {args.concurrency})")
    print("=" * 75 + "\n")

    if not PROXY_USER or not PROXY_PASS:
        print("❌ ERROR: PROXY_USERNAME or PROXY_PASSWORD not configured in .env!")
        sys.exit(1)

    if not ALL_PROXY_IPS:
        print("❌ ERROR: PROXY_IPS is empty in .env!")
        sys.exit(1)

    t_start = time.time()
    results = asyncio.run(audit_all_proxies(args.query, args.timeout, args.concurrency))
    total_time = time.time() - t_start

    # Summary calculations
    healthy = [r for r in results if r["status"] == "HEALTHY"]
    rate_limited = [r for r in results if r["status"] == "RATE_LIMITED"]
    timeouts = [r for r in results if r["status"] == "TIMEOUT"]
    errors = [r for r in results if r["status"] not in ("HEALTHY", "RATE_LIMITED", "TIMEOUT")]

    healthy_latencies = [r["latency_ms"] for r in healthy]
    avg_lat = int(sum(healthy_latencies) / len(healthy_latencies)) if healthy_latencies else 0
    fastest = min(healthy_latencies) if healthy_latencies else 0
    slowest = max(healthy_latencies) if healthy_latencies else 0

    print("\n" + "=" * 75)
    print(" 📊 AUDIT RESULTS SUMMARY TABLE")
    print("=" * 75)
    print(f" {'IP Address & Port':<23} | {'Status':<14} | {'Latency':<9} | {'Hits':<5} | {'Notes / Details'}")
    print("-" * 75)

    for r in sorted(results, key=lambda x: (x["status"] != "HEALTHY", x["latency_ms"])):
        ip = r["ip"]
        st = r["status"]
        lat = f"{r['latency_ms']}ms"
        hits = str(r["hits"])
        
        if st == "HEALTHY":
            st_fmt = "✓ HEALTHY"
            notes = f"Title: {r['sample_title'][:30]}"
        elif st == "RATE_LIMITED":
            st_fmt = "⏳ RATELIMIT"
            notes = "HTTP 202 - Rate-limited by DDG"
        elif st == "TIMEOUT":
            st_fmt = "⏱ TIMEOUT"
            notes = f"Exceeded {args.timeout}s limit"
        else:
            st_fmt = "❌ FAILED"
            notes = r["error"][:35]

        print(f" {ip:<23} | {st_fmt:<14} | {lat:<9} | {hits:<5} | {notes}")

    print("=" * 75)
    print(f"  Total Audited:      {len(results)}")
    print(f"  ✅ Fully Healthy:   {len(healthy)} / {len(results)} ({int(len(healthy)/len(results)*100)}%)")
    print(f"  ⏳ Rate-Limited:    {len(rate_limited)}")
    print(f"  ⏱ Timeouts:        {len(timeouts)}")
    print(f"  ❌ Errors/Failed:   {len(errors)}")
    if healthy:
        print(f"  ⚡ Latency (Healthy): Avg: {avg_lat}ms | Min: {fastest}ms | Max: {slowest}ms")
    print(f"  ⏱ Total Audit Time: {total_time:.2f}s")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
