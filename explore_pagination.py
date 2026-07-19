"""Step 4: can we collect in bulk by driving the page like a person?

Established so far:
  - A real browser passes Etimad's challenge on free GitHub machines.
  - The page's own data call returns clean JSON, 42 fields per tender, 7788 live.
  - ANY request we construct ourselves is refused, even an exact replay.

So collection must come from genuine page activity. This step finds the page's
own controls and tests them:
  1. Is there a page-size selector? (6 per page means ~1300 clicks per sweep;
     50 per page means ~156.)
  2. Does clicking next actually yield a fresh batch we can read?
  3. How fast, and does it keep working or get cut off?

Stores nothing. Looking only.
"""
from __future__ import annotations

import json
import sys
import time

from playwright.sync_api import sync_playwright

GATE_PAGE = "https://tenders.etimad.sa/Tender/AllTendersForVisitor"
TARGET = "AllSupplierTendersForVisitorAsync"
CLICKS_TO_TRY = 5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def main() -> int:
    captures: list[tuple[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="ar-SA", user_agent=USER_AGENT, viewport={"width": 1366, "height": 1200}
        )
        page = ctx.new_page()

        def on_response(resp):
            if TARGET in resp.url:
                try:
                    captures.append((resp.url, resp.text()))
                except Exception:  # noqa: BLE001
                    pass

        page.on("response", on_response)
        page.goto(GATE_PAGE, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(15_000)
        print(f"gate page title: {page.title()!r}")
        print(f"initial captures: {len(captures)}")

        # ---------- 1. what dropdowns does the page offer? ----------
        print("\n=== DROPDOWNS ON THE PAGE ===")
        try:
            selects = page.evaluate("""
              () => Array.from(document.querySelectorAll('select')).map(s => ({
                id: s.id, name: s.name,
                cls: (s.className || '').slice(0, 60),
                options: Array.from(s.options).slice(0, 12)
                          .map(o => o.value + '|' + o.text.trim().slice(0, 25))
              }))
            """)
            for s in selects:
                print(json.dumps(s, ensure_ascii=False))
            if not selects:
                print("(none found)")
        except Exception as exc:  # noqa: BLE001
            print(f"(could not read dropdowns: {exc})")

        # ---------- 2. what do the pagination controls look like? ----------
        print("\n=== PAGINATION CONTROLS ===")
        try:
            pager = page.evaluate("""
              () => {
                const hits = [];
                const sel = 'a,button,li';
                document.querySelectorAll(sel).forEach(el => {
                  const t = (el.textContent || '').trim();
                  const cls = el.className || '';
                  const looksPager =
                    /^\\d{1,3}$/.test(t) ||
                    /التالي|السابق|next|prev/i.test(t) ||
                    /pag(e|inat)/i.test(String(cls)) ||
                    /pag(e|inat)/i.test(el.id || '');
                  if (looksPager && hits.length < 25) {
                    hits.push({ tag: el.tagName, text: t.slice(0, 20),
                                id: el.id, cls: String(cls).slice(0, 60),
                                onclick: (el.getAttribute('onclick')||'').slice(0,80) });
                  }
                });
                return hits;
              }
            """)
            for h in pager:
                print(json.dumps(h, ensure_ascii=False))
            if not pager:
                print("(none found - the list may load by scrolling)")
        except Exception as exc:  # noqa: BLE001
            print(f"(could not read pagination: {exc})")

        # ---------- 3. try clicking through pages ----------
        print(f"\n=== CLICKING NEXT, {CLICKS_TO_TRY} TIMES ===")
        candidates = [
            "a[aria-label='Next']",
            "a.page-link[rel='next']",
            "li.next a",
            "a:has-text('التالي')",
            "button:has-text('التالي')",
            ".pagination li:last-child a",
        ]
        for i in range(CLICKS_TO_TRY):
            before = len(captures)
            clicked = None
            for sel in candidates:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        started = time.time()
                        el.click(timeout=8000)
                        clicked = sel
                        break
                except Exception:  # noqa: BLE001
                    continue
            if not clicked:
                print(f"click {i + 1}: no next control found - stopping")
                break
            page.wait_for_timeout(4000)
            gained = len(captures) - before
            print(f"click {i + 1}: via {clicked!r} -> {gained} new reply "
                  f"({time.time() - started:.1f}s)")
            if gained == 0:
                print("  (clicked but nothing new arrived)")

        browser.close()

    # ---------- results ----------
    print(f"\n=== WHAT WE COLLECTED ===\ntotal replies read: {len(captures)}")
    ids: set[int] = set()
    total_count = None
    rejected = 0
    for url, body in captures:
        if "Request Rejected" in body:
            rejected += 1
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        total_count = data.get("totalCount", total_count)
        for rec in data.get("data") or []:
            if isinstance(rec, dict) and rec.get("tenderId"):
                ids.add(rec["tenderId"])
        print(f"  {url.split('?')[-1][:80]} -> {len(data.get('data') or [])} tenders")

    print(f"\nunique tenders collected: {len(ids)}")
    print(f"tenders available in total: {total_count}")
    print(f"replies that were refused: {rejected}")

    print("\n" + "=" * 60)
    if len(ids) > 6:
        per_sweep = (total_count or 0) / max(len(ids), 1)
        print("BULK COLLECTION WORKS by driving the page.")
        print(f"At this rate a full sweep needs roughly {per_sweep:.0f} more rounds.")
    elif len(ids) == 6:
        print("Only the first batch was readable - clicking did not yield more.")
        print("Need a different way to turn the page.")
    else:
        print("Nothing collected. Something changed since the last run.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
