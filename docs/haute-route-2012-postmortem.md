# Haute Route 2012 — Failure Post-Mortem & Lessons for 2027

*Analysis of the 5 TCX files from the inaugural Haute Route Alps (Geneva→Nice, Aug 2012). Read as a coach: what the heart-rate and ride data actually say, and what to carry into the 2027 build.*

> **Data-quality note.** The "power" in these files came from an HR-strap-based estimator, not a strain-gauge meter — treat it as *virtual power*. So the absolute watts and kJ figures below are indicative only (probably loosely calibrated off speed/gradient/HR). The **heart-rate data is the trustworthy axis**, and the conclusions here rest on it. Where I lean on power it's only for *shape and direction* (e.g. power holding while HR can't respond), not precise numbers.

## What the data shows (the files don't lie)

| Day | Date | Time | Dist | Climb | Work | Avg HR | % time >80% HRmax | % time >90% HRmax | HR↔Power decoupling |
|-----|------|------|------|-------|------|--------|-------------------|-------------------|---------------------|
| 1 | Aug 19 | 6.4h | 126 km | 2,787 m | 5,347 kJ | 158 | **63%** | **28%** | +7% |
| 2 | Aug 20 | 5.6h | 107 km | 2,508 m | 4,427 kJ | 150 | 55% | 2% | +9% |
| 3 | Aug 21 | 2.4h | 40 km | 919 m | 1,567 kJ | 129 | 16% | 1% | **+43%** ← collapse |
| — | Aug 22 | — | rest (Alpe d'Huez TT skipped) | | | | | | |
| 4 | Aug 23 | 6.9h | 138 km | 3,425 m | 5,572 kJ | 154 | 62% | 12% | +3% |
| 5 | Aug 24 | 6.4h | 109 km | 2,960 m | 4,745 kJ | 143 | 38% | 0% | −12% |

(HRmax taken as 193, your observed peak on Day 1. The two HR-zone columns are pure heart-rate data — fully reliable. The Work and Decoupling columns use the strap-estimated virtual power, so read them for *pattern*, not precision.)

## The story these numbers tell

**Day 1 was the mistake that cost you the week.** On the opening stage of a seven-day race you spent **63% of 6+ hours above 80% of max HR, and 28% above 90%.** That is a one-day-hard-ride pacing strategy executed on day one of seven. You essentially time-trialled the first stage. There is no version of multi-day stage racing where that is survivable — you wrote a cheque on Monday that the rest of the week had to cash.

**Day 2 — the ceiling was already dropping.** Same effort (55% above 80% HRmax) but time above 90% collapsed from 28% to 2%. Your body wouldn't *let* you reach the top end anymore. That's the first warning shot: the engine was being rationed. You probably felt "a bit flat" but pushed on.

**Day 3 was a textbook depletion blow-up — and you can see it in HR alone, no power needed.** On a *climbing* stage your average HR was just **129 bpm** and your max never got above **178** (it had been 193 and 185 on Days 1–2). On the steepest part of the day your engine simply would not rev. That is the unmistakable signature of a depleted, parasympathetically-suppressed system — empty glycogen, "nothing in me," exactly as you remember it. The virtual-power trace agrees with the *direction* even if not the exact watts: it shows effort going in on the first climb while HR stayed stubbornly low, then output bleeding away until the broom wagon caught you at 40 km. You didn't lose fitness overnight; you ran the tank dry over three days and Day 3 was when the needle hit E.

**The rest day (Aug 22) proves the diagnosis.** After 24h off, Day 4 came back at 62% above 80% HRmax, 12% above 90%, decoupling of just +3% over **3,425 m of climbing** — your single biggest climbing day. The engine was never the problem. A day of rest and (presumably) eating restored it almost completely. That tells you the failure was **management, not capacity.**

**Day 5 is what good pacing looks like — and you finally did it.** Negative decoupling (−12%): heart rate *drifted down* while power went *up* across the ride. That's a rider working inside himself, fuelled and controlled. The contrast with Day 1 is the whole lesson in one row.

## Root causes, ranked

1. **Pacing — by a mile the biggest factor.** You raced Day 1 like a sportive PB attempt. In a stage race, Day 1 should feel almost embarrassingly easy. The rule: *the first day you should finish feeling you could have gone harder.* You inverted it.

2. **Fuelling — the accelerant.** Forget the exact kJ (virtual power, unreliable) — the duration alone makes the point: 6+ hours of hard mountain riding needs roughly **80–90 g of carbohydrate per hour, i.e. ~500 g across a day like Day 1.** By your own account you "had no idea about fuelling" in 2012, so you were almost certainly taking a fraction of that. Combine a too-hard pace (which burns a higher *fraction* of carbohydrate) with under-fuelling and you build a glycogen debt that compounds every day until Day 3 forecloses on it. The HR collapse on Day 3 is what that debt looks like when it comes due.

3. **Cadence / grinding.** You averaged 59–65 rpm on Days 1–3, and notably **73 rpm on Day 4 when you were fresh and rode well.** Grinding big gears at low cadence on long climbs recruits more fast-twitch fibre and chews through glycogen faster — a particularly costly habit for a masters rider, where neuromuscular fatigue lingers longer.

4. **No fatigue monitoring.** The Day 2 signal (top-end HR vanishing) was a clear, readable "back off now" flag. With nothing watching for it, you rode straight past the warning into the wall.

## What this means for 2027 (you're over 50 now — the margins are different)

The good news: your 2012 problem was almost entirely *executional*, not physiological. Those are the fixable kind. Carry these forward into the Haute Route Alpes 2027 build:

- **Pace off a hard HR/power ceiling, not off feel.** Day 1 of the 2027 event you should cap yourself well below threshold — think Z2 with only the steepest pitches nudging Z3. The fitness to climb fast is worthless if you can't repeat it for seven days. Your app already models CTL/TSB and durability drift — use the decoupling chart as your discipline check: if drift creeps past ~5% on long rides in training, you went too hard or under-fuelled.

- **Train the gut and rehearse fuelling at 80–90 g/h.** Carbohydrate tolerance is trainable and it is non-negotiable for a stage race. Your plan already has per-stage AI fuelling plans and in-ride compliance logging — treat those as the primary deliverable, not an afterthought. In 2012 fuelling was the gap; in 2027 it should be your edge. The target of ~500–550 g carbs on the big days is real, not optional.

- **Lift your climbing cadence.** Deliberately practise sustained climbing at 75–85 rpm. Spinning protects your legs and your glycogen — both of which recover more slowly at 50+ than they did at 36.

- **Respect cumulative load and over-50 recovery.** The data shows your body *can* absorb a 3,400 m climbing day — *if* it's not already in debt. Back-to-back fatigue tracking and the HRV traffic light in your app exist precisely to catch the Day-2 warning you missed in 2012. Heed amber.

- **The masters-athlete reframe:** at 50+ you have *less* margin for a pacing error and *slower* repayment of a glycogen/recovery debt, but your aerobic durability and pacing judgement can be *better* than they were at 36 — if you let the data govern the ego. The 2012 files are the perfect cautionary baseline: same rider, and the difference between Day 1 (blew up) and Day 5 (rode it right) was entirely how he chose to ride.

**Bottom line:** 2012 didn't fail because you weren't strong enough. It failed because you spent your whole week's matches in the first six hours and never put fuel back in the tank. Fix pacing and fuelling — the two things your 2027 plan is explicitly built around — and the engine that climbed 3,425 m on a recovered Day 4 is more than enough to finish.
