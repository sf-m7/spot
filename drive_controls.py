"""Step 5: drive Etimad's own controls.

Learned in step 4:
  - next page is a button labelled '»' (not the Arabic word I searched for)
  - page size can be set to 24 (7788 tenders -> ~325 rounds, not ~1300)
  - TenderCategory offers 'award stage' (5) and 'award announced' (6)
  - PublishDateId offers 'any time' (1), lifting the 3-month window

We never forge a request. We change the page's own controls and let the page's
own code do the asking - that is the only thing Etimad accepts.

Two parts:
  A. pagination - set 24 per page, click next repeatedly, count what we get
  B. awards    - filter to announced awards, see what an award record contains

Stores nothing. Looking only.
"""
from __future__ import annotations

import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

GATE_PAGE = "https://tenders.etimad.sa/Tender/AllTendersForVisitor"
TARGET = "AllSupplierTendersForVisitorAsync"
CLICKS = 4
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# These dropdowns are styled widgets; the underlying <select> is hidden, so a
# normal click will not work. Set the value and fire the page's own change
# handler - the page then makes the request itself.
SET_SELECT = """
([id, value]) => {
  const el = document.getElementById(id);
  if (!el) return 'no such control';
  el.value = value;
  if (el.value !== value) return 'value not accepted';
  el.dispatchEvent(new Event('change', { bubbles: true }));
  if (window.jQuery) { window.jQuery(el).val(value).trigger('change'); }
  return 'set';
}
"""


def summarise(captures, label):
    ids, total, refused = set(), None, 0
    for _url, body in captures:
        if "Request Rejected" in body:
            refused += 1
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        total = data.get("totalCount", total)
        for rec in data.get("data") or []:
            if isinstance(rec, dict) and rec.get("tenderId"):
                ids.add(rec["tenderId"])
    print(f"\n[{label}] replies={len(captures)} unique tenders={len(ids)} "
          f"totalCount={total} refused={refused}")
    return ids, total


def main() -> int:
    captures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="ar-SA", user_agent=USER_AGENT, viewport={"width": 1366, "height": 1400}
        )
        page = ctx.new_page()
        page.on("response", lambda r: captures.append((r.url, r.text()))
                if TARGET in r.url else None)

        page.goto(GATE_PAGE, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(15_000)
        print(f"gate page title: {page.title()!r}   first captures: {len(captures)}")

        # ---------------- PART A: pagination ----------------
        print("\n" + "=" * 60 + "\nPART A - PAGINATION\n" + "=" * 60)

        r = page.evaluate(SET_SELECT, ["itemsPerPage", "24"])
        print(f"set page size to 24: {r}")
        page.wait_for_timeout(5000)
        print(f"  captures now: {len(captures)}")

        next_btn = page.locator("button.page-link").filter(has_text=re.compile(r"^\s*»\s*$"))
        for i in range(CLICKS):
            before = len(captures)
            try:
                if next_btn.count() == 0:
                    print(f"click {i + 1}: next button vanished - stopping")
                    break
                t0 = time.time()
                next_btn.first.click(timeout=10_000)
            except Exception as exc:  # noqa: BLE001
                print(f"click {i + 1}: failed - {type(exc).__name__}: {exc}")
                break
            page.wait_for_timeout(4000)
            print(f"click {i + 1}: +{len(captures) - before} reply ({time.time() - t0:.1f}s)")

        page_ids, total = summarise(captures, "after pagination")
        for url, _b in captures:
            print("   " + url.split("?")[-1][:90])

        # ---------------- PART B: awards ----------------
        print("\n" + "=" * 60 + "\nPART B - AWARD DATA\n" + "=" * 60)
        award_start = len(captures)

        print("set publish window to 'any time':",
              page.evaluate(SET_SELECT, ["PublishDateId", "1"]))
        page.wait_for_timeout(2500)
        print("set category to 'award announced':",
              page.evaluate(SET_SELECT, ["TenderCategory", "6"]))
        page.wait_for_timeout(5000)

        # A search button may be needed to apply the filters.
        for sel in ["button:has-text('بحث')", "input[type=submit]", "#searchBtn",
                    "button[type=submit]"]:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    el.click(timeout=8000)
                    print(f"clicked search via {sel!r}")
                    page.wait_for_timeout(6000)
                    break
            except Exception:  # noqa: BLE001
                continue

        award_caps = captures[award_start:]
        print(f"replies after filtering: {len(award_caps)}")

        shown = False
        for url, body in award_caps:
            if "Request Rejected" in body:
                print("   refused: " + url.split("?")[-1][:80])
                continue
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                continue
            print(f"   {url.split('?')[-1][:90]} -> {len(data.get('data') or [])} records, "
                  f"totalCount={data.get('totalCount')}")
            recs = data.get("data") or []
            if recs and not shown:
                shown = True
                print("\n--- ONE AWARD-STAGE RECORD ---")
                print(json.dumps(recs[0], ensure_ascii=False, indent=2)[:4000])
                print("\n--- FIELDS PRESENT ---")
                for k in sorted(recs[0].keys()):
                    print(f"  {k}")

        if not shown:
            print("\n(no award records read - filters may need a different route)")

        browser.close()

    print("\n" + "=" * 60)
    if len(page_ids) > 24:
        rounds = (total or 0) / max(len(page_ids), 1)
        print(f"PAGINATION WORKS. {len(page_ids)} tenders in {CLICKS} clicks.")
        print(f"A full sweep of {total} needs roughly {rounds:.0f} such rounds.")
    elif len(page_ids) > 6:
        print(f"Page size changed ({len(page_ids)} tenders) but paging is unproven.")
    else:
        print("Still stuck on the first batch.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
