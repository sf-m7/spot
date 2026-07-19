# Spot — Stage 0

Saudi tender verdict engine. Free-first strategy; Stage 0 is internal only, no users.
Governing docs: Possibility Map > Decision Log > Assessment Report > Concept > Blueprints.
**Khabar priority overrides all of it.**

## Infrastructure (live)

| Thing | Value |
|---|---|
| Supabase project | `spot` — ref `wlnjdhgighoudrzoddyq`, eu-central-1, free tier, **separate from Khabar** |
| R2 bucket | `spot-archive` — **separate from `khabar-archive`** |
| Compute | GitHub Actions, public repo |

Schema applied: migrations `001_core_entities`, `002_verdict_and_calibration`, `003_ops_immutability_rls`.

## Invariants enforced in the database, not just in prose

- `verdict` rejects UPDATE and DELETE. A track record you can quietly edit is not a track record.
- `verdict` has a trigger that refuses any row whose `knowledge_cutoff` is later than the
  tender's `submission_deadline`. This is the anti-lookahead guard; without it a "backtest"
  is just hindsight and the Door-A pitch is fraudulent.
- `verdict.mode` is `live` or `backtest`, unique per ruleset. They must never be pooled
  into one calibration number.
- `cost_series.stream` accepts only `materials | fuel | wages | financing`. Transport and
  equipment are structurally impossible to insert — declared unknown, never estimated.
- `ruleset` is append-only and carries a mandatory `change_reason`. Threshold changes are
  logged by construction.
- `archive_manifest.verified_at` is null until an R2 copy is checked. Nothing gets purged
  from Postgres before it is set.
- `scrape_run.status` has an explicit `empty`. A zero-row run is a failure, not a success.

## Gate zero (do this first)

```
pip install -r requirements.txt
export SPOT_SUPABASE_SERVICE_KEY=...
python -m spot.probe_etimad
```

Then push and run the same thing on a GitHub Actions runner. The two answers may differ,
and the difference is the whole question: **can free datacentre compute reach Etimad, or
does Spot need paid residential proxies like Khabar does?**

## Build order after gate zero

1. Parser for whichever surface the probe reports reachable → `tender`, `agency`, `award`.
2. Award backfill, one sector.
3. Ruleset v1 + verdict issuer (backtest mode).
4. Self-grading harness → `verdict_grade`.
5. Calibration report → `calibration_run`. Stage 0 gate: ≥200 graded closed tenders in one
   sector, beating the naive baseline.
