# User Guide

A complete walkthrough of the AI Endurance Coach dashboard — what every tab shows,
how to read each chart, and what the buttons do.

**In the running app:** open **Help** in the top nav
(`http://127.0.0.1:8743/help`). That is the primary way to read this guide —
product workflow through coach chat, plus Architecture and AI Architecture for
the technical side. The Markdown files here are the authoring source the Help
centre renders.

If you just want to install and run the app, start with the
[project README](../README.md).

> 📸 *Screenshot: the dashboard home page with the top navigation bar visible.*

## How this guide is organised

| Page | Covers |
|------|--------|
| **[How the app works](how-it-works.md)** | End-to-end story: morning workflow, plan changes, coach chat, data flow |
| **[Getting Started](getting-started.md)** | Install, configure your `.env`, first run, connecting your Garmin account |
| **[Key Concepts](concepts.md)** | The mental model: readiness score, training load (CTL/ATL/TSB), the HRV traffic light, and the dual-channel HR + power model |
| **[Power Training](power-training.md)** | Power meter setup, activation, measured FTP/TSS, and what stays HR-primary vs watts-primary |
| **[Readiness](tabs/readiness.md)** | The home page — your daily readiness score, metric tiles, nutrition card, fatigue alerts, and session modulation |
| **[Performance](tabs/performance.md)** | The **Performance ▾** group: the Performance tab (training-load and trend charts) and the Analysis tab (per-workout AI review) |
| **[Plan](tabs/plan.md)** | The **Plan ▾** group: Calendar, Training, and Compliance |
| **[Health](tabs/health.md)** | The **Health ▾** group: Sleep and Body |
| **[Nutrition](tabs/nutrition.md)** | Top-level **Nutrition** tab — meal plan, ride fuelling, recipes, shopping |
| **[Events](tabs/events.md)** | The **Events ▾** group: the Tenerife camp and the Haute Route Alpes 2027 plan |
| **[Coach](tabs/coach.md)** | The AI coach chat — context, plan-change proposals, Memory, and commitments |
| **[Email & Automation](email-and-automation.md)** | The daily email, the Monday briefing, scheduling, and the command-line flags |
| **[FAQ & Troubleshooting](faq.md)** | Missing data, sign-in problems, clearing stale AI text, and protecting the dashboard |

### For developers

| Page | Covers |
|------|--------|
| **[Architecture](architecture.md)** | Interactive Mermaid system map (also `/architecture` fullscreen) |
| **[AI Architecture](ai-architecture.md)** | Context engineering, model routing, tools, caching |
| **[Coach chat walkthrough](coach-chat-walkthrough.md)** | One coach message end-to-end (browser → SSE → Apply) |

## The navigation bar at a glance

The bar across the top of every page has these items:

- **Readiness** — the home page (your single-page morning check-in).
- **Performance ▾** → Performance · Analysis
- **Plan ▾** → Calendar · Training · Compliance
- **Nutrition** — meal plan hub with sub-pages
- **Health ▾** → Sleep · Body
- **Events ▾** → Tenerife · Haute Route
- **Coach** — chat with your AI coach.
- **Memory** — durable coach memo across sessions.
- **Help** — this guide, rendered in the app (`/help`).

Wherever you see a small **ⓘ** next to a label, hover or tap it for a short
plain-language explanation of that metric.

## Reading the colours

The dashboard uses a consistent colour language throughout:

- 🟢 **Green** — good / on track / a deficit (for calories).
- 🟠 **Amber** — caution / ease off / a small surplus.
- 🔴 **Red** — warning / back right off / a large surplus.

So a red HRV traffic light and a red calorie balance mean opposite things in
training terms but follow the same rule: green is the comfortable end, red is the
"pay attention" end.

## Want a PDF?

Optional offline export (the in-app Help centre is preferred for sharing):

```bash
bash docs/build-pdf.sh   # produces docs/user-guide.pdf
```

This needs [`pandoc`](https://pandoc.org/) and a LaTeX engine installed
(`brew install pandoc basictex` on macOS). The Markdown files here are the
source of truth — the PDF is just a portable copy you can regenerate any time.
