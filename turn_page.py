"""Step 7: find any way to turn the page - six attempts in one run.

Step 6: Etimad refused nothing. The '»' button reports visible but a click
times out, meaning something covers it or we target a hidden copy.

Debugging a page I cannot see, one run at a time, is expensive. So this run
tries every reasonable route at once and reports which worked:

  0. diagnose - what element is actually at the button's position?
  1. click '»' with force (ignore the covering element)
  2. click the LAST matching '»' (there may be pagers top and bottom)
  3. click the page-number link '2' - an anchor, often easier
  4. click via the page's own scripting
  5. focus and press Enter
  6. dismiss any overlay, then click normally

Stores nothing. Looking only.
"""
from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

GATE_PAGE = "https://tenders.etimad.sa/Tender/AllTendersForVisitor"
TARGET = "AllSupplierTendersForVisitorAsync"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DIAGNOSE = """
() => {
  const out = [];
  document.querySelectorAll('button.page-link, a.page-link').forEach((el, i) => {
    const t = (el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const top = document.elementFromPoint(cx, cy);
    out.push({
      i, tag: el.tagName, text: t,
      disabled: el.disabled === true || el.classList.contains('disabled'),
      parentCls: (el.parentElement ? el.parentElement.className : '').slice(0, 40),
      box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
      elementOnTop: top ? (top.tagName + '.' + String(top.className).slice(0, 40)) : 'none',
      isSelf: top === el || (top && el.contains(top))
    });
  });
  return out;
}
"""


def count_new(captures, before):
    new = captures[before:]
    good = sum(1 for _u, b in new if "Request Rejected" not in b and b.strip().startswith("{"))
    bad = sum(1 for _u, b in new if "Request Rejected" in b)
    return len(new), good, bad


def main() -> int:
    captures: list[tuple[str, str]] = []
    winners: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="ar-SA", user_agent=USER_AGENT, viewport={"width": 1400, "height": 1600}
        )
        page = ctx.new_page()
        page.on("response", lambda r: captures.append((r.url, r.text()))
                if TARGET in r.url else None)

        page.goto(GATE_PAGE, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(15_000)
        print(f"gate page title: {page.title()!r}   first captures: {len(captures)}")

        # ---------- 0. diagnosis ----------
        print("\n=== WHAT IS ACTUALLY AT EACH PAGER BUTTON ===")
        try:
            for row in page.evaluate(DIAGNOSE):
                print(json.dumps(row, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            print(f"(diagnosis failed: {exc})")

        def attempt(label, fn):
            before = len(captures)
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                print(f"{label:<28} error: {type(exc).__name__}")
                return
            page.wait_for_timeout(4500)
            n, good, bad = count_new(captures, before)
            status = f"+{n} replies ({good} good, {bad} refused)"
            print(f"{label:<28} {status}")
            if good:
                winners.append(label)

        print("\n=== ATTEMPTS ===")

        attempt("1 force-click first »",
                lambda: page.locator("button.page-link", has_text="»").first
                .click(force=True, timeout=8000))

        attempt("2 force-click last »",
                lambda: page.locator("button.page-link", has_text="»").last
                .click(force=True, timeout=8000))

        attempt("3 click page number 2",
                lambda: page.locator("a.page-link", has_text="2").first
                .click(force=True, timeout=8000))

        attempt("4 click via page scripting", lambda: page.evaluate("""
            () => {
              const b = Array.from(document.querySelectorAll('button.page-link'))
                .find(x => (x.textContent || '').trim() === '»');
              if (!b) throw new Error('no next button');
              b.click();
            }
        """))

        attempt("5 focus and press Enter", lambda: (
            page.locator("button.page-link", has_text="»").first.focus(timeout=5000),
            page.keyboard.press("Enter"),
        ))

        def dismiss_then_click():
            for sel in ["button:has-text('موافق')", "button:has-text('إغلاق')",
                        ".modal.show .close", "#onetrust-accept-btn-handler",
                        ".muneer-widget button"]:
                try:
                    el = page.locator(sel).first
                    if el.count() and el.is_visible():
                        el.click(timeout=3000)
                        print(f"   (dismissed {sel})")
                except Exception:  # noqa: BLE001
                    pass
            page.locator("button.page-link", has_text="»").first.click(timeout=8000)

        attempt("6 dismiss overlay then click", dismiss_then_click)

        browser.close()

    # ---------- results ----------
    ids, total = set(), None
    for _u, body in captures:
        if "Request Rejected" in body:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        total = data.get("totalCount", total)
        for rec in data.get("data") or []:
            if isinstance(rec, dict) and rec.get("tenderId"):
                ids.add(rec["tenderId"])

    print("\n" + "=" * 60)
    print(f"unique tenders collected: {len(ids)} of {total}")
    if winners:
        print("WORKING ROUTES: " + "; ".join(winners))
        print("Exploring is done - the scraper can be built on the first of these.")
    else:
        print("No route turned the page.")
        print("Stop here and write the finding up before spending more.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
