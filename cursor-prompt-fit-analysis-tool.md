# Cursor prompt: In-app FIT file interval analysis tool

Paste everything below into Cursor.

---

Add a FIT-file interval analysis tool to this app. Motivation: a manual analysis of a 2×20 threshold session (FIT file) caught several things the app currently misses — a stale FTP (set 202 W, athlete demonstrated 214–216 W for 2×20 with strong finish), a stale LTHR on record (181 vs measured ~170–174 at threshold power), a stale device max HR (Garmin auto-detected 186 vs age-adjusted ~194–197 from a historical true max of 201), a pacing fault (interval 2 front-loaded at 227 W then fading to 207), and per-interval aerobic decoupling. Build this capability into the app so every ride gets it automatically.

## 1. FIT ingest module — `analysis/fit_ingest.py`

- Parse FIT files with `fitdecode` (add to deps). Sources: (a) new upload endpoint, (b) optionally fetch the FIT from Garmin for activities being analysed in `refresh_analyses()`.
- Extract: `record` stream (power, HR, cadence, temperature, timestamp), `lap` messages (incl. `wkt_step_index`), `workout_step` messages (target type, custom power/HR bounds, intensity), `session` summary, `zones_target` (device FTP, max HR, LTHR), `user_profile` (weight, resting HR).

## 2. Interval extraction + metrics

- Group laps by `wkt_step_index` to reconstruct each prescribed step's actual execution (structured workouts split steps into multiple laps — e.g. auto-lap at 5 km).
- Per work interval compute: duration, avg power, NP (30 s rolling 4th-power), VI, IF, %FTP, W/kg (from `user_profile.weight` or latest `body_metrics`), avg/max HR and %maxHR, avg cadence, 5-min splits (P/HR/cad), first-half vs second-half Pw:HR decoupling %, and time in / above / below the step's prescribed power band (from `workout_step` custom targets).
- Annotate with temperature range — decoupling >5% is expected at supra-threshold in heat; the interpretation note should reflect that.
- Persist per-interval rows in a new lazily-initialised table `interval_analyses` (activity_id, step_index, metrics JSON) following the existing `_ensure_*_schema()` pattern in `history/`.

## 3. Threshold-evidence engine (stale FTP detection)

- Rule: if a ride contains ≥1 sustained effort of ≥19 min at >103% of current `ftp_w` — or 2×20 at >103% where the second interval's avg power ≥ the first's (athlete not fading ⇒ genuinely below true threshold) — raise a "FTP likely stale" flag.
- Propose a new FTP: max(best-20-min × 0.95, 2×20 mean × 0.97), rounded. Surface as a dashboard prescription card (same pattern as the existing `ftp_retest` card) with two actions: "Accept estimate" (writes `ftp_tests` row with `ftp_w`, sets `workouts_stale_ftp` so the existing sync banner fires) or "Schedule retest" (existing flow).

## 4. HR calibration consistency checks

- Compare device `zones_target.max_heart_rate` against (a) highest HR observed in stored activities in the last 12 months and (b) an age-adjusted projection if a historical true max is stored (add optional `hr_max_reference` + date to config/coach memory; decline ≈0.5–0.7 bpm/yr).
- Compare stored `ftp_tests.ftp_hr` (LTHR) against measured avg HR during at-threshold-power intervals from §2. If LTHR on record exceeds measured threshold-effort HR by >5 bpm, flag it. Sanity bound: LTHR should be ~88–92% of true max.
- Surface discrepancies as a "HR calibration" card listing current vs evidence-based values for FTP, LTHR, max HR.

## 5. Pacing critique in AI analysis

- Extend `_build_analysis_prompt()` in `analysis/generate.py`: inject the per-interval 5-min splits, target-band compliance %, and decoupling numbers so the coach commentary can call out front-loading (e.g. first 5 min >8% above interval average), fades, and praise negative splits. Add an instruction that supra-threshold decoupling in >25 °C heat should not be flagged as an aerobic deficiency.
- Add the interval execution summary to `_build_coach_context()` in `server/coach.py` (recent N sessions) so coach chat can discuss execution quality, and cross-reference against `session_rpe` (objective vs subjective mismatch is itself a signal — e.g. supra-threshold power at RPE 3/5 ⇒ FTP stale).

## 6. UI

- Analysis tab: "Upload FIT" control → `POST /upload-fit` (multipart) → parse, match to existing activity by start time ± 2 min if present, render an interval table (the metrics in §2) plus any §3/§4 flags. For rides already ingested via Garmin, show the same table on the activity's analysis card.
- Keep templates package-data conventions (reinstall note in CLAUDE.md).

## 7. Tests

- Unit-test the NP/decoupling/band-compliance maths against a small synthetic record stream; test the stale-FTP rule boundaries (103%, second-interval-stronger condition); follow the conftest DB_PATH monkeypatch convention in `tests/conftest.py`.

Model usage per existing conventions: deterministic maths in Python, Sonnet only for the coaching narrative via the existing analysis pipeline. No new AI calls for the metrics themselves.
