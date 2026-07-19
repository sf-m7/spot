"""Step 3 (third attempt): read Etimad's own data call instead of inventing one.

Attempt 2 failed because I altered the request (PageSize=24, dropped the
cache-buster) and Etimad's firewall rejected the unfamiliar shape - a different
refusal from the human-check page.

So: load the page, let it make its normal call, and read the reply as it
arrives. That call is already known to succeed. Then, separately, test how far
the request can be bent - which decides whether bulk collection is possible or
whether we are stuck at six tenders a click.

Stores nothing. Looking only.
"""
from __future__ import annotations

import json
import re
import sys

from playwright.sync_api import sync_playwright

GATE_PAGE = "https://tenders.etimad.sa/Tender/AllTendersForVisitor"
TARGET = "AllSupplierTendersForVisitorAsync"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

IN_PAGE_FETCH = """
async (path) => {
  const r = await fetch(path, {
    headers: { 'X-Requested-With': 'XMLHttpRequest',
               'Accept': 'application/json, text/javascript, */*; q=0.01' },
    credentials: 'include'
  });
  const body = await r.text();
  return { status: r.status,
           contentType: r.headers.get('content-type') || '',
           rejected: body.includes('Request Rejected'),
           length: body.length,
           body: body.slice(0, 400000) };
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
            v = data.get(key)
            if isinstance(v, list) and v:
                return v
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return None


def report(label: str, body: str) -> None:
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print("Not JSON - looks like HTML markup. First 1200 characters:\n")
        print(body[:1200])
        return

    print("--- SHAPE ---")
    for line in describe(data):
        print(line)

    records = find_records(data)
    if records and isinstance(records[0], dict):
        print(f"\n--- FIELD NAMES ({len(records)} records on this page) ---")
        for k in sorted(records[0].keys()):
            print(f"  {k}")
        print("\n--- ONE FULL RECORD ---")
        print(json.dumps(records[0], ensure_ascii=False, indent=2)[:4000])
    else:
        print("\n(no obvious record list - see shape above)")


def main() -> int:
    captured: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="ar-SA", user_agent=USER_AGENT, viewport={"width": 1366, "height": 900}
        )
        page = ctx.new_page()

        def on_response(resp):
            if TARGET in resp.url:
                try:
                    captured.append((resp.url, resp.text()))
                except Exception as exc:  # noqa: BLE001
                    print(f"(could not read body of {resp.url}: {exc})")

        page.on("response", on_response)

        page.goto(GATE_PAGE, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(15_000)
        print(f"gate page title: {page.title()!r}")
        print(f"captured {len(captured)} data replies from the page's own request")

        # --- pagination probe: bend the page's own URL, one change at a time ---
        variants: list[tuple[str, str]] = []
        if captured:
            base = captured[0][0].split("tenders.etimad.sa")[-1]
            print(f"\nbase request the page used:\n  {base}")
            variants = [
                ("same URL again", base),
                ("page 2", re.sub(r"pageNumber=\d+", "pageNumber=2", base)),
                ("50 per page", re.sub(r"PageSize=\d+", "PageSize=50", base)),
                ("no date filter", re.sub(r"&?PublishDateId=\d+", "", base)),
            ]

        probe_results = []
        for label, url in variants:
            try:
                res = page.evaluate(IN_PAGE_FETCH, url)
                verdict = (
                    "REJECTED" if res["rejected"]
                    else f"OK {res['status']} {res['contentType'].split(';')[0]} {res['length']} chars"
                )
            except Exception as exc:  # noqa: BLE001
                verdict, res = f"ERROR {type(exc).__name__}", None
            probe_results.append((label, verdict, res))
            page.wait_for_timeout(3000)

        browser.close()

    if captured:
        report("THE PAGE'S OWN DATA (this is what we can definitely read)", captured[0][1])
    else:
        print("\nNo data reply captured. The page may render its table server-side.")

    print(f"\n{'=' * 60}\nHOW FAR THE REQUEST CAN BE BENT\n{'=' * 60}")
    for label, verdict, _ in probe_results:
        print(f"{label:<18} {verdict}")

    ok_bends = [lbl for lbl, v, _ in probe_results if v.startswith("OK")]
    print()
    if any(lbl in ("page 2", "50 per page", "no date filter") for lbl in ok_bends):
        print("Bulk collection is possible - we can walk through pages.")
    elif "same URL again" in ok_bends:
        print("We can repeat the exact call but not change it.")
        print("Bulk collection would mean clicking through pages like a person.")
    else:
        print("Even repeating the page's own call is refused.")
        print("Only what the page loads by itself is readable.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
