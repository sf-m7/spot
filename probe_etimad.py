"""Etimad access probe - standalone, no imports from other project files.

Answers one question: can a free GitHub Actions machine read Etimad, or does a
bot-defence wall stand in the way?

Run:  python probe_etimad.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

import httpx

SUPABASE_URL = os.environ.get("SPOT_SUPABASE_URL") or "https://wlnjdhgighoudrzoddyq.supabase.co"
SUPABASE_KEY = os.environ.get("SPOT_SUPABASE_SERVICE_KEY") or ""

DELAY_SECONDS = 3.0
TIMEOUT_SECONDS = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

CANDIDATES: list[tuple[str, str]] = [
    ("root", "https://tenders.etimad.sa/"),
    ("list_html", "https://tenders.etimad.sa/Tender/AllTendersForVisitor"),
    ("list_json", "https://tenders.etimad.sa/Tender/AllTendersForVisitorAsync?PageSize=6&PageNumber=1"),
    ("supplier_json", "https://tenders.etimad.sa/Tender/AllSupplierTendersForVisitorAsync?PageSize=6&PageNumber=1"),
    ("awards_html", "https://tenders.etimad.sa/Tender/AllAwardedTendersForVisitor"),
]

BLOCK_MARKERS = (
    "support id",
    "this question is for testing whether you are a human",
    "/tspd/",
    "captcha",
    "the requested url was rejected",
)


def classify(resp: httpx.Response) -> str:
    body = resp.text[:20000].lower()
    if any(m in body for m in BLOCK_MARKERS):
        return "BLOCKED"
    if resp.status_code == 404:
        return "NOT_FOUND"
    if resp.status_code >= 500:
        return "SERVER_ERROR"
    if resp.status_code != 200:
        return f"HTTP_{resp.status_code}"
    if "json" in resp.headers.get("content-type", ""):
        return "OK_JSON"
    if len(resp.text) < 2000:
        return "OK_BUT_TINY"
    return "OK_HTML"


def log_to_supabase(lines: list[str], reachable: bool) -> None:
    """Best effort. A logging failure must never hide the probe result."""
    if not SUPABASE_KEY:
        print("\n(no database key set - results printed only, not saved)")
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/scrape_run",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={
                "job": "probe_etimad",
                "finished_at": now,
                "status": "ok" if reachable else "empty",
                "rows_seen": len(lines),
                "notes": "\n".join(lines),
            },
            timeout=TIMEOUT_SECONDS,
        ).raise_for_status()
        print("\n(results saved to the database)")
    except Exception as exc:  # noqa: BLE001
        print(f"\n(could not save to database: {type(exc).__name__}: {exc})")


def main() -> int:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ar,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }
    lines: list[str] = []

    with httpx.Client(headers=headers, timeout=TIMEOUT_SECONDS, follow_redirects=True) as http:
        for name, url in CANDIDATES:
            try:
                resp = http.get(url)
                verdict = classify(resp)
                detail = (
                    f"{resp.status_code} "
                    f"{resp.headers.get('content-type', '?').split(';')[0]} "
                    f"{len(resp.content)} bytes"
                )
            except Exception as exc:  # noqa: BLE001
                verdict, detail = "CONNECT_FAILED", f"{type(exc).__name__}: {exc}"

            line = f"{name:<15} {verdict:<15} {detail}"
            lines.append(line)
            print(line, flush=True)
            time.sleep(DELAY_SECONDS)

    reachable = [ln.split()[0] for ln in lines if " OK" in ln]

    print("\n" + "=" * 60)
    if reachable:
        print("RESULT: WE CAN READ ETIMAD from this machine.")
        print("Working entry points: " + ", ".join(reachable))
        print("Next step: build the real scraper. No proxy cost.")
    else:
        print("RESULT: BLOCKED. Etimad refused every entry point.")
        print("The 'Spot runs for free' assumption does not hold.")
        print("Next step: decide whether to pay for proxies, or stop.")
    print("=" * 60)

    log_to_supabase(lines, bool(reachable))
    return 0  # always green: the printed result is the answer, not the exit code


if __name__ == "__main__":
    sys.exit(main())
