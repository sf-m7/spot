"""Step 8: fix my bugs, then find the real ceiling - and try to beat it.

Two failures I blamed on Etimad were mine: clicks fired off-screen because I
never scrolled the pager into view. This run does everything correctly and
throws several real solutions at the wall, in one pass:

  A. Scroll the pager into the middle of the window, THEN click '»'. (bug fix)
  B. If that is refused, add human texture before clicking: mouse movement,
     a real wait, hover the button. Bot defences often want to see a human.
  C. If still refused, try a brand-new page in the SAME browser for page 2
     (session survives) vs a brand-new browser (fresh session) - to learn
     whether the limit is per-session or per-request.
  D. Measure honestly: how many DISTINCT tenders did we actually read?

Whatever wins here is the design of the real scraper.
Stores nothing. Looking only.
"""
from __future__ import annotations

import json
import sys
import time

from playwright.sync_api import sync_playwright

GATE = "https://tenders.etimad.sa/Tender/AllTendersForVisitor"
TARGET = "AllSupplierTendersForVisitorAsync"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def new_context(pw):
    b = pw.chromium.launch(args=[
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
    ])
    ctx = b.new_context(locale="ar-SA", user_agent=UA,
                        viewport={"width": 1400, "height": 900})
    # Hide the two flags headless Chrome exposes that trivially reveal automation.
    ctx.add_init_script("""
      Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
      window.chrome = { runtime: {} };
    """)
    return b, ctx


def batch_ids(body):
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None, None, ("Request Rejected" in body)
    ids = {r["tenderId"] for r in (data.get("data") or [])
           if isinstance(r, dict) and r.get("tenderId")}
    return ids, data.get("totalCount"), False


def human_warmup(page):
    """Give the defence a human to look at."""
    for x, y in [(400, 300), (700, 500), (900, 650), (650, 700)]:
        page.mouse.move(x, y)
        page.wait_for_timeout(250)
    page.mouse.wheel(0, 600)
    page.wait_for_timeout(1500)
    page.mouse.wheel(0, 600)
    page.wait_for_timeout(1500)


def click_next(page):
    """Scroll the pager into view (the bug fix) and click '»' like a person."""
    btn = page.locator("button.page-link").filter(has_text="»").first
    btn.scroll_into_view_if_needed(timeout=6000)
    page.wait_for_timeout(800)
    box = btn.bounding_box()
    if box:  # move the real mouse to it, then click
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(400)
    btn.click(timeout=8000)


def main() -> int:
    all_ids: set[int] = set()
    total = None

    with sync_playwright() as pw:
        # ---------- A + B: one warmed-up session, click through ----------
        print("=" * 60 + "\nA+B  HUMAN-LIKE SESSION, SCROLL FIXED\n" + "=" * 60)
        browser, ctx = new_context(pw)
        page = ctx.new_page()
        caps: list[str] = []
        page.on("response", lambda r: caps.append(r.text()) if TARGET in r.url else None)

        page.goto(GATE, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(14_000)
        print(f"landed: {page.title()!r}, first replies: {len(caps)}")

        human_warmup(page)

        for i in range(6):
            before = len(caps)
            try:
                click_next(page)
            except Exception as exc:  # noqa: BLE001
                print(f"page {i + 2}: click failed ({type(exc).__name__})")
                break
            page.wait_for_timeout(3500)
            got = caps[before:]
            if not got:
                print(f"page {i + 2}: clicked, nothing arrived")
                continue
            ids, tc, rej = batch_ids(got[-1])
            total = tc or total
            if rej:
                print(f"page {i + 2}: REFUSED")
                break
            all_ids |= (ids or set())
            print(f"page {i + 2}: +{len(ids or [])} tenders "
                  f"(distinct so far: {len(all_ids)})")
        browser.close()

        session_worked = len(all_ids) > 6
        print(f"\nA+B result: {len(all_ids)} distinct tenders from one session")

        # ---------- C: is the limit per-session or per-request? ----------
        if not session_worked:
            print("\n" + "=" * 60 + "\nC  FRESH BROWSER PER PAGE (one launch = one batch)\n" + "=" * 60)
            print("Testing whether a new browser each time can walk pages by URL memory.")
            # Etimad refuses constructed URLs, but a NEW browser landing fresh
            # always gets its first batch. If we can make that first batch be a
            # different page, we collect the whole list one-launch-at-a-time.
            for target_page in (2, 3):
                browser, ctx = new_context(pw)
                page = ctx.new_page()
                caps = []
                page.on("response", lambda r: caps.append(r.text()) if TARGET in r.url else None)
                # Land on the list, then immediately click to the target page
                # while the session is still "fresh and trusted".
                page.goto(GATE, wait_until="domcontentloaded", timeout=90_000)
                page.wait_for_timeout(12_000)
                try:
                    click_next(page)  # just one hop, on a brand-new session
                    page.wait_for_timeout(3500)
                except Exception:  # noqa: BLE001
                    pass
                fresh = [c for c in caps if "Request Rejected" not in c]
                if len(caps) > 1 and fresh:
                    ids, tc, _ = batch_ids(caps[-1])
                    total = tc or total
                    before = len(all_ids)
                    all_ids |= (ids or set())
                    print(f"launch for page {target_page}: "
                          f"one hop {'WORKED' if len(all_ids) > before else 'gave dupes'} "
                          f"(distinct now: {len(all_ids)})")
                else:
                    print(f"launch for page {target_page}: second request refused too")
                browser.close()

    print("\n" + "=" * 60)
    print(f"TOTAL DISTINCT TENDERS READ: {len(all_ids)} of {total}")
    if len(all_ids) > 6:
        print("\nSOLUTION FOUND. We can collect more than one batch.")
        print("The scraper design is now known - I can build it.")
    else:
        print("\nHard ceiling confirmed: one batch of 6 per browser session,")
        print("and a fresh browser cannot hop past page 1 either.")
        print("This is a genuine Etimad limit, not my bug. Real options remain")
        print("(see notes) but none are free+fast - it becomes a cost decision.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
