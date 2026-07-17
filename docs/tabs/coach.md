# Coach

**Nav:** the **Coach** item. Related: **Memory** (durable coach memo).

## What it's for

A conversational AI coach that already knows your training context — your form,
your plan, your recent sessions, how you've been fuelling and recovering — so you
can ask real questions and get answers grounded in your actual data, and even
adjust your plan from the chat.

> 📸 *Screenshot: the Coach chat with a reply streaming in and a plan-change proposal card.*

## What you'll see

A chat window. You type a question; the coach streams back a reply. Before each
answer it quietly assembles a rich picture of where you are:

- Your current training load (CTL / ATL / TSB) and today's readiness.
- Every remaining session across all your plans (12-week build, Tenerife camp,
  event prep, Haute Route with power targets when FTP is known).
- Recent activities and their AI analyses, body composition, and any active plan
  overrides.
- Your recent RPE logs, in-ride fuelling compliance, back-to-back fatigue notes,
  and your calorie/macro intake (today's full breakdown plus 14-day averages).
- **When your power meter is active:** Coggan zone table, weekly TSS, measured
  W/kg, Pw:HR decoupling, power zone distribution, ride kJ, and dual-channel
  pacing guidance (watts for intervals; HR for readiness and fatigue).

So you can ask things like "I felt flat on yesterday's intervals — should I
change Thursday?" and it answers with your numbers in mind.

## How to use it

- **Just talk to it.** Ask about pacing, fuelling, whether to push or back off,
  how your week is shaping up — anything a coach with your data could answer.
  Type as usual, or use optional **push-to-talk**: click **MIC**, speak, click
  **STOP** (or wait for silence) — the transcript lands in the box and sends
  automatically. Replies can be spoken aloud (**SPEAK** / **MUTED** toggles
  that). Voice runs in the browser only; Chrome works best. Plan-change cards
  still need a click on **Apply**.
- **Accept or decline plan changes.** When the coach suggests a concrete change
  (a different duration or a session-type swap), it appears as a **confirmation
  card**, not an automatic edit. Approve it and the change is saved as a one-day
  override that flows through to your [Calendar](plan.md) and the daily email,
  and is **best-effort pushed to Garmin** for that date only (same funnel as the
  Readiness Apply buttons — see [How the app works](../how-it-works.md#how-a-plan-change-works)).
  Ignore the card and nothing changes.
- **Commitments and session notes.** The coach can also save durable commitments
  (checkpoints / guardrails) and short notes on a calendar day without a
  confirmation card — those write immediately so they survive the next chat.

## Memory

**Nav:** the **Memory** item.

A compact durable memo of your goals, tendencies, and past decisions. It is
refreshed in the background as conversations grow, so the coach has continuity
beyond the last ~20 messages on screen. Open **Memory** to read or refresh it.

## Good to know

- **It remembers across sessions** via Memory (above), not by keeping a live
  Claude session open — every turn rebuilds context from SQLite.
- **Dual-channel coaching.** When your power meter is active, the coach uses
  watts for interval pacing and load; HR remains primary for readiness, HRV
  modulation, and fatigue. See **[Power Training](../power-training.md)**.
- **The coach needs your Anthropic API key.** Without it, this tab is inert.
- **It advises; it doesn't act on its own** for plan overrides. Every plan change
  passes through your explicit approval first.
- **Technical deep-dive.** How the prompt is assembled, tools, and streaming:
  [AI Architecture](../ai-architecture.md) and
  [Coach chat walkthrough](../coach-chat-walkthrough.md).
