"""Etimad probe #2 - with a real browser.

Probe #1 was a plain script and got a bot-defence page. That is expected if the
wall is a JavaScript challenge rather than an IP ban. This probe drives an
actual Chrome, which can answer such a challenge, and answers two questions:

  1. Can a free GitHub machine get through to real Etimad content?
  2. Which addresses does the page fetch its data from? (Probe #1's guesses 404'd.)

Run:
  pip install playwright
  playwright install --with-deps chromium
  python probe_browser.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import httpx
from playwright.sync_api import sync_playwright

SUPABASE_URL = os.environ.get("SPOT_SUPABASE_URL") or "https://wlnjdhgighoudrzoddyq.supabase.co"
SUPABASE_KEY = os.environ.get("SPOT_SUPABASE_SERVICE_KEY") or ""

TARGETS = [
    ("home", "https://tenders.etimad.sa/"),
    ("tender_list", "https://tenders.etimad.sa/Tender/AllTendersForVisitor"),
]

BLOCK_MARKERS = (
    "support id",
    "this question is for testing whether you are a human",
    "the requested url was rejected",
)

# Words that only appear once we are looking at genuine tender content.
CONTENT_MARKERS = ("المنافسة", "الجهة", "منافسات", "tender")


def run_target(page, name: str, url: str, seen: list[str]) -> list[str]:
    out: list[str] = []
    try:
        page.goto(url, wait_until="networkidle", timeout=90_000)
    except Exception as exc:  # noqa: BLE001
        out.append(f"{name:<12} NAVIGATION_FAILED  {type(exc).__name__}: {exc}")
        return out

    # Give any challenge time to complete and redirect us to the real page.
    page.wait_for_timeout(8000)

    html = (page.content() or "")
    low = html.lower()
    blocked = any(m in low for m in BLOCK_MARKERS)
    has_content = any(m.lower() in low for m in CONTENT_MARKERS)

    if blocked and not has_content:
        verdict = "STILL_BLOCKED"
    elif has_content:
        verdict = "GOT_THROUGH"
    else:
        verdict = "UNCLEAR"

    out.append(f"{name:<12} {verdict:<15} {len(html)} chars   title={page.title()!r}")

    # Count how many tender rows we can actually see - the honest proof.
    try:
        rows = page.locator("tr").count()
        out.append(f"{'':<12} table rows visible: {rows}")
    except Exception:  # noqa: BLE001
        pass

    return out


def main() -> int:
    lines: list[str] = []
    data_urls: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="ar-SA",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )
        page = ctx.new_page()

        # Record every background data call the page makes. This is how we find
        # the real addresses instead of guessing at them.
        def on_response(resp):
            try:
                ctype = resp.headers.get("content-type", "")
                if "json" in ctype and "etimad" in resp.url:
                    data_urls.append(f"{resp.status} {resp.url}")
            except Exception:  # noqa: BLE001
                pass

        page.on("response", on_response)

        for name, url in TARGETS:
            lines.extend(run_target(page, name, url, data_urls))

        browser.close()

    for ln in lines:
        print(ln, flush=True)

    print("\n--- data addresses the page used ---")
    if data_urls:
        for u in sorted(set(data_urls)):
            print(u)
            lines.append(u)
    else:
        print("(none seen - the page may build its table server-side)")

    got_through = any("GOT_THROUGH" in ln for ln in lines)

    print("\n" + "=" * 60)
    if got_through:
        print("RESULT: A REAL BROWSER GETS THROUGH on GitHub's free machines.")
        print("Meaning: no proxy cost. Scraping is slower but free.")
    else:
        print("RESULT: EVEN A REAL BROWSER IS BLOCKED here.")
        print("Meaning: this is about the machine's address, not JavaScript.")
        print("Now the proxy-cost question is real.")
    print("=" * 60)

    if SUPABASE_KEY:
        try:
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/scrape_run",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={
                    "job": "probe_browser",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "ok" if got_through else "empty",
                    "rows_seen": len(lines),
                    "notes": "\n".join(lines)[:20000],
                },
                timeout=30,
            ).raise_for_status()
            print("\n(results saved to the database)")
        except Exception as exc:  # noqa: BLE001
            print(f"\n(could not save to database: {type(exc).__name__}: {exc})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
