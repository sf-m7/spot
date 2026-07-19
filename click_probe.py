"""Step 6: real interactions only, one change at a time.

Step 5 failed because I set the dropdowns by script and fired the change event
twice. Etimad refused the resulting request and the list broke.

This time: no scripted value-setting. Playwright operates the controls the way
a person does. And the two changes are tested separately so a failure points at
one cause:

  TEST 1 - just click next, four times, nothing else touched.
  TEST 2 - only if test 1 works: raise page size to 24 properly, click again.

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
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def read(captures, start=0):
    """Return (unique ids, totalCount, refused count) for captures[start:]."""
    ids, total, refused = set(), None, 0
    for _u, body in captures[start:]:
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
    return ids, total, refused


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

        # what state are the controls in?
        try:
            info = page.evaluate("""
              () => {
                const s = document.getElementById('itemsPerPage');
                const btns = Array.from(document.querySelectorAll('button.page-link'))
                  .map(b => (b.textContent || '').trim());
                return { pageSizeVisible: !!(s && s.offsetParent !== null),
                         pageSizeValue: s ? s.value : null,
                         pagerButtons: btns };
              }
            """)
            print(f"controls: {json.dumps(info, ensure_ascii=False)}")
        except Exception as exc:  # noqa: BLE001
            print(f"(control check failed: {exc})")

        # ---------------- TEST 1: pagination alone ----------------
        print("\n" + "=" * 60 + "\nTEST 1 - CLICK NEXT ONLY\n" + "=" * 60)
        t1_start = len(captures)
        next_btn = page.locator("button.page-link").filter(has_text=re.compile(r"^\s*»\s*$"))

        for i in range(4):
            before = len(captures)
            try:
                n = next_btn.count()
                if n == 0:
                    print(f"click {i + 1}: no next button present - stopping")
                    break
                t0 = time.time()
                next_btn.first.scroll_into_view_if_needed(timeout=5000)
                next_btn.first.click(timeout=10_000)
            except Exception as exc:  # noqa: BLE001
                print(f"click {i + 1}: failed - {type(exc).__name__}")
                break
            page.wait_for_timeout(4000)
            new = captures[before:]
            bad = sum(1 for _u, b in new if "Request Rejected" in b)
            print(f"click {i + 1}: +{len(new)} replies, {bad} refused "
                  f"({time.time() - t0:.1f}s)")
            for u, _b in new:
                print("      " + u.split("?")[-1][:85])

        ids1, total1, refused1 = read(captures, t1_start)
        print(f"\nTEST 1 RESULT: {len(ids1)} tenders gathered, {refused1} refusals, "
              f"totalCount={total1}")
        test1_ok = len(ids1) > 6

        # ---------------- TEST 2: page size, done properly ----------------
        print("\n" + "=" * 60 + "\nTEST 2 - RAISE PAGE SIZE TO 24\n" + "=" * 60)
        if not test1_ok:
            print("skipped - pagination itself is not working yet")
        else:
            t2_start = len(captures)
            try:
                # select_option performs a genuine selection and fires the page's
                # own handlers once, correctly.
                page.select_option("#itemsPerPage", "24", timeout=10_000)
                print("page size set to 24 by real selection")
            except Exception as exc:  # noqa: BLE001
                print(f"could not set page size: {type(exc).__name__}: {exc}")
            page.wait_for_timeout(5000)

            new = captures[t2_start:]
            bad = sum(1 for _u, b in new if "Request Rejected" in b)
            print(f"+{len(new)} replies, {bad} refused")
            for u, _b in new:
                print("      " + u.split("?")[-1][:85])

            ids2, total2, _r = read(captures, t2_start)
            print(f"TEST 2 RESULT: {len(ids2)} tenders in one reply")

        browser.close()

    all_ids, total, _r = read(captures)
    print("\n" + "=" * 60)
    print(f"unique tenders collected this run: {len(all_ids)} of {total}")
    if len(all_ids) > 6:
        print("COLLECTION WORKS by clicking. Sweep speed is now measurable.")
    else:
        print("Still only the batch the page loads by itself.")
        print("Next resort: open each tender's own page directly by its id.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
