"""GATE ZERO: can we reach Etimad at all, from the machine that will do the scraping?

Every downstream assumption in the concept documents rests on Etimad being
"openly accessible, no auth, no rate limiting". As of 2026-07-19 a request from
a datacentre IP is answered by an F5 bot-defence challenge page instead of data.
That may or may not apply to GitHub Actions runners - this probe measures it
rather than assuming either way.

Run it, read the table it prints, and only then decide whether the scraper is a
weekend of parsing or a proxy-budget problem.
"""
from __future__ import annotations

import sys
import time

import httpx

from . import config, db

# Candidate surfaces, cheapest/most valuable first. If a path 404s that is
# itself a finding (Etimad moved), and distinct from being blocked.
CANDIDATES: list[tuple[str, str]] = [
    ("root", "https://tenders.etimad.sa/"),
    ("list_html", "https://tenders.etimad.sa/Tender/AllTendersForVisitor"),
    ("list_json", "https://tenders.etimad.sa/Tender/AllTendersForVisitorAsync?PageSize=6&PageNumber=1"),
    ("supplier_json", "https://tenders.etimad.sa/Tender/AllSupplierTendersForVisitorAsync?PageSize=6&PageNumber=1"),
    ("awards_html", "https://tenders.etimad.sa/Tender/AllAwardedTendersForVisitor"),
]

# Fingerprints of the F5 / BIG-IP ASM interstitial rather than real content.
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
        return "BLOCKED_BOT_DEFENCE"
    if resp.status_code == 404:
        return "NOT_FOUND"
    if resp.status_code >= 500:
        return "SERVER_ERROR"
    if resp.status_code != 200:
        return f"HTTP_{resp.status_code}"
    ctype = resp.headers.get("content-type", "")
    if "json" in ctype:
        return "OK_JSON"
    if len(resp.text) < 2000:
        return "OK_BUT_TINY"
    return "OK_HTML"


def main() -> int:
    headers = {
        "User-Agent": config.USER_AGENT,
        "Accept-Language": "ar,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }
    results = []
    with db.run("probe_etimad") as r:
        with httpx.Client(
            headers=headers,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as http:
            for name, url in CANDIDATES:
                try:
                    resp = http.get(url)
                    verdict = classify(resp)
                    detail = (
                        f"{resp.status_code} "
                        f"{resp.headers.get('content-type', '?').split(';')[0]} "
                        f"{len(resp.content)}B"
                    )
                except Exception as exc:  # noqa: BLE001
                    verdict, detail = "TRANSPORT_ERROR", f"{type(exc).__name__}: {exc}"

                results.append((name, verdict, detail))
                r.rows_seen += 1
                r.note(f"{name:<15} {verdict:<20} {detail}")
                time.sleep(config.REQUEST_DELAY_SECONDS)

        reachable = [n for n, v, _ in results if v.startswith("OK")]
        if reachable:
            r.note(f"REACHABLE: {', '.join(reachable)} -> build the parser next.")
        else:
            r.note("NO SURFACE REACHABLE -> the 'no proxy costs' assumption is dead. "
                   "Decide: residential proxies (a real monthly cost) or stop.")

    print("\n=== Etimad access probe ===")
    for name, verdict, detail in results:
        print(f"{name:<15} {verdict:<20} {detail}")
    return 0 if any(v.startswith("OK") for _, v, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
