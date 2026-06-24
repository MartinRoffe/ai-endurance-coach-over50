#!/usr/bin/env python3
"""Read-only snapshot of the data relevant to a safe target-weight assessment.

Pulls body composition, VO2max, resting HR, blood pressure and nutrition
intake from the local history.db. Does NOT modify anything. Just run:

    python3 pull_body_data.py

Then paste the printed summary back to the coach.
"""
import os, sqlite3, statistics
from datetime import date, timedelta

DB = os.path.expanduser("~/.ai_endurance_coach_over50/history.db")
if not os.path.exists(DB):
    raise SystemExit(f"DB not found at {DB} — adjust the path at top of this script.")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

def cols(table):
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}

def has(table):
    return bool(con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())

def rows(q, *a):
    try: return con.execute(q, a).fetchall()
    except sqlite3.Error: return []

def avg(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.mean(vals), 1) if vals else None

today = date.today()
d30 = (today - timedelta(days=30)).isoformat()
d90 = (today - timedelta(days=90)).isoformat()
d14 = (today - timedelta(days=14)).isoformat()

print("=" * 64)
print(f"BODY / TARGET-WEIGHT DATA SNAPSHOT   ({today.isoformat()})")
print("=" * 64)

# ── Body composition ─────────────────────────────────────────────
print("\n## BODY COMPOSITION (body_metrics)")
if has("body_metrics"):
    latest = rows("SELECT * FROM body_metrics WHERE weight_kg IS NOT NULL ORDER BY date DESC LIMIT 1")
    if latest:
        r = latest[0]
        print(f"  Latest reading ({r['date']}):")
        for k in ("weight_kg","fat_pct","muscle_mass_kg","bone_mass_kg",
                  "hydration_pct","visceral_fat","bmi","metabolic_age"):
            if k in r.keys() and r[k] is not None:
                print(f"    {k:16s}: {r[k]}")
        # derive lean / fat-free mass
        if r["weight_kg"] and r["fat_pct"]:
            lean = r["weight_kg"] * (1 - r["fat_pct"]/100)
            print(f"    {'lean_mass_kg':16s}: {lean:.1f}  (derived = weight x (1 - fat%/100))")
    win = rows("SELECT date, weight_kg, fat_pct FROM body_metrics WHERE date>=? AND weight_kg IS NOT NULL ORDER BY date", d90)
    if win:
        ws = [x["weight_kg"] for x in win]
        fs = [x["fat_pct"] for x in win if x["fat_pct"] is not None]
        print(f"  90-day weight: min {min(ws):.1f} / max {max(ws):.1f} / avg {avg(ws)} kg  ({len(win)} readings)")
        if fs: print(f"  90-day body-fat: min {min(fs):.1f} / max {max(fs):.1f} / avg {avg(fs)} %")
        first, last = win[0], win[-1]
        print(f"  trend: {first['date']} {first['weight_kg']}kg  ->  {last['date']} {last['weight_kg']}kg")
    else:
        print("  (no readings in last 90 days)")
else:
    print("  table missing — no body-composition data logged")

# ── VO2max + resting HR + nutrition from daily_metrics ───────────
print("\n## FITNESS & INTAKE (daily_metrics)")
if has("daily_metrics"):
    dm = cols("daily_metrics")
    def latest_nonnull(col):
        if col not in dm: return None
        r = rows(f"SELECT date,{col} FROM daily_metrics WHERE {col} IS NOT NULL ORDER BY date DESC LIMIT 1")
        return (r[0]["date"], r[0][col]) if r else None
    for col in ("vo2_max","resting_hr"):
        v = latest_nonnull(col)
        print(f"  {col:16s}: {v[1]}  (as of {v[0]})" if v else f"  {col:16s}: n/a")
    # nutrition averages (14-day)
    for col in ("calories_consumed","calorie_goal","calorie_goal_adjusted","carbs_consumed","protein_consumed"):
        if col in dm:
            vals = [x[col] for x in rows(f"SELECT {col} FROM daily_metrics WHERE date>=? AND {col} IS NOT NULL", d14)]
            print(f"  14d avg {col:22s}: {avg(vals)}  (n={len(vals)})" if vals else f"  14d avg {col:22s}: n/a")
else:
    print("  table missing")

# ── Blood pressure ──────────────────────────────────────────────
print("\n## BLOOD PRESSURE (blood_pressure)")
if has("blood_pressure"):
    bp = rows("SELECT * FROM blood_pressure WHERE date>=? ORDER BY date DESC", d90)
    if bp:
        sys_ = avg([x["systolic"] for x in bp]); dia = avg([x["diastolic"] for x in bp])
        last = bp[0]
        print(f"  latest ({last['date']}): {last['systolic']}/{last['diastolic']}  pulse {last['pulse']}")
        print(f"  90-day avg: {sys_}/{dia}  ({len(bp)} readings)")
    else:
        print("  (no readings in last 90 days)")
else:
    print("  table missing")

# ── Estimated W/kg if available ─────────────────────────────────
print("\n## ESTIMATED W/kg (VO2max proxy, no power meter)")
try:
    latest = rows("SELECT date, weight_kg FROM body_metrics WHERE weight_kg IS NOT NULL ORDER BY date DESC LIMIT 1")
    vo2 = rows("SELECT vo2_max FROM daily_metrics WHERE vo2_max IS NOT NULL ORDER BY date DESC LIMIT 1")
    if latest and vo2:
        kg = latest[0]["weight_kg"]; v = vo2[0]["vo2_max"]
        est = 0.80 * (v - 7) * kg / 10.8
        print(f"  est FTP ~{est:.0f} W  ->  ~{est/kg:.2f} W/kg   (VO2max {v}, weight {kg}kg)")
    else:
        print("  insufficient data")
except Exception as e:
    print(f"  n/a ({e})")

print("\n" + "=" * 64)
print("WHAT THIS SCRIPT CANNOT SEE (you'll need to supply):")
print("  - height, age, sex (not stored)")
print("  - bloodwork: ferritin, testosterone, thyroid, vit D, FBC, lipids")
print("  - bone density (DEXA)")
print("=" * 64)
con.close()
