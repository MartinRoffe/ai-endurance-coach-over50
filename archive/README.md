# Garmin history archive (2009–2016)

Two-stage pipeline: extract activity metadata from Garmin Connect, then analyse
layoff rebuild rates and training consistency. Findings feed the dashboard
`/archive` page and coach chat context.

## Setup

```bash
pip install -r archive/requirements.txt
# Package auth (GARMIN_EMAIL / GARMIN_PASSWORD / ANTHROPIC_API_KEY) via .env
pip install .   # so ai_endurance_coach_over50.client is importable
```

## Stage 1 — Fetch

```bash
# Smoke test one month
python archive/garmin_fetch.py --start 2015-06-01 --end 2015-06-30

# Full range (default 2009-01-01 … 2016-12-31); resumable
python archive/garmin_fetch.py
```

Raw monthly JSON lands in `archive/raw/`. Re-runs skip cached months unless `--force`.

## Stage 2 — Analyse

```bash
python archive/garmin_analysis.py
# Regenerate Claude Opus narrative:
python archive/garmin_analysis.py --force-ai
```

Writes `findings.json`, `analysis_report.md`, `shortlist.csv`, and `charts/*.png`.
Also copies `findings.json` to `~/.ai_endurance_coach_over50/archive/` so the
launchd dashboard can find it regardless of working directory.

## Stage 3 — FIT / true MMP

```bash
# Smoke: 1–2 shortlist FITs
python archive/garmin_fit_fetch.py --limit 2

# Full shortlist (~35), then mean-maximal power + FIT-grounded rebuild
python archive/garmin_fit_fetch.py
python archive/garmin_mmp.py --force-ai
```

FITs land in `archive/fits/`. MMP merges into `findings.json` (`mmp`, `rebuild_fit`).

## Dashboard & coach

After analysis (and `pip install --force-reinstall .` if templates changed), open
**Train → History** (`/archive`). Coach chat picks up the rebuild-rate section
automatically from `findings.json` (prefers FIT-grounded when present).
