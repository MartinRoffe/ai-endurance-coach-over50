# Coach Chat — request lifecycle walkthrough

A companion to [`ai-architecture.md`](./ai-architecture.md). That guide explains the AI
patterns in isolation; this one traces a **single coach message end-to-end** — from keystroke
to applied plan change — so you can see how the pieces fit together in one flow.

The part most worth understanding is step 3 (how the prompt is assembled), but the value is in
seeing the whole chain.

---

## The one mental model to hold onto

**Every turn rebuilds the entire prompt from scratch.** There is no persistent "session" with
Claude. On every single message the server reassembles and re-sends:

- `system` — persona + rules + a *fresh snapshot of all your data*
- `messages` — the last 20 conversation turns + your new one

Continuity is an *illusion* created by the SQLite history, the compressed long-term memo, and
SQL-based retrieval, all re-injected each turn. Once that clicks, the whole coach page makes
sense.

---

## 1. The browser sends the message — `templates/coach_chat.html`

When you hit Enter, `sendCoachMessage()` (~line 177) renders your message bubble, drops an
empty assistant bubble with a blinking `▋` cursor, then:

```js
fetch('/coach-chat-stream', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({message: text}),
});
```

Note what it does **not** send: any history. The conversation lives server-side, so the client
only ever sends the latest message. That keeps the client dumb and lets history survive a page
reload.

The response is not JSON — it's a stream. Lines ~210–253 are a hand-rolled SSE reader: read
bytes → decode → split on `\n\n` (the SSE event delimiter) → for each `data: {...}` line, parse
and switch on `event.type`. Four event types arrive:

| `event.type` | Browser does |
|--------------|--------------|
| `text`     | append the token, redraw the bubble (the live-typing effect) |
| `tool`     | show a hint, e.g. "🔍 checking your sleep history…" |
| `proposal` | push a plan-change card with APPLY / DISMISS |
| `done` / `error` | finalise or show an error |

This is the client half of the contract; the server emits exactly these shapes.

---

## 2. The endpoint assembles the conversation — `server.py` → `coach_chat_stream` (~line 2871)

```python
history = load_coach_history(limit=20)
messages = [{"role": m["role"], "content": m["content"]} for m in history]
messages.append({"role": "user", "content": user_message})
return StreamingResponse(_stream_coach_sse(messages, user_message, api_key),
                         media_type="text/event-stream")
```

Because the client is dumb, the server pulls the **last 20 messages** from the
`coach_conversations` SQLite table and appends your new one. That list of `{role, content}`
dicts is the **short-term memory** — the verbatim conversation window. `StreamingResponse`
wraps a *generator* (`_stream_coach_sse`), so FastAPI streams whatever the generator yields.

---

## 3. The prompt gets built — the core

Inside `_stream_coach_sse` (~line 2806), two lines build the entire prompt:

```python
context = _build_coach_context()
system  = _coach_system() + f"\n\n## Current Context\n{context}"
```

The prompt has two distinct parts, and the split is the key insight.

### `system` = persona + rules + live data

Composed in layers by `_coach_system()` (~line 2323):

1. **`COACH_VOICE`** (from `coach_voice.py`) — *who* the coach is: Martin's 50+ endurance
   coach, warm-but-honest tone, the events being trained for. This constant is imported by the
   email advice and post-workout analysis code too, so the personality is defined in exactly
   one place.
2. **Behavioural rules**, as plain prose — response style ("2–4 short paragraphs, **bold** key
   numbers"), *when* to call the proposal tool ("once per date"), a catalogue of what the
   read-tools can fetch, and a long domain block about Garmin TSB units and functional
   overreaching. That overreaching paragraph is pure prompt engineering: without it Claude
   would see a deeply negative TSB and wrongly raise an alarm, so the prompt teaches it the
   athlete's context in advance.
3. **`hr_channel_note(...)`** — the HR-vs-power caveat (wording depends on whether a power
   meter is active).
4. **`ATHLETE_CONSTRAINTS`** — the hard rules ("NEVER suggest running").
5. **`_build_coach_context()`** glued on under a `## Current Context` header.

### `_build_coach_context()` = the live data dump — `coach_context.py` (~line 431)

~25 markdown sections, string-appended from SQLite: today's PMC (CTL/ATL/TSB), readiness
z-score, HRV traffic light, sleep, body composition, nutrition, compliance, zone distribution,
the full remaining plan, the Haute Route phases, RPE logs, and more. Two things to notice:

- It ends by pulling **coach memory** (the LLM-compressed long-term memo) and **RAG results**
  (`retrieve_relevant_analyses` — your recent same-discipline sessions, fetched by SQL join).
  So the final prompt fuses **three memory types**: long-term memo, short-term message window,
  and retrieved past sessions.
- This data lives in the `system` prompt, *not* in a user message — it's stable framing the
  model should treat as ground truth, kept separate from the back-and-forth turns.

So the complete call is: a large `system` string (persona + rules + all your data) plus a short
`messages` list (the actual chat).

---

## 4. The agent loop runs — `_stream_coach_sse` (~lines 2821–2857)

```python
for _ in range(_COACH_MAX_TOOL_TURNS):          # capped at 6
    with client.messages.stream(model=MODEL_SMART, system=system,
                                tools=all_tools, messages=convo) as stream:
        for chunk in stream.text_stream:
            yield f"data: {json.dumps({'type':'text','chunk':chunk})}\n\n"
        final = stream.get_final_message()
    if final.stop_reason != "tool_use":
        break
    # else: run each tool, append results to convo, loop again
```

`all_tools` is `[_COACH_TOOL, *_READ_TOOLS]` — the one **write** tool (`propose_plan_change`,
~line 2365) plus the **read** tools. Each tool is just a name + description + JSON
`input_schema`; **the description is what tells Claude when to use it.**

As Claude generates prose, `stream.text_stream` yields tokens, and each is immediately
`yield`ed to the browser as a `text` event — that's the live typing effect. When the turn ends,
the loop checks `final.stop_reason`:

- Not `"tool_use"` → Claude is done → break.
- `"tool_use"` → Claude wants a tool. The code walks `final.content` blocks (~lines 2839–2852):
  - a `propose_plan_change` block is enriched and emitted as a `proposal` event;
  - a read-tool block emits a `tool` event (the "🔍 checking…" hint) and runs
    `_dispatch_read_tool` (~line 2450), a big if/else returning plain text (e.g.
    `get_sleep_history` formats the last 30 nights).
  - Each tool's output is packed into a `tool_result` block, appended to `convo` alongside the
    assistant turn, and the loop calls Claude again — now with the tool output in context.

That loop **is** the agent. The `range(6)` cap stops infinite tool-calling. Read tools resolve
silently and feed back in; the write tool is special (next section).

---

## 5. Proposals are suggestions, not actions — `_enrich_plan_proposal` (~line 2634)

When Claude calls `propose_plan_change`, the server does **not** change your plan.
`_enrich_plan_proposal` takes the raw tool input (date, duration, reason) and looks up the
*current* session for that date — checking `plan_overrides` first, then the base plan — so the
card can show "before → after". That enriched dict is streamed as a `proposal` event, and the
browser's `renderProposals` (~line 84) draws a blue card with APPLY / DISMISS buttons.

Nothing mutates until you click APPLY → `applyProposal` (~line 125) → `POST /apply-plan-change`
(~line 2921). *That* endpoint writes the `plan_override` to SQLite (the source of truth) and
best-effort pushes the single date to Garmin Connect.

**The model proposes; the human disposes.** Anything that changes real state goes through this
confirmation gate.

---

## 6. Persistence and memory close the loop

After the stream finishes (~line 2859), the full assistant reply is saved with
`save_coach_message`, and `_maybe_update_memo_bg` fires: if the conversation has grown or the
memo is stale, a **daemon thread** asks the *fast* model to recompress the chat into the
150–250 word durable memo — without blocking your response. Next message, that memo flows back
in via step 3.

Note your user message was already saved at the *top* of the generator (~line 2809), before
Claude is even called, so it survives a dropped connection.

---

## The flow at a glance

```
Browser (coach_chat.html)
  └─ POST /coach-chat-stream { message }           ← only the new message
        │
server.py: coach_chat_stream
  ├─ load_coach_history(20)  ────────────────────  short-term memory (SQLite)
  └─ StreamingResponse(_stream_coach_sse)
        │
_stream_coach_sse
  ├─ save user message (survives drops)
  ├─ system = _coach_system() + _build_coach_context()
  │     _coach_system()        = COACH_VOICE + rules + HR note + constraints
  │     _build_coach_context() = ~25 live data sections + memo + RAG
  ├─ agent loop (≤6 turns):
  │     client.messages.stream(system, tools, messages=convo)
  │       ├─ text tokens      → yield SSE 'text'   → live typing
  │       ├─ read tool_use    → yield SSE 'tool'   → _dispatch_read_tool → loop
  │       └─ propose_plan_change → yield SSE 'proposal' → confirmation card
  ├─ save assistant reply
  └─ _maybe_update_memo_bg  ──────────────────────  long-term memory (daemon thread)
        │
Browser: APPLY button
  └─ POST /apply-plan-change → set_plan_override (SQLite) + best-effort Garmin push
```

---

## Files referenced

| File | Role in this flow |
|------|-------------------|
| `templates/coach_chat.html` | Chat UI + SSE reader + proposal cards |
| `templates/coach_tab.html` | Page shell that includes the chat widget |
| `server.py` | Endpoint, system prompt, tool defs, agent loop, streaming, persistence |
| `coach_voice.py` | `COACH_VOICE`, `ATHLETE_CONSTRAINTS`, `hr_channel_note` |
| `coach_context.py` | `build_coach_context()` — the live data dump |
| `analysis.py` | `retrieve_relevant_analyses` (RAG), `load_analysis` (read tool) |
| `history.py` | `coach_conversations`, `coach_memory`, `plan_overrides` tables |
| `workouts.py` | `apply_override_to_garmin` (the best-effort Garmin push) |
