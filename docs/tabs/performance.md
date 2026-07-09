# Performance & Analysis

**Nav:** the **Performance ▾** group → **Performance** and **Analysis**.

These two tabs are about the longer view: how your fitness and fatigue are
trending, and what each individual workout tells you.

For power meter setup and the dual-channel model, see **[Power Training](../power-training.md)**.

---

## Performance tab

**Route:** `/performance`

### What it's for

The big-picture training-load and trend view — are you getting fitter, are you
overcooked, and will you arrive at your event both fit and fresh?

> 📸 *Screenshot: the Performance tab showing the CTL/ATL/TSB chart with the projection overlay.*

### What you'll see

**Garmin PMC (always)**

- **The PMC chart (CTL / ATL / TSB).** Your fitness, fatigue, and form over time.
  See [the concept](../concepts.md#training-load-ctl-atl-and-tsb-the-pmc). A
  **projection** continues the lines to your event date using your planned
  sessions, drawn as a dashed amber overlay with a vertical line marking the
  event.
- **Taper scenarios table.** Three pre-computed "what-ifs" over the final two
  weeks — *as planned*, *drop one quality session*, and *halve final-week volume*
  — so you can see how each choice changes the form (TSB) you'll bring to the
  start line. The third scenario is also overlaid on the chart as a blue dashed
  line.
- **Zone 2 cardiac-drift trend.** A scatter of your easy rides only, with a
  best-fit line showing whether your heart rate is drifting up or settling over
  time at the same easy effort.
- **Training polarisation charts (HR).** A stacked bar of time in each HR zone
  (Z1–Z5) per week, plus a donut of the totals for the block.
- **HR durability drift chart.** For long rides, how much your heart rate drifts in
  the final third versus the first third.
- **Foster monotony / strain chart.** Weekly training monotony and strain, which
  feed the high-monotony fatigue alert.
- **Heat / altitude acclimation tile.** Your current acclimation percentages,
  when Garmin reports them.

**Power surfaces (when power meter active)**

See [Performance tab power surfaces](../power-training.md#performance-tab-power-surfaces):

- **Activate power** CTA and activation checklist (before or during onboarding).
- **Weekly TSS bars** and **Coggan CTL/ATL/TSB** (independent of Garmin PMC).
- **FTP trend** — LTHR and measured FTP watts on dual axes.
- **Measured W/kg** chart (VO₂max estimate as secondary overlay).
- **W/kg goal projection** — optional target form on Performance.
- **Power zone polarisation** — parallel to the HR polarisation charts.
- **Pw:HR decoupling** — aerobic decoupling on rides ≥90 min with power.
- **Dual-channel caveat card** — which decisions use HR vs watts.
- **Power profile** — Coggan 7-zone table from latest measured FTP.
- **Stale workouts banner** — prompts `/sync-workouts` after FTP changes.
- **Last quality session snapshot** — NP vs %FTP in the trends block.

### Good to know

- **Read Garmin PMC and power PMC as separate channels.** See
  [Two load channels](../concepts.md#two-load-channels).
- **Activate power** via `endurance-coach --activate-power 30` or the link on
  this tab if you have a meter but power charts are empty.

---

## Analysis tab

**Route:** `/analysis`

### What it's for

A per-workout review: for each recent activity, an AI coach reads your
heart-rate zone breakdown (and power zones when available) and writes a short,
discipline-aware assessment.

> 📸 *Screenshot: an Analysis card showing HR zones and the AI commentary, with the RPE emoji row.*

### What you'll see

- **One card per activity**, each with the heart-rate zone distribution and a
  Claude-written commentary tailored to the type of session (a long ride reads
  differently from intervals).
- **Power zones and watts** on cycling cards when your meter was active — including
  per-rep average power on interval sessions.
- **Avg / normalised power** on activity headers when power data exists.
- **Compound sessions** (e.g. a kettlebell + stair-climber day) are collapsed
  into a single card showing both halves side by side.

### How to use it

- **Log your RPE.** Each card has a row of effort emoji — 😴 😊 😤 🔥 💀 — to record
  how hard the session *felt* (rate of perceived exertion). This is saved and fed
  to the AI coach so its advice accounts for how you actually experienced the
  work, not just the numbers.
- **Log your fuelling.** For endurance rides you can record how your in-ride
  fuelling went (planned vs actual carbs per hour, whether fluids were on track,
  and a note). Plans may include estimated ride kJ when FTP is known.
- **Regenerate an analysis.** Use the **Refresh** action to pull and analyse any
  activities that haven't been processed yet.

### Good to know

- **Analysis needs the activity to have synced** to Garmin first, and needs your
  Anthropic API key set. Without the key, this tab stays empty.
- FTP test sessions **auto-populate your fitness-test history** (HR and watts when
  available), which feeds the Readiness FTP cards and the Performance FTP trend.
