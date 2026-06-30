# AI Architecture — a learning guide

This document explains the **AI engineering** side of the endurance-coach app: how Claude
is actually used, where each pattern lives in the code, and what transferable concept each
one teaches. It assumes you know Python, SQL, and HTML/CSS, but not much about applied AI.

It's written to be read top-to-bottom as a tutorial, then kept as a reference.

> **Companion:** for a single coach message traced end-to-end (browser → prompt assembly →
> agent loop → applied plan change), see
> [`coach-chat-walkthrough.md`](./coach-chat-walkthrough.md).

---

## The one idea that explains everything

Almost none of the intelligence lives in clever model code. It lives in **how data is
turned into text and fed to Claude**. This is sometimes called *context engineering*, and
it's the most important thing to understand about this app.

The pattern is the same everywhere:

1. **Pull** structured data out of SQLite — `history.py`
2. **Format** it into a plain-text prompt — `coach_context.py`, the `_build_*_prompt` helpers
3. **Call** Claude with a `system` prompt (who it is + the rules) and `messages` (the request)

If you internalise that loop, you understand most of the app. Everything below is a
variation on it.

---

## Model routing — `llm.py`

The whole file is two constants:

```python
MODEL_SMART = "claude-sonnet-4-6"          # coach chat, post-workout analysis, stage plans
MODEL_FAST  = "claude-haiku-4-5-20251001"  # blurbs, nutrition targets, memory summaries
```

Every call site imports these instead of hardcoding a model string.

**Concept: model routing.** Pick the cheapest model that's good enough *per task*. Reasoning
and judgement (coaching, analysis) get the smart model; cheap throwaway text generation gets
the fast one. Centralising the IDs means upgrading a model is a one-line change.

**Try this:** grep for `MODEL_FAST` and look at every job that uses it. Ask yourself for each
one: could this be rule-based instead of an LLM call? Could any `MODEL_FAST` job actually need
`MODEL_SMART`, or vice versa? That judgement *is* the skill.

---

## The basic call shape — `report.py` → `generate_advice` (~line 83)

This is the cleanest example of a single Claude call. Three things to notice:

```python
client = anthropic.Anthropic(api_key=api_key)
message = client.messages.create(
    model=MODEL_SMART,
    max_tokens=500,
    temperature=0,
    messages=[{"role": "user", "content": prompt}],
    system=system,
)
text = message.content[0].text
```

1. **`system` is separate from `messages`.** The system prompt is *who Claude is and the
   rules it follows*; messages are *the actual request/conversation*. Keep persona out of
   the per-request payload. (Here the persona comes from `coach_persona_brief()`.)
2. **`temperature=0`.** Deterministic output. Daily training advice shouldn't be random;
   creative tasks would use a higher value. Temperature is your randomness dial.
3. **`message.content[0].text`.** The response is a *list of content blocks*, not a string.
   For plain text you take `[0].text`. This list structure becomes critical once tools are
   involved (see Tool use below) — a response can contain text blocks *and* tool-use blocks.

**Concept: the system/user split, and the dials (`max_tokens`, `temperature`).**

---

## Graceful degradation — same function

If `ANTHROPIC_API_KEY` is unset, `generate_advice` returns `_rule_based_advice()` — a
hand-written if/else over the same metrics. And the live call is wrapped so an API error
falls back to the same rules:

```python
except anthropic.APIStatusError as e:
    logging...warning("Anthropic API error (%s), using rule-based advice", e.status_code)
    return _rule_based_advice(m, stats, comp_z)
```

**Concept: degrade, never crash.** A good AI feature has a non-AI floor. This app is fully
usable — email, dashboard, advice — with no API key at all; you just get the rule-based
version. The LLM is an *enhancement layer*, not a hard dependency. The same defensive habit
shows up in every Garmin API call (each is individually try/except'd and leaves a field
`None` rather than failing the whole fetch).

---

## Context construction — `coach_context.py` → `build_coach_context` (~line 431)

This ~600-line function is the heart of the app and the best single thing to study. It
assembles roughly 25 labelled markdown sections — training load (PMC), today's readiness,
HRV traffic light, sleep, body composition, nutrition, compliance, zone distribution,
durability, the full plan, the Haute Route phases, and more — into one large string. That
string becomes the coach's live context every turn.

What to notice as a learner:

- **It's just string-building.** `parts.append("## Sleep History")`, then
  `"\n".join(parts)`. There is no magic — a prompt is a string you build with ordinary code.
- **Inline caveats are prompt engineering.** Look for lines like
  *"Garmin training-load units, NOT Coggan TSS"* and *"NOT necessarily the same workout
  type as today"*. These exist to pre-empt mistakes the model would otherwise make. Writing
  these defensive notes is a core prompt-engineering skill: you are debugging the model's
  assumptions in advance.
- **Match context size to the job.** `build_advice_context` (~line 278) is a *trimmed*
  version of the same idea for the morning email — fewer sections, smaller payload. Don't
  send everything everywhere; more context costs money, adds latency, and can dilute the
  model's focus.

**Concept: context engineering.** The quality of the answer is mostly determined here, before
Claude is even called.

---

## Retrieval (RAG) without embeddings — `analysis.py` → `retrieve_relevant_analyses` (~line 1306)

This is a useful myth-buster. People associate "RAG" (retrieval-augmented generation) with
vector databases and embeddings. Here it's a **SQL join**:

```sql
SELECT ... FROM activity_analyses an
JOIN activities ac ON ac.activity_id = an.activity_id
WHERE ac.type_key IN (<keys matching today's discipline>)
ORDER BY ac.date DESC
LIMIT ?
```

It finds your most recent past analyses in the same discipline as the upcoming session,
truncates each to ~280 characters, and injects them into the context so the coach can say
"last time you did this kind of session…".

**Concept: retrieval = fetch the relevant facts and put them in the prompt.** When your data
is already structured (as it is in a SQLite database), SQL *is* your retriever. Embeddings
only earn their complexity when you need *semantic* similarity over unstructured text. Reach
for the simple version first.

---

## Tool use / the agentic loop — `server.py` → `_call_coach` (~line 2672)

This is the most advanced pattern in the app and the most worth your time. The coach is given
tools:

- One **write** tool — `propose_plan_change` (~line 2365) — to suggest changing a session.
- Several **read-only** tools — `get_meal_cycle`, `get_hr_plan`, `get_activity_analysis`,
  etc. — that let the coach fetch full detail on demand instead of bloating every prompt.

A tool is just a name, a description, and a JSON `input_schema`:

```python
_COACH_TOOL = {
    "name": "propose_plan_change",
    "description": "Propose changing a planned session — duration, type, or both. ...",
    "input_schema": {
        "type": "object",
        "properties": {
            "date":         {"type": "string",  "description": "Session date (YYYY-MM-DD)"},
            "duration_min": {"type": "integer", "description": "New duration in minutes"},
            "reason":       {"type": "string",  "description": "Why ... (1–2 sentences)"},
            ...
        },
        "required": ["date", "duration_min", "reason"],
    },
}
```

**The description IS the prompt.** It's how Claude decides *when* to call the tool. Good tool
descriptions are prompt engineering.

The agent loop itself:

```python
for _ in range(_COACH_MAX_TOOL_TURNS):
    response = client.messages.create(model=MODEL_SMART, system=system,
                                      tools=all_tools, messages=convo)
    tool_results = []
    for block in response.content:           # response is a LIST of blocks
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            # run the tool, build a tool_result
            tool_results.append({"type": "tool_result",
                                 "tool_use_id": block.id, "content": content})
    if response.stop_reason != "tool_use":    # Claude is done asking for tools
        break
    convo += [{"role": "assistant", "content": response.content},
              {"role": "user",      "content": tool_results}]
```

Walk through what happens:

1. Call Claude with the tools available.
2. Claude replies with content blocks — possibly text, possibly `tool_use` requests.
3. For each `tool_use`, you run the actual function and capture its output.
4. If Claude's `stop_reason` is `"tool_use"`, it's waiting for results: append the
   assistant turn *and* a user turn containing the `tool_result` blocks, then loop again.
5. When `stop_reason` is anything else, Claude has finished — break.

**That loop is what people mean by "an agent."** The model decides which tools to call and
when; your code just executes them and feeds the results back. The `range(MAX_TURNS)` cap is
a safety rail so it can't loop forever.

**Human-in-the-loop design:** notice the write tool *doesn't* change anything. It returns a
*proposal* that the UI renders as a confirmation card; the plan is only mutated when the user
clicks approve (`POST /apply-plan-change`). Anything that mutates real state should require
confirmation — the model proposes, the human disposes.

---

## Agent memory — `server.py` → `_regenerate_coach_memory` (~line 2758)

The coach has two tiers of memory:

- **Short-term:** the last 20 chat messages, passed verbatim each turn.
- **Long-term:** a compact 150–250 word "memo" stored in the `coach_memory` SQLite table.

The memo is produced by Claude itself: a background thread periodically asks the *fast* model
to compress recent conversation into durable notes — goals, tendencies, decisions made. The
prompt explicitly says **omit anything already in live data** (today's CTL, readiness,
upcoming sessions), because the coach receives all of that fresh every turn. So the memo only
carries what *wouldn't* otherwise survive: the cross-session, slowly-changing stuff.

It runs in a daemon thread (`_maybe_update_memo_bg`) so summarising never blocks the chat
response, and only fires when the conversation has grown or the memo is stale
(`_MEMO_MIN_MESSAGES`, `_MEMO_STALE_HOURS`).

**Concept: memory = short verbatim window + LLM-compressed long-term store.** This is how you
give an assistant continuity without an ever-growing (and ever-more-expensive) context.

---

## Two supporting patterns

**Streaming — `server.py` → `_stream_coach_sse` (~line 2806).** Uses `client.messages.stream`
plus Server-Sent Events so the reply appears token-by-token in the browser instead of arriving
all at once. Same tool loop as above, wrapped in a streaming context manager. Streaming is
purely a UX improvement — the total work is identical, it just *feels* faster.

**Caching — see the cache table in `CLAUDE.md`.** Several layers (`daily_advice`, `text_cache`,
`activity_analyses`, `workout_descriptions`, …) exist for one reason: **never pay for the same
LLM call twice.** Generated text is keyed (often by date or by a session key) and reused. Some
caches even store *negative* results so a failed generation isn't retried in a hot loop. Cost
and latency control is a real part of AI engineering, not an afterthought.

---

## A learning path through the code

Read these in order, easiest to hardest:

1. `llm.py` — model routing (2 lines).
2. `report.py` → `generate_advice` and `_build_advice_prompt` — a single Claude call + its prompt.
3. `coach_context.py` → `build_advice_context`, then `build_coach_context` — context engineering at two scales.
4. `analysis.py` → `retrieve_relevant_analyses` — retrieval as SQL.
5. `server.py` → `_call_coach` and `_COACH_TOOL` / `_READ_TOOLS` — the tool-use agent loop.
6. `server.py` → `_regenerate_coach_memory` — LLM-compressed long-term memory.

By the end you'll have seen single-shot calls, prompt engineering, retrieval, function-calling
agents, streaming, caching, and memory — which is most of an applied-AI-engineering syllabus,
all in code you already own.

## The single highest-leverage experiment

Open `_build_advice_prompt` in `report.py`, change the instructions (e.g. ask for a different
tone, an extra section, or a stricter format), regenerate the advice, and read the diff in the
output. Editing a prompt and watching the result change is the fastest way to build real
intuition for prompt engineering — faster than any amount of reading, including this document.

---

*Reference map of the AI-relevant files:*

| File | AI role |
|------|---------|
| `llm.py` | Model IDs (smart vs fast) |
| `coach_voice.py` | Coach persona / voice constants, athlete constraints |
| `coach_context.py` | Builds the big context blocks for advice + chat |
| `report.py` | Daily advice, weekly briefing, email text (single-shot calls + rule-based fallback) |
| `analysis.py` | Post-workout analysis pipeline, RAG retrieval, prefetch generators |
| `server.py` | Coach chat: system prompt, tool definitions, agent loop, streaming, memory |
| `modulation.py` | Rule-based HRV traffic light (non-LLM decision logic the prompts reference) |
| `alerts.py` | Rule-based fatigue alerts (also surfaced into context) |
