"""Step 3 (second attempt): get one real page of Etimad tender data.

First attempt failed in a useful way: the browser earned 10 cookies, handed them
to a plain script, and Etimad rejected it outright. The pass is bound to the
browser itself, not just to the cookies. So the fetch must happen INSIDE the
browser - which is exactly what Etimad's own page does.

This step only LOOKS. It stores nothing. Its job is to reveal what fields
Etimad actually gives us per tender.

Run:
  pip install playwright
  playwright install --with-deps chromium
  python fetch_sample.py
"""
from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

GATE_PAGE = "https://tenders.etimad.sa/Tender/AllTendersForVisitor"
# Exactly the shape the page itself used, only asking for more per page.
DATA_PATH = (
    "/Tender/AllSupplierTendersForVisitorAsync"
    "?PageSize=24&PublishDateId=5&pageNumber=1"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# JavaScript run inside the loaded page, so the request carries the page's own
# identity - same connection, same cookies, same fingerprint.
IN_PAGE_FETCH = """
async (path) => {
  const r = await fetch(path, {
    headers: { 'X-Requested-With': 'XMLHttpRequest',
               'Accept': 'application/json, text/javascript, */*; q=0.01' },
    credentials: 'include'
  });
  return { status: r.status,
           contentType: r.headers.get('content-type') || '',
           body: await r.text() };
}
"""


def describe(obj, depth: int = 0, out: list[str] | None = None) -> list[str]:
    out = out if out is not None else []
    pad = "  " * depth
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                out.append(f"{pad}{k}: {type(v).__name__}")
                if depth < 2:
                    describe(v, depth + 1, out)
            else:
                out.append(f"{pad}{k}: {type(v).__name__} = {str(v)[:70]}")
    elif isinstance(obj, list):
        out.append(f"{pad}[{len(obj)} items]")
        if obj and depth < 2:
            describe(obj[0], depth + 1, out)
    return out


def find_records(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "items", "tenders", "result", "Data", "Items"):
            if isinstance(data.get(key), list) and data[key]:
                return data[key]
        # fall back to the first non-empty list of dicts anywhere on top level
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return None


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="ar-SA", user_agent=USER_AGENT, viewport={"width": 1366, "height": 900}
        )
        page = ctx.new_page()

        page.goto(GATE_PAGE, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(12_000)  # let the challenge clear
        print(f"gate page title: {page.title()!r}")

        res = page.evaluate(IN_PAGE_FETCH, DATA_PATH)
        browser.close()

    print(f"\ndata request: {res['status']} {res['contentType']} {len(res['body'])} chars")

    body = res["body"]
    if "Request Rejected" in body or "support ID" in body:
        print("\nStill rejected even from inside the page. First 500 characters:")
        print(body[:500])
        return 0

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print("\nNot JSON. This is probably an HTML fragment for the table.")
        print("First 1500 characters so we can see its structure:\n")
        print(body[:1500])
        return 0

    print("\n--- SHAPE OF THE RESPONSE ---")
    for line in describe(data):
        print(line)

    records = find_records(data)
    if records:
        print(f"\n--- ONE FULL RECORD (of {len(records)} on this page) ---")
        print(json.dumps(records[0], ensure_ascii=False, indent=2)[:4000])
        print("\n--- FIELD NAMES ---")
        if isinstance(records[0], dict):
            for k in sorted(records[0].keys()):
                print(k)
    else:
        print("\n(could not spot the list of tenders - see the shape above)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
