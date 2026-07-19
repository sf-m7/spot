"""Step 3: get one real page of Etimad tender data and show its shape.

Confirmed by probe #2: a real browser passes Etimad's challenge from GitHub's
free machines, and the page loads its data from
  /Tender/AllSupplierTendersForVisitorAsync

So: open a browser once to earn the pass, hand the pass to a plain fast
request, and read the data. Browser for the doorman, script for the shopping.

This step only LOOKS. It stores nothing. Its whole job is to tell us what
fields Etimad actually provides, so the real scraper is written against
reality instead of guesses.

Run:
  pip install playwright httpx
  playwright install --with-deps chromium
  python fetch_sample.py
"""
from __future__ import annotations

import json
import sys

import httpx
from playwright.sync_api import sync_playwright

GATE_PAGE = "https://tenders.etimad.sa/Tender/AllTendersForVisitor"
DATA_URL = (
    "https://tenders.etimad.sa/Tender/AllSupplierTendersForVisitorAsync"
    "?PageSize=24&PublishDateId=5&pageNumber=1"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def earn_pass() -> dict[str, str]:
    """Open a browser, let it clear the challenge, return the cookies it earned."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="ar-SA", user_agent=USER_AGENT, viewport={"width": 1366, "height": 900}
        )
        page = ctx.new_page()
        # 'domcontentloaded', not 'networkidle' - the home page never goes idle
        # (that is what timed out in probe #2).
        page.goto(GATE_PAGE, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(12_000)  # let the challenge finish and redirect
        print(f"gate page title: {page.title()!r}")
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        browser.close()
    print(f"cookies earned: {len(cookies)} -> {sorted(cookies)}")
    return cookies


def describe(obj, path: str = "", depth: int = 0, out: list[str] | None = None) -> list[str]:
    """Print the shape of the response without dumping all of it."""
    out = out if out is not None else []
    pad = "  " * depth
    if isinstance(obj, dict):
        for k, v in obj.items():
            kind = type(v).__name__
            if isinstance(v, (dict, list)):
                out.append(f"{pad}{k}: {kind}")
                if depth < 2:
                    describe(v, f"{path}.{k}", depth + 1, out)
            else:
                preview = str(v)[:70]
                out.append(f"{pad}{k}: {kind} = {preview}")
    elif isinstance(obj, list):
        out.append(f"{pad}[{len(obj)} items]")
        if obj and depth < 2:
            describe(obj[0], path + "[0]", depth + 1, out)
    return out


def main() -> int:
    cookies = earn_pass()
    if not cookies:
        print("No cookies earned - cannot continue.")
        return 0

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ar,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": GATE_PAGE,
    }

    resp = httpx.get(DATA_URL, headers=headers, cookies=cookies, timeout=60, follow_redirects=True)
    ctype = resp.headers.get("content-type", "?")
    print(f"\ndata request: {resp.status_code} {ctype} {len(resp.content)} bytes")

    if "json" not in ctype:
        print("\nNot JSON - the pass did not carry over. First 800 characters:")
        print(resp.text[:800])
        return 0

    data = resp.json()
    print("\n--- SHAPE OF THE RESPONSE ---")
    for line in describe(data):
        print(line)

    # Find the list of tenders wherever it lives and show one in full.
    records = None
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        for key in ("data", "items", "tenders", "result"):
            if isinstance(data.get(key), list):
                records = data[key]
                break

    if records:
        print(f"\n--- ONE FULL RECORD (of {len(records)} on this page) ---")
        print(json.dumps(records[0], ensure_ascii=False, indent=2)[:4000])
    else:
        print("\n(could not spot the list of tenders - see the shape above)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
